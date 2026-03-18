"""Tests for PDF parser: helper functions and row parsing."""
import pytest
from datetime import date
from app.services.pdf_parser import (
    _safe_float,
    _safe_int,
    _parse_maturity,
    _clean_string,
    _parse_row,
    _parse_pdf_metadata_date,
)


class TestParsePdfMetadataDate:
    def test_standard_creation_date(self):
        assert _parse_pdf_metadata_date("D:20260313090752+04'00'") == date(2026, 3, 13)

    def test_without_d_prefix(self):
        assert _parse_pdf_metadata_date("20260313090752") == date(2026, 3, 13)

    def test_date_only(self):
        assert _parse_pdf_metadata_date("D:20260315") == date(2026, 3, 15)

    def test_none(self):
        assert _parse_pdf_metadata_date(None) is None

    def test_empty(self):
        assert _parse_pdf_metadata_date("") is None

    def test_invalid_string(self):
        assert _parse_pdf_metadata_date("not-a-date") is None

    def test_invalid_date_values(self):
        # Month 13 should fail
        assert _parse_pdf_metadata_date("D:20261332") is None

    def test_with_utc_offset(self):
        assert _parse_pdf_metadata_date("D:20260101120000Z") == date(2026, 1, 1)

    def test_with_negative_offset(self):
        assert _parse_pdf_metadata_date("D:20251231235959-05'00'") == date(2025, 12, 31)


class TestSafeFloat:
    def test_normal_float(self):
        assert _safe_float("4.5") == 4.5

    def test_with_comma(self):
        assert _safe_float("1,234.56") == 1234.56

    def test_none(self):
        assert _safe_float(None) is None

    def test_dash(self):
        assert _safe_float("-") is None

    def test_nr(self):
        assert _safe_float("NR") is None

    def test_wr(self):
        assert _safe_float("WR") is None

    def test_empty(self):
        assert _safe_float("") is None

    def test_integer_string(self):
        assert _safe_float("100") == 100.0


class TestSafeInt:
    def test_normal_int(self):
        assert _safe_int("200000") == 200000

    def test_with_comma(self):
        assert _safe_int("200,000") == 200000

    def test_with_spaces(self):
        assert _safe_int("2 00,000") == 200000

    def test_none(self):
        assert _safe_int(None) is None

    def test_dash(self):
        assert _safe_int("-") is None


class TestParseMaturity:
    def test_standard_format(self):
        assert _parse_maturity("30-Mar-27") == date(2027, 3, 30)

    def test_full_year(self):
        assert _parse_maturity("30-Mar-2027") == date(2027, 3, 30)

    def test_perp(self):
        assert _parse_maturity("PERP") is None

    def test_perp_call(self):
        assert _parse_maturity("PERP/CALL") is None

    def test_none(self):
        assert _parse_maturity(None) is None

    def test_empty(self):
        assert _parse_maturity("") is None

    def test_slash_format(self):
        assert _parse_maturity("30/03/2027") == date(2027, 3, 30)


class TestCleanString:
    def test_normal(self):
        assert _clean_string("USD") == "USD"

    def test_whitespace(self):
        assert _clean_string("  USD  ") == "USD"

    def test_dash(self):
        assert _clean_string("-") is None

    def test_none(self):
        assert _clean_string(None) is None

    def test_na(self):
        assert _clean_string("N/A") is None


class TestParseRow:
    def test_valid_row(self):
        row = [
            "XS2282234090", "FAB SUKUK COMPANY LTD", "1.411", "FIXED",
            "99.50", "100.50", "4.63", "30-Mar-27", "AT MATURITY",
            "USD", "AA-", "Aa3", "AA-", "200,000", "UAE", "Financial",
            "Sukuk Al Murabaha,Sukuk Al Wakala\nBel Istithmar",
        ]
        result = _parse_row(row)
        assert result is not None
        assert result["isin"] == "XS2282234090"
        assert result["issuer"] == "FAB SUKUK COMPANY LTD"
        assert result["profit_rate"] == 1.411
        assert result["bid_price"] == 99.50
        assert result["ask_price"] == 100.50
        assert result["ytm"] == 4.63
        assert result["maturity"] == date(2027, 3, 30)
        assert result["ccy"] == "USD"
        assert result["min_investment"] == 200000
        assert result["country_risk"] == "UAE"

    def test_invalid_isin(self):
        row = ["NOT_AN_ISIN", "Issuer", "1.0", "FIXED"] + [None] * 13
        result = _parse_row(row)
        assert result is None

    def test_header_row_filtered(self):
        row = ["ISIN", "Issuer", "Profit Rate"] + [None] * 14
        result = _parse_row(row)
        assert result is None

    def test_short_row_padded(self):
        row = ["XS1234567890", "Test Issuer", "5.0"]
        result = _parse_row(row)
        # Should be padded and parsed (ISIN is invalid length though - 12 chars needed)
        # XS1234567890 is 12 chars, so valid
        assert result is not None
        assert result["isin"] == "XS1234567890"

    def test_perpetual_maturity(self):
        row = [
            "XS9876543210", "PERP ISSUER", "6.0", "VARIABLE",
            "97.00", "98.50", "8.0", "PERP", "PERP/CALL",
            "USD", None, None, None, "200,000", "Turkey", "Financial",
            "Sukuk Al Mudarabah",
        ]
        result = _parse_row(row)
        assert result is not None
        assert result["maturity"] is None
        assert result["maturity_type"] == "PERP/CALL"
