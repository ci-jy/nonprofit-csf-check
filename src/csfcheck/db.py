"""PostgreSQL storage: the CSF core reference tables and assessment state."""

from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, create_engine, delete, select
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
    __tablename__ = "assessment"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisation.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    organisation: Mapped[Organisation] = relationship(back_populates="assessments")
    answers: Mapped[list["AnswerRow"]] = relationship(cascade="all, delete-orphan")


class AnswerRow(Base):
    __tablename__ = "answer"
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessment.id"), primary_key=True)
    question_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(String(40))
    evidence: Mapped[str] = mapped_column(Text, default="")


def make_engine(url: str) -> SAEngine:
    return create_engine(url, pool_pre_ping=True)


def load_core(engine: SAEngine, catalog: Catalog | None = None) -> dict[str, int]:
    """Create the schema and (re)load the CSF core from the vendored export.

    The export's checksum is verified before anything is written, and the
    reference tables are replaced in one transaction, so a reload is safe.
    """
    catalog = catalog or load_export()
    Base.metadata.create_all(engine)
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
