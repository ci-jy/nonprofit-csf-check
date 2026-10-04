from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from csfcheck.catalog import default_catalog
from csfcheck.db import Assessment, catalog_from_db, load_core, make_engine, upgrade_schema


def test_loader_imports_all_subcategories_into_postgres(database_url):
    db = make_engine(database_url)
    try:
        counts = load_core(db)
        assert counts == {"functions": 6, "categories": 22, "subcategories": 106, "implementation examples": 363}
        assert load_core(db) == counts  # reload is a no-op
        with db.connect() as conn:
            assert conn.dialect.name in {"postgresql"}
            sha = conn.execute(text("select sha256 from csf_source")).scalar_one()
            assert sha == default_catalog().sha256
            n = conn.execute(text(
                "select count(*) from csf_subcategory s join csf_category c on c.id = s.category_id "
                "where c.function_id = 'GV'"
            )).scalar_one()
            assert n == 31
        from_db = catalog_from_db(db)
        assert from_db.subcategories == default_catalog().subcategories
    finally:
        db.dispose()


def test_upgrade_adds_version_columns_to_an_older_database(database_url):
    """A database made before versioning gets the new assessment columns in place."""
    db = make_engine(database_url)
    legacy = create_engine(db.url, connect_args={"options": "-csearch_path=legacy"})
    try:
        with db.begin() as conn:
            conn.execute(text("drop schema if exists legacy cascade; create schema legacy"))
            conn.execute(text(
                "create table legacy.organisation (id serial primary key, name varchar(200), profile json);"
                "create table legacy.assessment (id serial primary key, "
                "organisation_id integer references legacy.organisation(id), token_hash varchar(64));"
                "insert into legacy.organisation (name, profile) values ('Old', '{\"has_office\": true}');"
                "insert into legacy.assessment (organisation_id, token_hash) values (1, 'x')"
            ))
        upgrade_schema(legacy)
        upgrade_schema(legacy)  # running it twice is harmless
        with Session(legacy) as s:
            a = s.get(Assessment, 1)
            assert a.version == 1 and a.previous_id is None and a.profile is None
            assert a.effective_profile == {"has_office": True}
    finally:
        with db.begin() as conn:
            conn.execute(text("drop schema if exists legacy cascade"))
        legacy.dispose()
        db.dispose()
