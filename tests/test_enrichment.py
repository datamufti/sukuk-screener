"""Tests for enrichment module: type detection, zakat, credit risk, sector risk."""
import pytest
from app.services.enrichment import (
    detect_sukuk_type,
    get_zakat_rate,
    calc_zakat_adjusted_ytm,
    calc_credit_risk_score,
    calc_sector_risk_score,
    calc_risk_adjusted_metric,
    enrich_row,
    ZAKAT_RATES,
)


# ---------------------------------------------------------------------------
# Sukuk type detection
# ---------------------------------------------------------------------------
class TestDetectSukukType:
    def test_ijara_simple(self):
        assert detect_sukuk_type("Sukuk Al Ijara") == "Ijara"

    def test_ijara_case_insensitive(self):
        assert detect_sukuk_type("sukuk al ijarah") == "Ijara"

    def test_murabaha(self):
        assert detect_sukuk_type("Sukuk Al Murabaha") == "Murabaha"

    def test_murabahah_variant(self):
        assert detect_sukuk_type("Sukuk Al Murabahah") == "Murabaha"

    def test_wakala(self):
        assert detect_sukuk_type("Sukuk Al Wakala Bel Istithmar") == "Partnership"

    def test_mudaraba(self):
        assert detect_sukuk_type("Sukuk Al Mudarabah") == "Partnership"

    def test_musharaka(self):
        assert detect_sukuk_type("Sukuk Al Musharakah") == "Partnership"

    def test_hybrid_ijara_murabaha(self):
        assert detect_sukuk_type("Sukuk Al Ijara,Sukuk Al Murabaha") == "Hybrid"

    def test_hybrid_ijara_wakala(self):
        assert detect_sukuk_type("Sukuk Al Ijara,Sukuk Al Wakala") == "Hybrid"

    def test_unknown_returns_hybrid(self):
        assert detect_sukuk_type("Sukuk/Islamic") == "Hybrid"

    def test_none_returns_hybrid(self):
        assert detect_sukuk_type(None) == "Hybrid"

    def test_empty_returns_hybrid(self):
        assert detect_sukuk_type("") == "Hybrid"

    def test_murabaha_wakala_is_hybrid(self):
        """Mixed Murabaha+Wakala should be Hybrid (two different categories)."""
        assert detect_sukuk_type("Sukuk Al Murabaha,Sukuk Al Wakala Bel Istithmar") == "Hybrid"


# ---------------------------------------------------------------------------
# Zakat rates
# ---------------------------------------------------------------------------
class TestZakatRates:
    def test_ijara_zero(self):
        assert get_zakat_rate("Ijara") == 0.0

    def test_murabaha_full(self):
        assert get_zakat_rate("Murabaha") == 0.025

    def test_partnership_quarter(self):
        assert get_zakat_rate("Partnership") == 0.00625

    def test_hybrid_half(self):
        assert get_zakat_rate("Hybrid") == 0.0125

    def test_unknown_defaults_hybrid(self):
        assert get_zakat_rate("SomethingElse") == 0.0125

    def test_zakat_adjusted_ytm_ijara(self):
        """Ijara: 0% zakat, YTM unchanged."""
        assert calc_zakat_adjusted_ytm(5.0, 0.0) == 5.0

    def test_zakat_adjusted_ytm_murabaha(self):
        """Murabaha: 2.5% zakat deducted from YTM."""
        result = calc_zakat_adjusted_ytm(5.0, 0.025)
        assert result == pytest.approx(4.875, abs=0.001)

    def test_zakat_adjusted_ytm_partnership(self):
        result = calc_zakat_adjusted_ytm(5.0, 0.00625)
        assert result == pytest.approx(4.9688, abs=0.001)

    def test_zakat_adjusted_ytm_none(self):
        assert calc_zakat_adjusted_ytm(None, 0.025) is None


