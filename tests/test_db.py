from sqlalchemy import text

from csfcheck.catalog import default_catalog
from csfcheck.db import catalog_from_db, load_core, make_engine


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
