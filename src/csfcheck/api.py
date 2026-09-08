"""FastAPI service: organisations, assessments, question flow and results.

Each assessment gets one random token when it is created; every request about
that assessment must send it in the ``X-Assessment-Token`` header. Only its
SHA-256 is stored.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import secrets
from dataclasses import asdict

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .db import AnswerRow, Assessment, Organisation, catalog_from_db, load_core, make_engine
from .engine import AnswerError, Engine
from .model import load_risk_model, load_targets
from .questions import load_bank
from .workbook import build_workbook

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class OrganisationIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    profile: dict[str, bool] = Field(default_factory=dict)


class AnswerIn(BaseModel):
    question_id: str
    value: str
    evidence: str = ""


class AnswersIn(BaseModel):
    answers: list[AnswerIn]


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_app(database_url: str) -> FastAPI:
    db = make_engine(database_url)
    load_core(db)
    catalog = catalog_from_db(db)
    # Validates questions.yaml against the catalog that is actually in the
    # database; an inconsistent bank stops the app here.
    engine = Engine(catalog, load_bank(catalog=catalog), load_targets(catalog), load_risk_model())

    app = FastAPI(
        title="csfcheck",
        description="NIST CSF 2.0 self-assessment for small non-profits",
        version="0.1.0",
    )
    app.state.engine = engine
    app.state.db = db

    def session():
        with Session(db) as s:
            yield s

    def assessment(
        assessment_id: int,
        x_assessment_token: str = Header(...),
        s: Session = Depends(session),
    ) -> Assessment:
        a = s.get(Assessment, assessment_id)
        if a is None or not hmac.compare_digest(a.token_hash, _hash(x_assessment_token)):
            raise HTTPException(404, "assessment not found or wrong token")
        return a

    def state(a: Assessment):
        answers = {r.question_id: r.value for r in a.answers}
        evidence = {r.question_id: r.evidence for r in a.answers if r.evidence}
        return a.organisation.profile, answers, evidence

    def question_json(q):
        return {
            "id": q.id,
            "section": q.section,
            "text": q.text,
            "options": [{"value": o.value, "label": o.label} for o in q.options],
            "subcategories": list(q.maps),
        }

    @app.get("/health")
    def health():
        return {"status": "ok", "csf": f"{catalog.document} {catalog.version}",
                "subcategories": len(catalog.subcategories), "questions": len(engine.bank.questions)}

    @app.get("/profile-flags")
    def profile_flags():
        return engine.bank.flags

    @app.post("/organisations", status_code=201)
    def create_organisation(body: OrganisationIn, s: Session = Depends(session)):
        try:
            profile = engine.bank.normalise_profile(body.profile)
        except KeyError as exc:
            raise HTTPException(422, str(exc.args[0])) from None
        org = Organisation(name=body.name, profile=profile)
        s.add(org)
        s.commit()
        return {"id": org.id, "name": org.name, "profile": profile}

    @app.post("/organisations/{organisation_id}/assessments", status_code=201)
    def start_assessment(organisation_id: int, s: Session = Depends(session)):
        org = s.get(Organisation, organisation_id)
        if org is None:
            raise HTTPException(404, "organisation not found")
        token = secrets.token_urlsafe(24)
        a = Assessment(organisation_id=org.id, token_hash=_hash(token))
        s.add(a)
        s.commit()
        total = len(engine.bank.applicable(org.profile))
        return {"id": a.id, "token": token, "questions_for_profile": total}

    @app.get("/assessments/{assessment_id}/next")
    def next_questions(limit: int = Query(5, ge=1, le=100), a: Assessment = Depends(assessment)):
        profile, answers, _ = state(a)
        qs = engine.next_questions(profile, answers, limit)
        result = engine.assess(profile, answers)
        return {
            "questions": [question_json(q) for q in qs],
            "answered": len(answers),
            "remaining": result.totals["questions_asked"] - len(answers),
            "complete": result.complete,
        }

    @app.post("/assessments/{assessment_id}/answers")
    def submit_answers(body: AnswersIn, a: Assessment = Depends(assessment), s: Session = Depends(session)):
        a = s.merge(a)
        profile, answers, _ = state(a)
        incoming = {x.question_id: x.value for x in body.answers}
        try:
            engine.check_answers(profile, {**answers, **incoming})
        except AnswerError as exc:
            raise HTTPException(422, str(exc)) from None
        existing = {r.question_id: r for r in a.answers}
        for x in body.answers:
            row = existing.get(x.question_id)
            if row is None:
                a.answers.append(AnswerRow(question_id=x.question_id, value=x.value, evidence=x.evidence))
            else:
                row.value, row.evidence = x.value, x.evidence or row.evidence
        # Lowering an answer can make earlier follow-up answers unreachable;
        # drop them so the stored state never holds a skipped question.
        merged = {r.question_id: r.value for r in a.answers}
        status = engine.question_status(profile, merged)
        for r in list(a.answers):
            if status[r.question_id] != "asked":
                a.answers.remove(r)
        s.commit()
        return {"saved": len(body.answers), "answered": len(a.answers)}

    @app.get("/assessments/{assessment_id}/profile")
    def profile(a: Assessment = Depends(assessment)):
        prof, answers, _ = state(a)
        result = engine.assess(prof, answers)
        return {
            "complete": result.complete,
            "totals": result.totals,
            "subcategories": [asdict(r) for r in result.subcategories],
        }

    @app.get("/assessments/{assessment_id}/action-plan")
    def action_plan(limit: int | None = Query(None, ge=1), a: Assessment = Depends(assessment)):
        prof, answers, _ = state(a)
        result = engine.assess(prof, answers)
        actions = result.actions[:limit] if limit else result.actions
        return {"complete": result.complete, "actions": [asdict(x) for x in actions]}

    @app.get("/assessments/{assessment_id}/workbook")
    def workbook(a: Assessment = Depends(assessment)):
        prof, answers, evidence = state(a)
        result = engine.assess(prof, answers)
        buf = io.BytesIO()
        build_workbook(engine, result, answers, evidence, a.organisation.name).save(buf)
        buf.seek(0)
        name = f"csf-assessment-{a.id}.xlsx"
        return StreamingResponse(buf, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})

    return app
