"""FastAPI service: organisations, assessments, question flow and results.

The JSON API lives here; the server-rendered pages are in ``web``.

Each assessment gets one random token when it is created; every request about
that assessment must send it in the ``X-Assessment-Token`` header. Only its
SHA-256 is stored. A retake keeps the token, so the same header opens every
version of the organisation's assessment and the comparison between them.
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

from . import web
from .compare import compare
from .db import Assessment, Organisation, catalog_from_db, load_core, make_engine, retake, store_answers, versions
from .engine import AnswerError, Engine
from .model import load_risk_model, load_targets
from .questions import load_bank
from .workbook import Progress, build_workbook

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


class RetakeIn(BaseModel):
    profile: dict[str, bool] | None = None
    copy_answers: bool = True


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_app(database_url: str) -> FastAPI:
    db = make_engine(database_url)
    load_core(db)
    catalog = catalog_from_db(db)
    # Validates questions.yaml against the catalog that is actually in the
    # database; an inconsistent bank stops the app here.
    engine = Engine(catalog, load_bank(catalog=catalog), load_targets(catalog), load_risk_model(catalog))

    app = FastAPI(
        title="csfcheck",
        description="NIST CSF 2.0 self-assessment for small non-profits",
        version="0.3.0",
    )
    app.state.engine = engine
    app.state.db = db
    web.install(app, engine, db, _hash)

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
        return a.answer_state()

    def previous_of(s: Session, a: Assessment, other: int | None) -> Assessment:
        """The version to compare ``a`` with: ``other`` if given, else the one it was retaken from."""
        b = s.get(Assessment, other if other is not None else a.previous_id) if (other or a.previous_id) else None
        if b is None or b.organisation_id != a.organisation_id or b.token_hash != a.token_hash:
            raise HTTPException(404, "no earlier version of this assessment to compare with")
        return b

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
        a = Assessment(organisation_id=org.id, token_hash=_hash(token), version=1, profile=org.profile)
        s.add(a)
        s.commit()
        total = len(engine.bank.applicable(org.profile))
        return {"id": a.id, "version": a.version, "token": token, "questions_for_profile": total}

    @app.post("/assessments/{assessment_id}/retake", status_code=201)
    def retake_assessment(body: RetakeIn | None = None, a: Assessment = Depends(assessment),
                          s: Session = Depends(session)):
        body = body or RetakeIn()
        a = s.merge(a)
        try:
            new = retake(engine, s, a, body.profile, body.copy_answers)
        except KeyError as exc:
            raise HTTPException(422, str(exc.args[0])) from None
        s.commit()
        return {
            "id": new.id,
            "version": new.version,
            "previous_id": a.id,
            "answers_copied": len(new.answers),
            "questions_for_profile": len(engine.bank.applicable(new.effective_profile)),
        }

    @app.get("/assessments/{assessment_id}/versions")
    def list_versions(a: Assessment = Depends(assessment), s: Session = Depends(session)):
        out = []
        for v in versions(s, a):
            profile, answers, _ = state(v)
            result = engine.assess(profile, answers)
            t = result.totals
            out.append({
                "id": v.id, "version": v.version, "previous_id": v.previous_id, "complete": result.complete,
                "answered": len(answers), "subcategories_at_target": t["subcategories_at_target"],
                "total_risk": t["total_risk"], "actions": len(result.actions),
            })
        return {"organisation": a.organisation.name, "versions": out}

    @app.get("/assessments/{assessment_id}/compare")
    def compare_versions(other: int | None = Query(None, alias="with"), a: Assessment = Depends(assessment),
                         s: Session = Depends(session)):
        a = s.merge(a)
        b = previous_of(s, a, other)
        p_old, ans_old, _ = state(b)
        p_new, ans_new, _ = state(a)
        c = compare(engine, engine.assess(p_old, ans_old), engine.assess(p_new, ans_new), ans_old, ans_new)
        return {
            "before": {"id": b.id, "version": b.version},
            "after": {"id": a.id, "version": a.version},
            "totals": c.totals,
            "profile_changes": {k: {"before": v[0], "after": v[1]} for k, v in c.profile_changes.items()},
            "functions": [asdict(f) for f in c.functions],
            "subcategories": [asdict(x) for x in c.subcategories if x.change != "unchanged"],
            "actions": [asdict(x) for x in c.actions],
            "answers": [asdict(x) for x in c.answers],
        }

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
            engine.check_answers(profile, {**answers, **incoming}, only=incoming)
        except AnswerError as exc:
            raise HTTPException(422, str(exc)) from None
        stored = store_answers(engine, a, {x.question_id: (x.value, x.evidence or None) for x in body.answers})
        s.commit()
        return {"saved": len(body.answers), "answered": stored}

    @app.get("/assessments/{assessment_id}/profile")
    def profile(a: Assessment = Depends(assessment)):
        prof, answers, _ = state(a)
        result = engine.assess(prof, answers)
        return {
            "version": a.version,
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
    def workbook(a: Assessment = Depends(assessment), s: Session = Depends(session)):
        a = s.merge(a)
        prof, answers, evidence = state(a)
        result = engine.assess(prof, answers)
        progress = None
        if a.previous_id is not None:
            b = previous_of(s, a, None)
            p_old, ans_old, _ = state(b)
            progress = Progress(compare(engine, engine.assess(p_old, ans_old), result, ans_old, answers),
                                f"version {b.version}", f"version {a.version}")
        buf = io.BytesIO()
        build_workbook(engine, result, answers, evidence, a.organisation.name, progress=progress).save(buf)
        buf.seek(0)
        name = f"csf-assessment-{a.id}.xlsx"
        return StreamingResponse(buf, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})

    return app
