import os

import pytest
from fastapi.testclient import TestClient

from shortlist_api.db import check_db
from shortlist_api.main import app, get_db_check


def _client(db_up: bool) -> TestClient:
    app.dependency_overrides[get_db_check] = lambda: lambda: db_up
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_health_db_up() -> None:
    assert _client(True).get("/health").json() == {"status": "ok", "db": "ok"}


def test_health_db_down() -> None:
    r = _client(False).get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "unavailable"}


@pytest.mark.db
def test_check_db_against_real_postgres() -> None:
    if not os.environ.get("RUN_DB_TESTS"):
        pytest.skip("set RUN_DB_TESTS=1 with Postgres running")
    assert check_db() is True