# ---------------------------------------------------------------------------
# Credit risk score
# ---------------------------------------------------------------------------
class TestCreditRiskScore:
    def test_aaa_all_agencies(self):
        score = calc_credit_risk_score("AAA", "Aaa", "AAA")
        assert score == 21.0

    def test_single_sp(self):
        score = calc_credit_risk_score("BBB", None, None)
        assert score == 13.0

    def test_single_moodys(self):
        score = calc_credit_risk_score(None, "Baa2", None)
        assert score == 13.0

    def test_mixed_ratings(self):
        score = calc_credit_risk_score("A", "A2", "A")
        # S&P A=16, Moody's A2=16, Fitch A=16 → 16.0
        assert score == 16.0

    def test_split_ratings(self):
        score = calc_credit_risk_score("BBB+", "Baa1", "BBB")
        # S&P BBB+=14, Moody's Baa1=14, Fitch BBB=13
        # (14*0.35 + 14*0.35 + 13*0.30) = 4.9+4.9+3.9 = 13.7
        assert score == pytest.approx(13.7, abs=0.01)

    def test_no_ratings(self):
        assert calc_credit_risk_score(None, None, None) is None

    def test_junk_rating(self):
        score = calc_credit_risk_score("B-", None, None)
        assert score == 6.0

    def test_wr_not_rated(self):
        """WR (Watch Removed) is not in the lookup."""
        assert calc_credit_risk_score("WR", None, None) is None


# ---------------------------------------------------------------------------
# Sector risk score
# ---------------------------------------------------------------------------
class TestSectorRiskScore:
    def test_government(self):
        assert calc_sector_risk_score("Government") == 1.0

    def test_financial(self):
        assert calc_sector_risk_score("Financial") == 2.0

    def test_consumer_cyclical(self):
        assert calc_sector_risk_score("Consumer, Cyclical") == 3.0

    def test_unknown_sector(self):
        assert calc_sector_risk_score("Alien Technology") == 3.0

    def test_none_sector(self):
        assert calc_sector_risk_score(None) == 3.0

    def test_partial_match(self):
        """Sector containing 'Government' should match."""
        assert calc_sector_risk_score("Government of Bahrain") == 1.0


# ---------------------------------------------------------------------------
# Risk-adjusted metric
# ---------------------------------------------------------------------------
class TestRiskAdjustedMetric:
    def test_basic_calculation(self):
        result = calc_risk_adjusted_metric(
            ytm=5.0, credit_risk_score=16.0,
            zakat_adjusted_ytm=5.0, sector_risk_score=1.0,
        )
        # 5.0 - (1.0*0.3) + (16/21*2) = 5.0 - 0.3 + 1.524 = 6.224
        assert result == pytest.approx(6.224, abs=0.01)

    def test_none_ytm(self):
        result = calc_risk_adjusted_metric(
            ytm=None, credit_risk_score=16.0,
            zakat_adjusted_ytm=None, sector_risk_score=1.0,
        )
        assert result is None


# ---------------------------------------------------------------------------
# Full enrichment pipeline
# ---------------------------------------------------------------------------
class TestEnrichRow:
    def test_ijara_row(self):
        row = {
            "sukuk_type": "Sukuk Al Ijara",
            "ytm": 4.5,
            "sp_rating": "A",
            "moodys_rating": "A2",
            "fitch_rating": "A",
            "sector": "Government",
        }
        result = enrich_row(row)
        assert result["sukuk_type_detected"] == "Ijara"
        assert result["zakat_rate"] == 0.0
        assert result["zakat_adjusted_ytm"] == 4.5  # No zakat deduction
        assert result["credit_risk_score"] == 16.0
        assert result["sector_risk_score"] == 1.0

    def test_murabaha_row(self):
        row = {
            "sukuk_type": "Sukuk Al Murabaha",
            "ytm": 5.0,
            "sp_rating": "BBB",
            "moodys_rating": None,
            "fitch_rating": None,
            "sector": "Financial",
        }
        result = enrich_row(row)
        assert result["sukuk_type_detected"] == "Murabaha"
        assert result["zakat_rate"] == 0.025
        assert result["zakat_adjusted_ytm"] == pytest.approx(4.875, abs=0.001)
        assert result["sector_risk_score"] == 2.0

    def test_missing_everything(self):
        row = {}
        result = enrich_row(row)
        assert result["sukuk_type_detected"] == "Hybrid"
        assert result["zakat_rate"] == 0.0125
        assert result["zakat_adjusted_ytm"] is None
        assert result["credit_risk_score"] is None
