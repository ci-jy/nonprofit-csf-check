"""PostgreSQL storage: the CSF core reference tables and assessment state."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, create_engine, delete, func, select, text
from sqlalchemy.engine import Engine as SAEngine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from .catalog import Catalog, Category, Example, Function, Subcategory, load_export


class Base(DeclarativeBase):
    pass


class CsfSource(Base):
    __tablename__ = "csf_source"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document: Mapped[str] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(40))
    sha256: Mapped[str] = mapped_column(String(64))


class CsfFunction(Base):
    __tablename__ = "csf_function"
    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    title: Mapped[str] = mapped_column(String(40))
    text: Mapped[str] = mapped_column(Text)


class CsfCategory(Base):
    __tablename__ = "csf_category"
    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    function_id: Mapped[str] = mapped_column(ForeignKey("csf_function.id"))
    title: Mapped[str] = mapped_column(String(120))
    text: Mapped[str] = mapped_column(Text)


class CsfSubcategory(Base):
    __tablename__ = "csf_subcategory"
    id: Mapped[str] = mapped_column(String(12), primary_key=True)
    category_id: Mapped[str] = mapped_column(ForeignKey("csf_category.id"))
    text: Mapped[str] = mapped_column(Text)


class CsfExample(Base):
    __tablename__ = "csf_implementation_example"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    subcategory_id: Mapped[str] = mapped_column(ForeignKey("csf_subcategory.id"), index=True)
    label: Mapped[str] = mapped_column(String(10))
    text: Mapped[str] = mapped_column(Text)


class Organisation(Base):
    __tablename__ = "organisation"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    profile: Mapped[dict] = mapped_column(JSON)
    assessments: Mapped[list["Assessment"]] = relationship(back_populates="organisation")


class Assessment(Base):
    """One version of an organisation's assessment.

    A retake is a new row with the next version number, a link to the version
    it was retaken from and the same token hash, so one resume code opens the
    organisation's whole history. The profile is kept per version because an
    organisation can change between assessments (start taking card payments,
    let staff work from home).
    """

    __tablename__ = "assessment"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisation.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    previous_id: Mapped[int | None] = mapped_column(ForeignKey("assessment.id"), nullable=True)
    profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    organisation: Mapped[Organisation] = relationship(back_populates="assessments")
    answers: Mapped[list["AnswerRow"]] = relationship(cascade="all, delete-orphan")

    @property
    def effective_profile(self) -> dict:
        """This version's profile; rows from before versioning fall back to the organisation's."""
        return self.profile if self.profile is not None else self.organisation.profile

    def answer_state(self) -> tuple[dict, dict[str, str], dict[str, str]]:
        """(profile, answers, evidence) as the engine wants them."""
        answers = {r.question_id: r.value for r in self.answers}
        evidence = {r.question_id: r.evidence for r in self.answers if r.evidence}
        return self.effective_profile, answers, evidence


class AnswerRow(Base):
    __tablename__ = "answer"
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessment.id"), primary_key=True)
    question_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(String(40))
    evidence: Mapped[str] = mapped_column(Text, default="")


def store_answers(engine, a: Assessment, incoming: dict[str, tuple[str, str | None]]) -> int:
    """Save answers (value, evidence) on an assessment and drop unreachable ones.

    ``engine`` is the scoring engine. An evidence of ``None`` keeps whatever
    was stored before. Lowering an answer can make earlier follow-up answers
    unreachable; those are removed so the stored state never holds a skipped
    question. Returns the number of answers now stored.
    """
    existing = {r.question_id: r for r in a.answers}
    for qid, (value, evidence) in incoming.items():
        row = existing.get(qid)
        if row is None:
            a.answers.append(AnswerRow(question_id=qid, value=value, evidence=evidence or ""))
        else:
            row.value = value
            if evidence is not None:
                row.evidence = evidence
    merged = {r.question_id: r.value for r in a.answers}
    status = engine.question_status(a.effective_profile, merged)
    for r in list(a.answers):
        if status[r.question_id] != "asked":
            a.answers.remove(r)
    return len(a.answers)


def versions(s: Session, a: Assessment) -> list[Assessment]:
    """Every version of ``a``'s organisation that the same token opens, oldest first."""
    return list(s.scalars(
        select(Assessment)
        .where(Assessment.organisation_id == a.organisation_id, Assessment.token_hash == a.token_hash)
        .order_by(Assessment.version)
    ))


