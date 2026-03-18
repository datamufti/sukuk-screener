"""Tests for database operations: schema, upsert, queries."""
import pytest
from datetime import date, datetime
from pathlib import Path
import tempfile

from app.database import setup_database
from app.services.db_ops import (
    upsert_daily,
    get_latest_date,
    get_sukuk_list,
    get_sukuk_detail,
    get_sukuk_history,
    get_filter_options,
    get_available_dates,
)

SAMPLE_ROWS = [
    {
        "isin": "XS1111111111",
        "issuer": "TEST SOVEREIGN",
        "profit_rate": 4.5,
        "profit_type": "FIXED",
        "bid_price": 99.50,
        "ask_price": 100.50,
        "ytm": 4.63,
        "maturity": date(2027, 3, 30),
        "maturity_type": "AT MATURITY",
        "ccy": "USD",
        "sp_rating": "A",
        "moodys_rating": "A2",
        "fitch_rating": "A",
        "min_investment": 200000,
        "country_risk": "UAE",
        "sector": "Government",
        "sukuk_type": "Sukuk Al Ijara",
    },
    {
        "isin": "XS2222222222",
        "issuer": "TEST BANK LTD",
        "profit_rate": 5.5,
        "profit_type": "FIXED",
        "bid_price": 98.00,
        "ask_price": 99.50,
        "ytm": 6.10,
        "maturity": date(2029, 6, 15),
        "maturity_type": "AT MATURITY",
        "ccy": "USD",
        "sp_rating": "BBB",
        "moodys_rating": None,
        "fitch_rating": "BBB",
        "min_investment": 200000,
        "country_risk": "Bahrain",
        "sector": "Financial",
        "sukuk_type": "Sukuk Al Murabaha",
    },
    {
        "isin": "XS3333333333",
        "issuer": "PERP ISSUER",
        "profit_rate": 7.0,
        "profit_type": "VARIABLE",
        "bid_price": 95.00,
        "ask_price": 97.00,
        "ytm": 8.50,
        "maturity": None,
        "maturity_type": "PERP/CALL",
        "ccy": "USD",
        "sp_rating": None,
        "moodys_rating": "Ba3",
        "fitch_rating": None,
        "min_investment": 200000,
        "country_risk": "Turkey",
        "sector": "Financial",
        "sukuk_type": "Sukuk Al Mudarabah",
    },
]


