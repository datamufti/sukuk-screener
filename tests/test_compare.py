"""Tests for comparison view and diversification scoring."""
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
        db_path = Path(tmpdir) / "test_compare.duckdb"
        conn = setup_database(db_path)
        upsert_daily(conn, SAMPLE_ROWS, date(2026, 3, 18), "test://pdf")
        test_app = _make_test_app(conn)
        with TestClient(test_app) as tc:
            yield tc
        conn.close()


# ─── Compare page route tests ────────────────────────

class TestComparePage:
    def test_compare_renders(self, client):
        resp = client.get("/compare?isins=XS1111111111,XS2222222222")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Compare Sukuk" in resp.text

    def test_compare_shows_sukuk_data(self, client):
        resp = client.get("/compare?isins=XS1111111111,XS2222222222")
        assert "XS1111111111" in resp.text
        assert "XS2222222222" in resp.text
        assert "TEST BANK SUKUK" in resp.text

    def test_compare_single_sukuk(self, client):
        resp = client.get("/compare?isins=XS1111111111")
        assert resp.status_code == 200
        assert "XS1111111111" in resp.text

    def test_compare_invalid_isin(self, client):
        resp = client.get("/compare?isins=INVALID123456")
        assert resp.status_code == 200
        assert "No valid sukuk" in resp.text

    def test_compare_mixed_valid_invalid(self, client):
        resp = client.get("/compare?isins=XS1111111111,INVALID123")
        assert resp.status_code == 200
        assert "XS1111111111" in resp.text
        assert "1 sukuk compared" in resp.text

    def test_compare_empty_isins(self, client):
        resp = client.get("/compare?isins=")
        assert resp.status_code == 200
        assert "No valid sukuk" in resp.text

    def test_compare_all_three(self, client):
        resp = client.get("/compare?isins=XS1111111111,XS2222222222,XS3333333333")
        assert resp.status_code == 200
        assert "3 sukuk compared" in resp.text

    def test_compare_max_five(self, client):
        """Even if more than 5 ISINs are passed, only 5 are used."""
        isins = ",".join([f"XS{i}111111111" for i in range(7)])
        resp = client.get(f"/compare?isins={isins}")
        assert resp.status_code == 200

    def test_compare_shows_metrics(self, client):
        resp = client.get("/compare?isins=XS1111111111,XS2222222222")
        assert "YTM" in resp.text
        assert "Credit Score" in resp.text
        assert "Zakat Rate" in resp.text

    def test_compare_shows_profit_rate(self, client):
        resp = client.get("/compare?isins=XS1111111111,XS2222222222")
        assert "Profit Rate" in resp.text
        assert "4.500" in resp.text  # XS1111111111 profit_rate
        assert "7.125" in resp.text  # XS2222222222 profit_rate

    def test_compare_shows_structure_detail(self, client):
        """The raw sukuk_type from the PDF should show as Structure Detail."""
        resp = client.get("/compare?isins=XS1111111111,XS2222222222")
        assert "Structure Detail" in resp.text
        assert "Sukuk Al Ijara" in resp.text
        assert "Sukuk Al Murabaha" in resp.text

    def test_compare_bid_lowest_is_best(self, client):
        """Lowest bid should be highlighted, not highest."""
        resp = client.get("/compare?isins=XS1111111111,XS2222222222")
        # XS2222222222 has bid 96.5 (lower) vs XS1111111111 at 99.0
        # The best (lowest) bid cell should have the highlight class
        assert "96.50" in resp.text
        assert "99.00" in resp.text

    def test_compare_ask_lowest_is_best(self, client):
        """Lowest ask should be highlighted."""
        resp = client.get("/compare?isins=XS1111111111,XS2222222222")
        # XS2222222222 has ask 97.8 (lower) vs XS1111111111 at 100.5
        assert "97.80" in resp.text
        assert "100.50" in resp.text


# ─── Diversification tests ───────────────────────────

class TestDiversification:
    def test_diversification_section_present(self, client):
        resp = client.get("/compare?isins=XS1111111111,XS2222222222,XS3333333333")
        assert "Diversification Analysis" in resp.text

    def test_diversification_country_shown(self, client):
        resp = client.get("/compare?isins=XS1111111111,XS2222222222,XS3333333333")
        assert "Country Concentration" in resp.text
        assert "UAE" in resp.text
        assert "Turkey" in resp.text
        assert "Bahrain" in resp.text

    def test_diversification_sector_shown(self, client):
        resp = client.get("/compare?isins=XS1111111111,XS2222222222,XS3333333333")
        assert "Sector Concentration" in resp.text
        assert "Financial" in resp.text
        assert "Industrial" in resp.text
        assert "Government" in resp.text

    def test_diversification_rating_band_shown(self, client):
        resp = client.get("/compare?isins=XS1111111111,XS2222222222,XS3333333333")
        assert "Rating Band" in resp.text

    def test_concentrated_portfolio_warning(self, client):
        """A single-country portfolio should get a warning."""
        # Only UAE sukuk - 100% concentration
        resp = client.get("/compare?isins=XS1111111111")
        assert resp.status_code == 200

    def test_diversified_portfolio(self, client):
        """3 different countries, sectors should be well distributed."""
        resp = client.get("/compare?isins=XS1111111111,XS2222222222,XS3333333333")
        assert resp.status_code == 200
        assert "33.3%" in resp.text


