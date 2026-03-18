"""Tests for FastAPI endpoints (API + page routes)."""
import pytest
import tempfile
from pathlib import Path
from datetime import date
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import setup_database
from app.services.db_ops import upsert_daily


def _make_test_app(conn):
    """Build a fresh FastAPI app wired to the given DB connection (no lifespan)."""
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


@pytest.fixture
def client():
    """Create a test client with a temp database pre-loaded with sample data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_api.duckdb"
        conn = setup_database(db_path)

        # Insert sample data
        sample_rows = [
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
            {
                "isin": "XS2222222222",
                "issuer": "TURKISH CORP SUKUK",
                "profit_rate": 7.125,
                "profit_type": "FIXED",
                "bid_price": 96.5,
                "ask_price": 97.8,
                "ytm": 8.1,
                "maturity": date(2030, 3, 20),
                "maturity_type": "AT MATURITY",
                "ccy": "USD",
                "sp_rating": "BB-",
                "moodys_rating": None,
                "fitch_rating": "BB-",
                "min_investment": 200000,
                "country_risk": "Turkey",
                "sector": "Industrial",
                "sukuk_type": "Sukuk Al Murabaha",
            },
            {
                "isin": "XS3333333333",
                "issuer": "BAHRAIN GOV SUKUK",
                "profit_rate": 6.0,
                "profit_type": "VARIABLE",
                "bid_price": 98.0,
                "ask_price": 99.0,
                "ytm": 6.5,
                "maturity": None,
                "maturity_type": "PERP/CALL",
                "ccy": "USD",
                "sp_rating": "B+",
                "moodys_rating": "B1",
                "fitch_rating": None,
                "min_investment": 200000,
                "country_risk": "Bahrain",
                "sector": "Government",
                "sukuk_type": "Sukuk Al Wakala",
            },
        ]
        doc_date = date(2026, 3, 18)
        upsert_daily(conn, sample_rows, doc_date, "test://pdf")

        test_app = _make_test_app(conn)
        with TestClient(test_app) as tc:
            yield tc
        conn.close()


# ─── API JSON endpoints ────────────────────────────────

class TestAPIListSukuk:
    def test_list_returns_json(self, client):
        resp = client.get("/api/sukuk")
        assert resp.status_code == 200
        body = resp.json()
        assert "count" in body
        assert "data" in body
        assert body["count"] == 3

    def test_list_sorted_by_ytm_desc(self, client):
        resp = client.get("/api/sukuk?sort_by=ytm&sort_dir=DESC")
        data = resp.json()["data"]
        ytms = [r["ytm"] for r in data if r["ytm"] is not None]
        assert ytms == sorted(ytms, reverse=True)

    def test_filter_by_country(self, client):
        resp = client.get("/api/sukuk?country=UAE")
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["country_risk"] == "UAE"

    def test_filter_by_ytm_range(self, client):
        resp = client.get("/api/sukuk?ytm_min=6&ytm_max=9")
        data = resp.json()["data"]
        assert len(data) == 2  # Turkey 8.1 and Bahrain 6.5
        for r in data:
            assert 6 <= r["ytm"] <= 9

    def test_search_by_issuer(self, client):
        resp = client.get("/api/sukuk?search=TURKISH")
        data = resp.json()["data"]
        assert len(data) == 1
        assert "TURKISH" in data[0]["issuer"]

    def test_search_by_isin(self, client):
        resp = client.get("/api/sukuk?search=XS1111")
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["isin"] == "XS1111111111"


class TestAPIDetail:
    def test_detail_found(self, client):
        resp = client.get("/api/sukuk/XS1111111111")
        assert resp.status_code == 200
        body = resp.json()
        assert body["isin"] == "XS1111111111"
        assert body["issuer"] == "TEST BANK SUKUK"
        assert "zakat_adjusted_ytm" in body

    def test_detail_not_found(self, client):
        resp = client.get("/api/sukuk/XS0000000000")
        body = resp.json()
        assert "error" in body


class TestAPIHistory:
    def test_history_returns_data(self, client):
        resp = client.get("/api/sukuk/XS1111111111/history")
        assert resp.status_code == 200
        body = resp.json()
        assert body["isin"] == "XS1111111111"
        assert isinstance(body["data"], list)


class TestAPIFilters:
    def test_filters_populated(self, client):
        resp = client.get("/api/filters")
        assert resp.status_code == 200
        body = resp.json()
        assert "UAE" in body["countries"]
        assert "Turkey" in body["countries"]
        assert len(body["sectors"]) >= 2
        assert "USD" in body["currencies"]

    def test_sukuk_types_in_filters(self, client):
        resp = client.get("/api/filters")
        body = resp.json()
        assert len(body["sukuk_types"]) >= 2


class TestAPIDates:
    def test_latest_date(self, client):
        resp = client.get("/api/latest-date")
        assert resp.status_code == 200
        assert resp.json()["latest_date"] == "2026-03-18"

    def test_available_dates(self, client):
        resp = client.get("/api/dates")
        assert resp.status_code == 200
        assert "2026-03-18" in resp.json()["dates"]


class TestAPIIngestionLog:
    def test_ingestion_log(self, client):
        resp = client.get("/api/ingestion-log")
        assert resp.status_code == 200
        log = resp.json()["log"]
        assert len(log) >= 1


# ─── HTML page routes ──────────────────────────────────

class TestPageRoutes:
    def test_index_page_renders(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Sukuk Screener" in resp.text
        assert "XS1111111111" in resp.text

    def test_index_shows_all_sukuk(self, client):
        resp = client.get("/")
        assert "XS1111111111" in resp.text
        assert "XS2222222222" in resp.text
        assert "XS3333333333" in resp.text

    def test_detail_page_renders(self, client):
        resp = client.get("/sukuk/XS1111111111")
        assert resp.status_code == 200
        assert "TEST BANK SUKUK" in resp.text

    def test_detail_page_not_found(self, client):
        resp = client.get("/sukuk/XS0000000000")
        assert resp.status_code == 200
        assert "not found" in resp.text.lower()

    def test_htmx_table_partial(self, client):
        resp = client.get("/htmx/table?sort_by=ytm&sort_dir=DESC")
        assert resp.status_code == 200
        # Should be a partial (table rows), not full page
        assert "<html" not in resp.text
        assert "XS1111111111" in resp.text or "XS2222222222" in resp.text
