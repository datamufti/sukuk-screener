"""Tests for screener presets CRUD."""
import json
import pytest
import tempfile
from pathlib import Path
from datetime import date
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import setup_database
from app.services.db_ops import (
    upsert_daily,
    list_presets,
    create_preset,
    delete_preset,
)


def _make_test_app(conn):
    from app.config import STATIC_DIR
    from fastapi.staticfiles import StaticFiles
    from app.routers import pages, api

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    test_app = FastAPI(lifespan=noop_lifespan)
    test_app.state.db = conn
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    test_app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    test_app.include_router(pages.router)
    test_app.include_router(api.router, prefix="/api")
    return test_app


SAMPLE_ROWS = [
    {
        "isin": "XS1111111111",
        "issuer": "TEST BANK SUKUK",
        "profit_rate": 4.5,
        "profit_type": "FIXED",
        "bid_price": 99.0,
        "ask_price": 100.5,
        "ytm": 5.2,
        "maturity": date(2028, 6, 15),
        "maturity_type": "AT MATURITY",
        "ccy": "USD",
        "sp_rating": "A+",
        "moodys_rating": "A1",
        "fitch_rating": "A+",
        "min_investment": 200000,
        "country_risk": "UAE",
        "sector": "Financial",
        "sukuk_type": "Sukuk Al Ijara",
    },
]


@pytest.fixture
def db_conn():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_presets.duckdb"
        conn = setup_database(db_path)
        upsert_daily(conn, SAMPLE_ROWS, date(2026, 3, 18), "test://pdf")
        yield conn
        conn.close()


@pytest.fixture
def client(db_conn):
    test_app = _make_test_app(db_conn)
    with TestClient(test_app) as tc:
        yield tc


# ─── DB-level preset tests ───────────────────────────

class TestPresetDBOps:
    def test_list_presets_empty(self, db_conn):
        presets = list_presets(db_conn)
        assert presets == []

    def test_create_preset(self, db_conn):
        filters = json.dumps({"country": "UAE", "ytm_min": "5"})
        preset = create_preset(db_conn, "UAE High Yield", filters)
        assert preset["name"] == "UAE High Yield"
        assert preset["filters"]["country"] == "UAE"
        assert preset["id"] is not None

    def test_list_presets_after_create(self, db_conn):
        create_preset(db_conn, "Preset A", json.dumps({"country": "UAE"}))
        create_preset(db_conn, "Preset B", json.dumps({"sector": "Financial"}))
        presets = list_presets(db_conn)
        assert len(presets) == 2
        names = {p["name"] for p in presets}
        assert "Preset A" in names
        assert "Preset B" in names

    def test_delete_preset(self, db_conn):
        preset = create_preset(db_conn, "To Delete", json.dumps({}))
        assert delete_preset(db_conn, preset["id"]) is True
        assert list_presets(db_conn) == []

    def test_delete_nonexistent_preset(self, db_conn):
        assert delete_preset(db_conn, 99999) is False

    def test_create_preset_with_empty_filters(self, db_conn):
        preset = create_preset(db_conn, "Empty", json.dumps({}))
        assert preset["filters"] == {}

    def test_preset_filters_json_parsed(self, db_conn):
        filters = {"country": "UAE", "ytm_min": "3.5", "search": "test"}
        create_preset(db_conn, "Complex", json.dumps(filters))
        presets = list_presets(db_conn)
        assert presets[0]["filters"]["country"] == "UAE"
        assert presets[0]["filters"]["ytm_min"] == "3.5"


# ─── API-level preset tests ──────────────────────────

class TestPresetAPI:
    def test_list_presets_api(self, client):
        resp = client.get("/api/presets")
        assert resp.status_code == 200
        assert "presets" in resp.json()
        assert resp.json()["presets"] == []

    def test_create_preset_api(self, client):
        resp = client.post("/api/presets?name=My+Filter&filters=%7B%22country%22%3A+%22UAE%22%7D")
        assert resp.status_code == 200
        body = resp.json()
        assert "preset" in body
        assert body["preset"]["name"] == "My Filter"

    def test_create_and_list_preset_api(self, client):
        client.post("/api/presets?name=Test&filters=%7B%7D")
        resp = client.get("/api/presets")
        presets = resp.json()["presets"]
        assert len(presets) == 1
        assert presets[0]["name"] == "Test"

    def test_delete_preset_api(self, client):
        create_resp = client.post("/api/presets?name=ToDelete&filters=%7B%7D")
        preset_id = create_resp.json()["preset"]["id"]
        del_resp = client.delete(f"/api/presets/{preset_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["deleted"] is True

    def test_delete_nonexistent_preset_api(self, client):
        resp = client.delete("/api/presets/99999")
        assert "error" in resp.json()

    def test_presets_shown_on_index(self, client):
        client.post("/api/presets?name=UAE+Only&filters=%7B%22country%22%3A+%22UAE%22%7D")
        resp = client.get("/")
        assert "UAE Only" in resp.text