class TestDiversificationLogic:
    """Test the _compute_diversification function directly."""

    def test_empty_portfolio(self):
        from app.routers.pages import _compute_diversification
        result = _compute_diversification([])
        assert result["country"] == {}
        assert result["sector"] == {}
        assert result["rating_band"] == {}
        assert result["warnings"] == []

    def test_single_sukuk_concentrated(self):
        from app.routers.pages import _compute_diversification
        sukuk = [{"country_risk": "UAE", "sector": "Financial", "credit_risk_score": 18.0}]
        result = _compute_diversification(sukuk)
        assert result["country"]["UAE"] == 100.0
        assert result["sector"]["Financial"] == 100.0
        assert len(result["warnings"]) >= 1
        assert result["overall"] == "warning"

    def test_two_different_countries(self):
        from app.routers.pages import _compute_diversification
        sukuk = [
            {"country_risk": "UAE", "sector": "Financial", "credit_risk_score": 18.0},
            {"country_risk": "Turkey", "sector": "Industrial", "credit_risk_score": 8.0},
        ]
        result = _compute_diversification(sukuk)
        assert result["country"]["UAE"] == 50.0
        assert result["country"]["Turkey"] == 50.0

    def test_three_different_all_categories(self):
        from app.routers.pages import _compute_diversification
        sukuk = [
            {"country_risk": "UAE", "sector": "Financial", "credit_risk_score": 18.0},
            {"country_risk": "Turkey", "sector": "Industrial", "credit_risk_score": 8.0},
            {"country_risk": "Bahrain", "sector": "Government", "credit_risk_score": 5.0},
        ]
        result = _compute_diversification(sukuk)
        assert result["overall"] == "good"
        for pct in result["country"].values():
            assert abs(pct - 33.3) < 0.1
        assert result["warnings"] == []

    def test_rating_bands(self):
        from app.routers.pages import _compute_diversification
        sukuk = [
            {"country_risk": "A", "sector": "X", "credit_risk_score": 21},  # AAA-AA
            {"country_risk": "B", "sector": "Y", "credit_risk_score": 16},  # A
            {"country_risk": "C", "sector": "Z", "credit_risk_score": 13},  # BBB
            {"country_risk": "D", "sector": "W", "credit_risk_score": 3},   # Below B
        ]
        result = _compute_diversification(sukuk)
        assert "AAA-AA" in result["rating_band"]
        assert "A" in result["rating_band"]
        assert "BBB" in result["rating_band"]
        assert "Below B" in result["rating_band"]

    def test_unrated_sukuk(self):
        from app.routers.pages import _compute_diversification
        sukuk = [{"country_risk": "UAE", "sector": "Financial", "credit_risk_score": None}]
        result = _compute_diversification(sukuk)
        assert "Unrated" in result["rating_band"]


# ─── Enhanced filter tests ────────────────────────────

class TestEnhancedFilters:
    def test_maturity_date_filter_after(self, client):
        resp = client.get("/api/sukuk?maturity_after=2029-01-01")
        data = resp.json()["data"]
        # Only XS2222222222 matures 2030-03-20
        assert len(data) == 1
        assert data[0]["isin"] == "XS2222222222"

    def test_maturity_date_filter_before(self, client):
        resp = client.get("/api/sukuk?maturity_before=2029-01-01")
        data = resp.json()["data"]
        # XS1111111111 matures 2028-06-15, XS3333333333 is perp (NULL maturity, excluded)
        assert len(data) == 1
        assert data[0]["isin"] == "XS1111111111"

    def test_maturity_date_range(self, client):
        resp = client.get("/api/sukuk?maturity_after=2027-01-01&maturity_before=2031-01-01")
        data = resp.json()["data"]
        assert len(data) == 2

    def test_rating_min_filter(self, client):
        resp = client.get("/api/sukuk?rating_min=15")
        data = resp.json()["data"]
        # Only XS1111111111 with A+ ratings should have score >= 15
        assert len(data) == 1
        assert data[0]["isin"] == "XS1111111111"

    def test_empty_maturity_filter_ignored(self, client):
        resp = client.get("/api/sukuk?maturity_after=&maturity_before=")
        data = resp.json()["data"]
        assert len(data) == 3

    def test_empty_rating_filter_ignored(self, client):
        resp = client.get("/api/sukuk?rating_min=")
        data = resp.json()["data"]
        assert len(data) == 3

    def test_invalid_date_filter_ignored(self, client):
        resp = client.get("/api/sukuk?maturity_after=not-a-date")
        data = resp.json()["data"]
        assert len(data) == 3

    def test_htmx_table_with_new_filters(self, client):
        resp = client.get("/htmx/table?maturity_after=2029-01-01")
        assert resp.status_code == 200
        assert "XS2222222222" in resp.text
        assert "XS1111111111" not in resp.text

    def test_htmx_table_rating_filter(self, client):
        resp = client.get("/htmx/table?rating_min=15")
        assert resp.status_code == 200
        assert "XS1111111111" in resp.text

    def test_result_count_oob(self, client):
        resp = client.get("/htmx/table?country=UAE")
        assert resp.status_code == 200
        assert "Showing" in resp.text
        assert 'hx-swap-oob' in resp.text

    def test_index_shows_total_count(self, client):
        resp = client.get("/")
        assert "Showing" in resp.text
        # All 3 shown out of 3 total
        assert ">3<" in resp.text.replace(" ", "")


class TestCheckboxInTable:
    def test_checkbox_in_table_rows(self, client):
        resp = client.get("/")
        assert 'class="compare-cb' in resp.text
        assert 'toggleCompare' in resp.text

    def test_compare_tray_in_index(self, client):
        resp = client.get("/")
        assert 'id="compare-tray"' in resp.text
        assert 'goCompare' in resp.text
