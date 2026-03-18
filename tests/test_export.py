"""Tests for CSV export endpoint."""
import csv
import io
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


@pytest.fixture
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_export.duckdb"
        conn = setup_database(db_path)
        upsert_daily(conn, SAMPLE_ROWS, date(2026, 3, 18), "test://pdf")
        test_app = _make_test_app(conn)
        with TestClient(test_app) as tc:
            yield tc
        conn.close()


class TestCSVExport:
    def test_csv_returns_200(self, client):
        resp = client.get("/api/export/csv")
        assert resp.status_code == 200

    def test_csv_content_type(self, client):
        resp = client.get("/api/export/csv")
        assert "text/csv" in resp.headers["content-type"]

    def test_csv_content_disposition(self, client):
        resp = client.get("/api/export/csv")
        cd = resp.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert "sukuk_export_" in cd
        assert ".csv" in cd

    def test_csv_has_headers(self, client):
        resp = client.get("/api/export/csv")
        reader = csv.reader(io.StringIO(resp.text))
        headers = next(reader)
        assert "ISIN" in headers
        assert "Issuer" in headers
        assert "YTM" in headers
        assert "Country" in headers

    def test_csv_has_data_rows(self, client):
        resp = client.get("/api/export/csv")
        reader = csv.reader(io.StringIO(resp.text))
        rows = list(reader)
        # Header + 3 data rows
        assert len(rows) == 4

    def test_csv_contains_isin(self, client):
        resp = client.get("/api/export/csv")
        assert "XS1111111111" in resp.text
        assert "XS2222222222" in resp.text

    def test_csv_respects_country_filter(self, client):
        resp = client.get("/api/export/csv?country=UAE")
        reader = csv.reader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 2  # Header + 1 UAE row
        assert "XS1111111111" in rows[1][0]

    def test_csv_respects_ytm_filter(self, client):
        resp = client.get("/api/export/csv?ytm_min=6&ytm_max=9")
        reader = csv.reader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 3  # Header + 2 rows (Turkey + Bahrain)

    def test_csv_column_count(self, client):
        resp = client.get("/api/export/csv")
        reader = csv.reader(io.StringIO(resp.text))
        headers = next(reader)
        data_row = next(reader)
        assert len(headers) == len(data_row)
        assert len(headers) == 19  # 19 columns defined in CSV_COLUMNS
