"""Server-rendered questionnaire, heat map and action plan (Jinja templates).

The pages use the same engine and tables as the JSON API. Starting an
assessment sets its token in an HttpOnly cookie scoped to that assessment's
pages, and the token is shown once so the assessment can be resumed from
another browser. There are no user accounts. A retake keeps the token, so the
same code opens every version and the progress page between them.
"""

from __future__ import annotations

import hmac
import io
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.engine import Engine as SAEngine
from sqlalchemy.orm import Session

from .compare import compare
from .compare import summary_points as progress_points
from .db import Assessment, Organisation, retake, store_answers, versions
from .engine import ASKED, SKIPPED_FOLLOW_UP, SKIPPED_PROFILE, AnswerError, Engine
from .heatmap import render_svg
from .report import build_report, summary_points
from .rollup import by_function
from .workbook import Progress, build_workbook

HERE = Path(__file__).parent
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class NotAllowed(Exception):
    """No valid token for the assessment; rendered as a plain 404 page."""


def cookie_name(assessment_id: int) -> str:
    return f"csfcheck_{assessment_id}"


def slug(section: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", section.lower()).strip("-")


@dataclass
class QuestionView:
    q: object
    status: str
    value: str | None
    evidence: str
    note: str = ""  # why a skipped question is not asked
    parent_text: str = ""
    waiting: bool = False  # a follow-up whose parent has no answer yet


@dataclass
class SectionView:
    name: str
    slug: str
    asked: int
    answered: int
    skipped: int

    @property
    def done(self) -> bool:
        return self.asked > 0 and self.answered == self.asked


def build_router(engine: Engine, db: SAEngine, token_hash) -> APIRouter:
    router = APIRouter(include_in_schema=False)
    templates = Jinja2Templates(directory=str(HERE / "templates"))
    bank = engine.bank
    sections = list(dict.fromkeys(q.section for q in bank.questions))
    by_slug = {slug(s): s for s in sections}

    def session():
        with Session(db) as s:
            yield s

    def assessment(assessment_id: int, request: Request, s: Session = Depends(session)) -> Assessment:
        token = request.cookies.get(cookie_name(assessment_id), "")
        a = s.get(Assessment, assessment_id)
        if a is None or not token or not hmac.compare_digest(a.token_hash, token_hash(token)):
            raise NotAllowed()
        return a

    def state(a: Assessment):
        return a.answer_state()

    def progress(profile, answers):
        status = engine.question_status(profile, answers)
        views = []
        for name in sections:
            qs = [q for q in bank.questions if q.section == name]
            asked = [q for q in qs if status[q.id] == ASKED]
            views.append(SectionView(name, slug(name), len(asked), sum(q.id in answers for q in asked),
                                     len(qs) - len(asked)))
        return status, views

    def previous_of(s: Session, a: Assessment) -> Assessment | None:
        b = s.get(Assessment, a.previous_id) if a.previous_id else None
        if b is None or b.organisation_id != a.organisation_id or b.token_hash != a.token_hash:
            return None
        return b

    def progress_for(s: Session, a: Assessment, result=None) -> Progress | None:
        """This version against the one it was retaken from, if any."""
        b = previous_of(s, a)
        if b is None:
            return None
        p_old, ans_old, _ = state(b)
        p_new, ans_new, _ = state(a)
        result = result or engine.assess(p_new, ans_new)
        return Progress(compare(engine, engine.assess(p_old, ans_old), result, ans_old, ans_new),
                        f"version {b.version}", f"version {a.version}")

    def set_token(resp, assessment_id: int, token: str) -> None:
        resp.set_cookie(cookie_name(assessment_id), token, path=f"/a/{assessment_id}", httponly=True,
                        samesite="lax")

    def render(request: Request, name: str, status_code: int = 200, **ctx) -> HTMLResponse:
        return templates.TemplateResponse(request, name, ctx, status_code=status_code)

    def page(request: Request, a: Assessment, name: str, **ctx) -> HTMLResponse:
        profile, answers, _ = state(a)
        status, views = progress(profile, answers)
        asked = sum(v.asked for v in views)
        done = sum(v.answered for v in views)
        return render(request, name, a=a, org=a.organisation, sections=views, asked=asked, answered=done,
                      pct=round(100 * done / asked) if asked else 100, **ctx)

    def plain_condition(text: str) -> str:
        return text.replace("_", " ")

    def next_section(views: list[SectionView], after: str | None) -> str | None:
        """The next section with unanswered questions, looking after ``after`` first."""
        names = [v.slug for v in views]
        start = names.index(after) + 1 if after in names else 0
        for v in views[start:] + views[:start]:
            if v.asked and not v.done:
                return v.slug
        return None

    @router.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return render(request, "index.html", flags=bank.flags, questions=len(bank.questions),
                      subcategories=len(engine.catalog.subcategories))

    @router.post("/start")
    async def start(request: Request, s: Session = Depends(session)):
        form = await request.form()
        name = str(form.get("name", "")).strip()[:200]
        if not name:
            return render(request, "index.html", 422, flags=bank.flags, questions=len(bank.questions),
                          subcategories=len(engine.catalog.subcategories),
                          error="Please give the organisation a name.")
        profile = bank.normalise_profile({f: form.get(f) == "on" for f in bank.flags})
        org = Organisation(name=name, profile=profile)
        s.add(org)
        s.flush()
        token = secrets.token_urlsafe(24)
        a = Assessment(organisation_id=org.id, token_hash=token_hash(token), version=1, profile=profile)
        s.add(a)
        s.commit()
        resp = RedirectResponse(f"/a/{a.id}?new=1", status_code=303)
        set_token(resp, a.id, token)
        # Shown once on the overview page, then forgotten.
        resp.set_cookie(f"csfcheck_show_{a.id}", token, path=f"/a/{a.id}", httponly=True, samesite="lax",
                        max_age=60)
        return resp

    @router.post("/resume")
    def resume(request: Request, assessment_id: int = Form(...), token: str = Form(...),
               s: Session = Depends(session)):
        a = s.get(Assessment, assessment_id)
        if a is None or not hmac.compare_digest(a.token_hash, token_hash(token.strip())):
            return render(request, "index.html", 404, flags=bank.flags, questions=len(bank.questions),
                          subcategories=len(engine.catalog.subcategories),
                          error="No assessment matches that number and code.")
        resp = RedirectResponse(f"/a/{a.id}", status_code=303)
        for v in versions(s, a):  # the code opens every version of this assessment
            set_token(resp, v.id, token.strip())
        return resp

    @router.get("/a/{assessment_id}", response_class=HTMLResponse)
    def overview(request: Request, a: Assessment = Depends(assessment), s: Session = Depends(session)):
        profile, answers, _ = state(a)
        _, views = progress(profile, answers)
        token = request.cookies.get(f"csfcheck_show_{a.id}")
        resp = page(request, a, "overview.html", token=token, resume_at=next_section(views, None),
                    flags={f: bank.flags[f] for f, on in profile.items() if on}, versions=versions(s, a),
                    copied=request.query_params.get("retake") == "1")
        if token:
            resp.delete_cookie(f"csfcheck_show_{a.id}", path=f"/a/{a.id}")
        return resp

    @router.get("/a/{assessment_id}/questions")
    def questions(a: Assessment = Depends(assessment)):
        profile, answers, _ = state(a)
        _, views = progress(profile, answers)
        target = next_section(views, None)
        return RedirectResponse(f"/a/{a.id}/s/{target}" if target else f"/a/{a.id}/heatmap", status_code=303)

    @router.get("/a/{assessment_id}/s/{section}", response_class=HTMLResponse)
    def section_page(request: Request, section: str, a: Assessment = Depends(assessment)):
        if section not in by_slug:
            raise NotAllowed()
        profile, answers, evidence = state(a)
        status, views = progress(profile, answers)
        items = []
        for q in bank.questions:
            if q.section != by_slug[section]:
                continue
            view = QuestionView(q, status[q.id], answers.get(q.id), evidence.get(q.id, ""))
            if q.requires:
                parent = bank.by_id[q.requires[0]]
                view.parent_text = parent.text
                if view.status == SKIPPED_FOLLOW_UP:
                    pv = answers.get(parent.id)
                    if pv is None:
                        view.waiting = True
                    else:
                        view.note = f"Skipped because you answered “{parent.option(pv).label}” to: {parent.text}"
            if view.status == SKIPPED_PROFILE:
                view.note = f"Only asked if: {plain_condition(q.when.text)}"
            items.append(view)
        names = [v.slug for v in views if v.asked]
        here = names.index(section) if section in names else -1
        return page(
            request, a, "section.html", section=views[[v.slug for v in views].index(section)],
            items=[i for i in items if i.status == ASKED or i.waiting],
            skipped=[i for i in items if i.status != ASKED and not i.waiting],
            prev_slug=names[here - 1] if here > 0 else None,
            next_slug=names[here + 1] if 0 <= here < len(names) - 1 else None,
        )

    @router.post("/a/{assessment_id}/s/{section}")
    async def save_section(request: Request, section: str, a: Assessment = Depends(assessment),
                           s: Session = Depends(session)):
        if section not in by_slug:
            raise NotAllowed()
        a = s.merge(a)
        form = await request.form()
        profile, answers, _ = state(a)
        old = dict(answers)
        incoming = {k[2:]: str(v) for k, v in form.items() if k.startswith("q_") and str(v)}
        # A lowered parent on this page closes its follow-ups; their old values
        # are still in the form, so leave those out instead of rejecting them.
        status = engine.question_status(profile, {**answers, **incoming})
        incoming = {k: v for k, v in incoming.items() if status.get(k) == ASKED}
        try:
            engine.check_answers(profile, {**answers, **incoming}, only=incoming)
        except AnswerError as exc:
            return Response(str(exc), status_code=422, media_type="text/plain")
        store_answers(engine, a, {q: (v, str(form.get(f"e_{q}", "")).strip()) for q, v in incoming.items()})
        s.commit()

        before = engine.question_status(profile, old)
        profile, answers, _ = state(a)
        now, views = progress(profile, answers)
        opened = [q.id for q in bank.questions if q.section == by_slug[section]
                  and now[q.id] == ASKED and before[q.id] != ASKED and q.id not in answers]
        if form.get("go") == "back":
            names = [v.slug for v in views if v.asked]
            here = names.index(section) if section in names else 0
            target = names[here - 1] if here > 0 else section
        elif opened:
            # The answers just given opened follow-ups on this page.
            return RedirectResponse(f"/a/{a.id}/s/{section}#q-{opened[0]}", status_code=303)
        else:
            target = next_section(views, section)
        if target is None:
            return RedirectResponse(f"/a/{a.id}/heatmap", status_code=303)
        return RedirectResponse(f"/a/{a.id}/s/{target}", status_code=303)

    @router.get("/a/{assessment_id}/retake", response_class=HTMLResponse)
    def retake_form(request: Request, a: Assessment = Depends(assessment)):
        return page(request, a, "retake.html", flags=bank.flags, profile=a.effective_profile)

    @router.post("/a/{assessment_id}/retake")
    async def retake_post(request: Request, a: Assessment = Depends(assessment), s: Session = Depends(session)):
        form = await request.form()
        a = s.merge(a)
        profile = {f: form.get(f) == "on" for f in bank.flags}
        new = retake(engine, s, a, profile, copy_answers=form.get("copy") == "on")
        s.commit()
        resp = RedirectResponse(f"/a/{new.id}?retake=1", status_code=303)
        set_token(resp, new.id, request.cookies[cookie_name(a.id)])
        return resp

    @router.get("/a/{assessment_id}/progress", response_class=HTMLResponse)
    def progress_page(request: Request, a: Assessment = Depends(assessment), s: Session = Depends(session)):
        p = progress_for(s, a)
        if p is None:
            return RedirectResponse(f"/a/{a.id}", status_code=303)
        c = p.comparison
        return page(request, a, "progress.html", progress=p, c=c, points=progress_points(c, p.before),
                    changed=[x for x in c.subcategories if x.change != "unchanged"],
                    moved=[x for x in c.actions if x.status != "still open"])

    def results(a: Assessment):
        profile, answers, evidence = state(a)
        return engine.assess(profile, answers), answers, evidence

    @router.get("/a/{assessment_id}/heatmap", response_class=HTMLResponse)
    def heatmap(request: Request, a: Assessment = Depends(assessment)):
        result, _, _ = results(a)
        return page(request, a, "heatmap.html", result=result, svg=render_svg(engine.catalog, result),
                    points=summary_points(engine, result, a.organisation.name),
                    functions=by_function(engine.catalog, result))

    @router.get("/a/{assessment_id}/heatmap.svg")
    def heatmap_svg(a: Assessment = Depends(assessment)):
        result, _, _ = results(a)
        return Response(render_svg(engine.catalog, result), media_type="image/svg+xml")

    @router.get("/a/{assessment_id}/plan", response_class=HTMLResponse)
    def plan(request: Request, a: Assessment = Depends(assessment)):
        result, _, _ = results(a)
        groups = {h: [x for x in result.actions if x.horizon == h] for h in ("Now", "Next", "Later")}
        return page(request, a, "plan.html", result=result, groups=groups)

    def download(buf: io.BytesIO, media_type: str, name: str) -> StreamingResponse:
        buf.seek(0)
        return StreamingResponse(buf, media_type=media_type,
                                 headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @router.get("/a/{assessment_id}/report.docx")
    def report(a: Assessment = Depends(assessment), s: Session = Depends(session)):
        result, answers, evidence = results(a)
        buf = io.BytesIO()
        build_report(engine, result, answers, evidence, a.organisation.name,
                     progress=progress_for(s, a, result)).save(buf)
        return download(buf, DOCX, f"csf-findings-{a.id}.docx")

    @router.get("/a/{assessment_id}/workbook.xlsx")
    def workbook(a: Assessment = Depends(assessment), s: Session = Depends(session)):
        result, answers, evidence = results(a)
        buf = io.BytesIO()
        build_workbook(engine, result, answers, evidence, a.organisation.name,
                       progress=progress_for(s, a, result)).save(buf)
        return download(buf, XLSX, f"csf-assessment-{a.id}.xlsx")

    return router


def install(app, engine: Engine, db: SAEngine, token_hash) -> None:
    from fastapi.staticfiles import StaticFiles

    templates = Jinja2Templates(directory=str(HERE / "templates"))

    @app.exception_handler(NotAllowed)
    async def not_allowed(request: Request, exc: NotAllowed):
        return templates.TemplateResponse(request, "missing.html", {}, status_code=404)

    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
    app.include_router(build_router(engine, db, token_hash))