@pytest.fixture
def db_conn():
    """Create a temporary DuckDB for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        conn = setup_database(db_path)
        yield conn
        conn.close()


class TestSchemaCreation:
    def test_tables_exist(self, db_conn):
        tables = db_conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        assert "sukuk_daily" in table_names
        assert "sukuk_enriched" in table_names
        assert "sukuk_master" in table_names
        assert "screener_presets" in table_names
        assert "news_items" in table_names


class TestUpsertDaily:
    def test_insert_rows(self, db_conn):
        count = upsert_daily(db_conn, SAMPLE_ROWS, date(2026, 3, 18), "http://test.pdf")
        assert count == 3

        # Verify data in sukuk_daily
        rows = db_conn.execute("SELECT COUNT(*) FROM sukuk_daily").fetchone()
        assert rows[0] == 3

        # Verify enrichment was computed
        enriched = db_conn.execute("SELECT COUNT(*) FROM sukuk_enriched").fetchone()
        assert enriched[0] == 3

        # Verify master was updated
        master = db_conn.execute("SELECT COUNT(*) FROM sukuk_master").fetchone()
        assert master[0] == 3

    def test_idempotent_upsert(self, db_conn):
        """Upserting same date twice should not create duplicates."""
        upsert_daily(db_conn, SAMPLE_ROWS, date(2026, 3, 18), "http://test.pdf")
        upsert_daily(db_conn, SAMPLE_ROWS, date(2026, 3, 18), "http://test.pdf")

        count = db_conn.execute("SELECT COUNT(*) FROM sukuk_daily").fetchone()
        assert count[0] == 3  # Not 6

    def test_different_dates_accumulate(self, db_conn):
        upsert_daily(db_conn, SAMPLE_ROWS, date(2026, 3, 18), "http://test.pdf")
        upsert_daily(db_conn, SAMPLE_ROWS, date(2026, 3, 19), "http://test.pdf")

        count = db_conn.execute("SELECT COUNT(*) FROM sukuk_daily").fetchone()
        assert count[0] == 6

    def test_master_updated(self, db_conn):
        upsert_daily(db_conn, SAMPLE_ROWS, date(2026, 3, 18), "http://test.pdf")

        master = db_conn.execute(
            "SELECT isin, issuer, is_active FROM sukuk_master ORDER BY isin"
        ).fetchall()
        assert len(master) == 3
        assert all(m[2] for m in master)  # All active

    def test_enrichment_values(self, db_conn):
        upsert_daily(db_conn, SAMPLE_ROWS, date(2026, 3, 18), "http://test.pdf")

        # Check Ijara sukuk has 0% zakat
        ijara = db_conn.execute(
            "SELECT zakat_rate, sukuk_type_detected FROM sukuk_enriched WHERE isin = 'XS1111111111'"
        ).fetchone()
        assert ijara[0] == 0.0
        assert ijara[1] == "Ijara"

        # Check Murabaha sukuk has 2.5% zakat
        murabaha = db_conn.execute(
            "SELECT zakat_rate, sukuk_type_detected FROM sukuk_enriched WHERE isin = 'XS2222222222'"
        ).fetchone()
        assert murabaha[0] == 0.025
        assert murabaha[1] == "Murabaha"

        # Check Mudarabah sukuk detected as Partnership
        partnership = db_conn.execute(
            "SELECT zakat_rate, sukuk_type_detected FROM sukuk_enriched WHERE isin = 'XS3333333333'"
        ).fetchone()
        assert partnership[0] == 0.00625
        assert partnership[1] == "Partnership"


class TestQueries:
    @pytest.fixture(autouse=True)
    def seed_data(self, db_conn):
        upsert_daily(db_conn, SAMPLE_ROWS, date(2026, 3, 18), "http://test.pdf")

    def test_get_latest_date(self, db_conn):
        assert get_latest_date(db_conn) == date(2026, 3, 18)

    def test_get_available_dates(self, db_conn):
        dates = get_available_dates(db_conn)
        assert dates == [date(2026, 3, 18)]

    def test_get_sukuk_list_all(self, db_conn):
        rows = get_sukuk_list(db_conn)
        assert len(rows) == 3

    def test_get_sukuk_list_sorted_by_ytm_desc(self, db_conn):
        rows = get_sukuk_list(db_conn, sort_by="ytm", sort_dir="DESC")
        ytms = [r["ytm"] for r in rows if r["ytm"] is not None]
        assert ytms == sorted(ytms, reverse=True)

    def test_get_sukuk_list_filter_country(self, db_conn):
        rows = get_sukuk_list(db_conn, filters={"country": "UAE"})
        assert len(rows) == 1
        assert rows[0]["country_risk"] == "UAE"

    def test_get_sukuk_list_filter_ytm_range(self, db_conn):
        rows = get_sukuk_list(db_conn, filters={"ytm_min": "5.0", "ytm_max": "7.0"})
        assert len(rows) == 1
        assert rows[0]["isin"] == "XS2222222222"

    def test_get_sukuk_list_filter_search(self, db_conn):
        rows = get_sukuk_list(db_conn, filters={"search": "SOVEREIGN"})
        assert len(rows) == 1
        assert rows[0]["issuer"] == "TEST SOVEREIGN"

    def test_get_sukuk_detail(self, db_conn):
        detail = get_sukuk_detail(db_conn, "XS1111111111")
        assert detail is not None
        assert detail["issuer"] == "TEST SOVEREIGN"
        assert detail["sukuk_type_detected"] == "Ijara"

    def test_get_sukuk_detail_not_found(self, db_conn):
        assert get_sukuk_detail(db_conn, "XSNOTEXIST00") is None

    def test_get_sukuk_history(self, db_conn):
        # Add a second day
        upsert_daily(db_conn, SAMPLE_ROWS, date(2026, 3, 19), "http://test.pdf")
        history = get_sukuk_history(db_conn, "XS1111111111")
        assert len(history) == 2
        assert history[0]["document_date"] < history[1]["document_date"]

    def test_get_filter_options(self, db_conn):
        opts = get_filter_options(db_conn)
        assert "UAE" in opts["countries"]
        assert "Financial" in opts["sectors"]
        assert "USD" in opts["currencies"]
        assert "Ijara" in opts["sukuk_types"]