def retake(engine, s: Session, a: Assessment, profile: dict | None = None, copy_answers: bool = True) -> Assessment:
    """Start the next version of an assessment.

    ``engine`` is the scoring engine. The new version keeps the token, takes
    ``profile`` if given (otherwise this version's) and starts from a copy of
    the answers and evidence, so people only change what has changed. Answers
    the new profile no longer asks are dropped.
    """
    profile = engine.bank.normalise_profile(profile if profile is not None else a.effective_profile)
    latest = max(v.version for v in versions(s, a))
    new = Assessment(organisation_id=a.organisation_id, token_hash=a.token_hash, version=latest + 1,
                     previous_id=a.id, profile=profile)
    new.organisation = a.organisation
    s.add(new)
    a.organisation.profile = profile
    if copy_answers:
        store_answers(engine, new, {r.question_id: (r.value, r.evidence) for r in a.answers})
    return new


# Columns added after the first release; create_all() does not alter tables
# that already exist, so an older database gets them here.
UPGRADES = (
    "ALTER TABLE assessment ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE assessment ADD COLUMN IF NOT EXISTS previous_id INTEGER REFERENCES assessment(id)",
    "ALTER TABLE assessment ADD COLUMN IF NOT EXISTS profile JSON",
    "ALTER TABLE assessment ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
)


def upgrade_schema(engine: SAEngine) -> None:
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for statement in UPGRADES:
            conn.execute(text(statement))


def make_engine(url: str) -> SAEngine:
    return create_engine(url, pool_pre_ping=True)


def load_core(engine: SAEngine, catalog: Catalog | None = None) -> dict[str, int]:
    """Create the schema and (re)load the CSF core from the vendored export.

    The export's checksum is verified before anything is written, and the
    reference tables are replaced in one transaction, so a reload is safe.
    """
    catalog = catalog or load_export()
    upgrade_schema(engine)
    with Session(engine) as s, s.begin():
        current = s.get(CsfSource, 1)
        if current and current.sha256 == catalog.sha256:
            n = s.query(CsfSubcategory).count()
            if n == len(catalog.subcategories):
                return _counts(s)
        for table in (CsfExample, CsfSubcategory, CsfCategory, CsfFunction, CsfSource):
            s.execute(delete(table))
        s.flush()
        s.add(CsfSource(id=1, document=catalog.document, version=catalog.version, sha256=catalog.sha256))
        s.add_all(CsfFunction(id=f.id, title=f.title, text=f.text) for f in catalog.functions.values())
        s.flush()
        s.add_all(
            CsfCategory(id=c.id, function_id=c.function_id, title=c.title, text=c.text)
            for c in catalog.categories.values()
        )
        s.flush()
        s.add_all(
            CsfSubcategory(id=x.id, category_id=x.category_id, text=x.text)
            for x in catalog.subcategories.values()
        )
        s.flush()
        s.add_all(
            CsfExample(id=e.id, subcategory_id=x.id, label=e.label, text=e.text)
            for x in catalog.subcategories.values()
            for e in x.examples
        )
        s.flush()
        return _counts(s)


def _counts(s: Session) -> dict[str, int]:
    return {
        "functions": s.query(CsfFunction).count(),
        "categories": s.query(CsfCategory).count(),
        "subcategories": s.query(CsfSubcategory).count(),
        "implementation examples": s.query(CsfExample).count(),
    }


def catalog_from_db(engine: SAEngine) -> Catalog:
    """Rebuild the in-memory catalog from the reference tables."""
    with Session(engine) as s:
        src = s.get(CsfSource, 1)
        if src is None:
            raise RuntimeError("CSF core not loaded; run `python -m csfcheck load-csf`")
        cat = Catalog(document=src.document, version=src.version, sha256=src.sha256)
        for f in s.scalars(select(CsfFunction)):
            cat.functions[f.id] = Function(f.id, f.title, f.text)
        for c in s.scalars(select(CsfCategory)):
            cat.categories[c.id] = Category(c.id, c.function_id, c.title, c.text)
        examples: dict[str, list[Example]] = {}
        for e in s.scalars(select(CsfExample).order_by(CsfExample.id)):
            examples.setdefault(e.subcategory_id, []).append(Example(e.id, e.label, e.text))
        for x in s.scalars(select(CsfSubcategory).order_by(CsfSubcategory.id)):
            cat.subcategories[x.id] = Subcategory(x.id, x.category_id, x.text, tuple(examples.get(x.id, [])))
    return cat
