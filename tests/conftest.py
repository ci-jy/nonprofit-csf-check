import os
from pathlib import Path

import pytest

from csfcheck.devdb import find_pg_bin, temporary_postgres
from csfcheck.engine import Engine

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = sorted((ROOT / "samples").glob("*.json"))


@pytest.fixture(scope="session")
def engine() -> Engine:
    return Engine.default()


@pytest.fixture(scope="session")
def database_url():
    """PostgreSQL for the API and loader tests.

    Uses CSFCHECK_TEST_DATABASE_URL when set, otherwise starts a throwaway
    cluster from the local PostgreSQL binaries.
    """
    url = os.environ.get("CSFCHECK_TEST_DATABASE_URL")
    if url:
        yield url
        return
    if find_pg_bin() is None:
        pytest.fail("PostgreSQL binaries not found; install postgresql or set CSFCHECK_TEST_DATABASE_URL")
    with temporary_postgres(port=25433) as url:
        yield url
