"""Integration test: download real PDF → parse → enrich → store → query.

This test hits the real Emirates Islamic PDF URL.
Mark as slow/skip if running without network access.
"""
import pytest
from datetime import date
from pathlib import Path
import tempfile

from app.database import setup_database
from app.services.pdf_parser import download_pdf, extract_document_date, parse_pdf
from app.services.db_ops import (
    upsert_daily,
    get_latest_date,
    get_sukuk_list,
    get_filter_options,
    get_sukuk_detail,
)
from app.services.ingest import run_ingestion
from app.config import PDF_URL


@pytest.fixture(scope="module")
def real_pdf_bytes():
    """Download the real PDF once for all tests in this module."""
    return download_pdf()


@pytest.fixture
def db_conn():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "integration_test.duckdb"
        conn = setup_database(db_path)
        yield conn
        conn.close()


class TestRealPDFParsing:
    def test_pdf_downloads(self, real_pdf_bytes):
        """PDF should be a valid PDF file (starts with %PDF)."""
        assert real_pdf_bytes[:4] == b"%PDF"
        assert len(real_pdf_bytes) > 10_000  # should be at least 10KB

    def test_document_date_extracted(self, real_pdf_bytes):
        doc_date = extract_document_date(real_pdf_bytes)
        assert isinstance(doc_date, date)
        # Should be today or within the last 3 business days
        assert (date.today() - doc_date).days <= 4
        # Must be a UAE business day (not a weekend/holiday)
        from app.services.scheduler import is_uae_business_day
        assert is_uae_business_day(doc_date)

    def test_rows_parsed(self, real_pdf_bytes):
        rows = parse_pdf(real_pdf_bytes)
        # Expect 100-200 sukuk rows
        assert len(rows) >= 50, f"Only parsed {len(rows)} rows — expected 100+"
        assert len(rows) <= 300

        # Each row should have an ISIN
        for row in rows:
            assert row["isin"] is not None
            assert len(row["isin"]) == 12

    def test_data_quality(self, real_pdf_bytes):
        rows = parse_pdf(real_pdf_bytes)
        # Check some rows have valid numeric data
        has_ytm = sum(1 for r in rows if r["ytm"] is not None)
        has_bid = sum(1 for r in rows if r["bid_price"] is not None)
        assert has_ytm > len(rows) * 0.5, "Less than 50% of rows have YTM"
        assert has_bid > len(rows) * 0.3, "Less than 30% of rows have bid price"

        # Check some rows have country and sector
        has_country = sum(1 for r in rows if r["country_risk"] is not None)
        assert has_country > len(rows) * 0.7

    def test_sukuk_types_present(self, real_pdf_bytes):
        rows = parse_pdf(real_pdf_bytes)
        types = {r["sukuk_type"] for r in rows if r["sukuk_type"]}
        # Should find at least Ijara and Murabaha types
        type_text = " ".join(types).upper()
        assert "IJARA" in type_text or "MURABAHA" in type_text or "WAKALA" in type_text


class TestFullIngestion:
    def test_run_ingestion_with_real_pdf(self, db_conn, real_pdf_bytes):
        result = run_ingestion(db_conn, force=True, pdf_bytes=real_pdf_bytes)
        assert result["success"] is True
        assert result["row_count"] >= 50
        assert result["document_date"] is not None

    def test_data_queryable_after_ingestion(self, db_conn, real_pdf_bytes):
        run_ingestion(db_conn, force=True, pdf_bytes=real_pdf_bytes)

        # Verify latest date
        latest = get_latest_date(db_conn)
        assert latest is not None

        # Verify list query works
        sukuk_list = get_sukuk_list(db_conn)
        assert len(sukuk_list) >= 50

        # Verify enrichment columns present
        first = sukuk_list[0]
        assert "zakat_adjusted_ytm" in first
        assert "credit_risk_score" in first
        assert "sukuk_type_detected" in first

    def test_filter_options_populated(self, db_conn, real_pdf_bytes):
        run_ingestion(db_conn, force=True, pdf_bytes=real_pdf_bytes)

        opts = get_filter_options(db_conn)
        assert len(opts["countries"]) >= 3  # UAE, Turkey, Bahrain, etc.
        assert len(opts["sectors"]) >= 2
        assert len(opts["currencies"]) >= 1

    def test_idempotent_ingestion(self, db_conn, real_pdf_bytes):
        """Running ingestion twice should not double the rows."""
        result1 = run_ingestion(db_conn, force=True, pdf_bytes=real_pdf_bytes)
        count1 = result1["row_count"]

        result2 = run_ingestion(db_conn, force=True, pdf_bytes=real_pdf_bytes)
        count2 = result2["row_count"]

        total = db_conn.execute("SELECT COUNT(*) FROM sukuk_daily").fetchone()[0]
        assert total == count1  # Should not be doubled
        assert count1 == count2

    def test_detail_view_works(self, db_conn, real_pdf_bytes):
        run_ingestion(db_conn, force=True, pdf_bytes=real_pdf_bytes)

        # Get first ISIN from the list
        sukuk_list = get_sukuk_list(db_conn)
        first_isin = sukuk_list[0]["isin"]

        detail = get_sukuk_detail(db_conn, first_isin)
        assert detail is not None
        assert detail["isin"] == first_isin
