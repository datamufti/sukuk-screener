"""Enrich parsed sukuk data: type detection, zakat, credit risk, sector risk."""
import re
from typing import Any

# ---------------------------------------------------------------------------
# Sukuk type detection
# ---------------------------------------------------------------------------
TYPE_KEYWORDS = {
    "IJARA": "Ijara",
    "IJARAH": "Ijara",
    "MURABAHA": "Murabaha",
    "MURABAHAH": "Murabaha",
    "MUSHARAKA": "Partnership",
    "MUSHARAKAH": "Partnership",
    "MUDARABA": "Partnership",
    "MUDARABAH": "Partnership",
    "WAKALA": "Partnership",
    "WAKALAH": "Partnership",
}


def detect_sukuk_type(sukuk_type_raw: str | None) -> str:
    """Classify the sukuk type from the raw TYPE_OF_Sukuk field.

    Returns one of: Ijara, Murabaha, Partnership, Hybrid.
    """
    if not sukuk_type_raw:
        return "Hybrid"

    text = sukuk_type_raw.upper()
    found_types = set()

    for keyword, category in TYPE_KEYWORDS.items():
        if keyword in text:
            found_types.add(category)

    if len(found_types) == 0:
        return "Hybrid"
    if len(found_types) == 1:
        return found_types.pop()
    # Multiple different types found -> Hybrid
    return "Hybrid"


# ---------------------------------------------------------------------------
# Zakat rates per AAOIFI guidelines
# ---------------------------------------------------------------------------
ZAKAT_RATES = {
    "Ijara": 0.0,
    "Murabaha": 0.025,
    "Partnership": 0.00625,
    "Hybrid": 0.0125,
}


def get_zakat_rate(sukuk_type_detected: str) -> float:
    """Return the zakat rate for the detected sukuk type."""
    return ZAKAT_RATES.get(sukuk_type_detected, 0.0125)


def calc_zakat_adjusted_ytm(ytm: float | None, zakat_rate: float) -> float | None:
    """Calculate the zakat-adjusted YTM.

    Formula: ytm * (1 - zakat_rate)
    """
    if ytm is None:
        return None
    return round(ytm * (1.0 - zakat_rate), 4)


# ---------------------------------------------------------------------------
# Credit risk score (composite from S&P, Moody's, Fitch)
# ---------------------------------------------------------------------------
# Numeric score: higher = better credit (inverted for risk)
_SP_SCORES = {
    "AAA": 21, "AA+": 20, "AA": 19, "AA-": 18,
    "A+": 17, "A": 16, "A-": 15,
    "BBB+": 14, "BBB": 13, "BBB-": 12,
    "BB+": 11, "BB": 10, "BB-": 9,
    "B+": 8, "B": 7, "B-": 6,
    "CCC+": 5, "CCC": 4, "CCC-": 3,
    "CC": 2, "C": 1, "D": 0,
}

_MOODYS_SCORES = {
    "Aaa": 21, "Aa1": 20, "Aa2": 19, "Aa3": 18,
    "A1": 17, "A2": 16, "A3": 15,
    "Baa1": 14, "Baa2": 13, "Baa3": 12,
    "Ba1": 11, "Ba2": 10, "Ba3": 9,
    "B1": 8, "B2": 7, "B3": 6,
    "Caa1": 5, "Caa2": 4, "Caa3": 3,
    "Ca": 2, "C": 1,
}

_FITCH_SCORES = _SP_SCORES.copy()  # Fitch uses same scale as S&P


def calc_credit_risk_score(
    sp: str | None, moodys: str | None, fitch: str | None
) -> float | None:
    """Compute a composite credit quality score (0-21 scale, higher = better).

    Uses a weighted average: S&P 35%, Moody's 35%, Fitch 30%.
    Returns None if no valid rating is available.
    """
    scores = []
    weights = []

    sp_val = _SP_SCORES.get(sp)
    if sp_val is not None:
        scores.append(sp_val)
        weights.append(0.35)

    moodys_val = _MOODYS_SCORES.get(moodys)
    if moodys_val is not None:
        scores.append(moodys_val)
        weights.append(0.35)

    fitch_val = _FITCH_SCORES.get(fitch)
    if fitch_val is not None:
        scores.append(fitch_val)
        weights.append(0.30)

    if not scores:
        return None

    total_weight = sum(weights)
    return round(sum(s * w for s, w in zip(scores, weights)) / total_weight, 2)


# ---------------------------------------------------------------------------
# Sector risk score
# ---------------------------------------------------------------------------
SECTOR_RISK = {
    "Government": 1.0,
    "Supranational": 1.0,
    "Financial": 2.0,
    "Energy": 2.5,
    "Utilities": 2.0,
    "Consumer, Non-cyclical": 2.5,
    "Consumer, Cyclical": 3.0,
    "Industrial": 3.0,
    "Basic Materials": 3.0,
    "Technology": 3.0,
    "Communications": 2.5,
    "Diversified": 2.5,
}


def calc_sector_risk_score(sector: str | None) -> float:
    """Return a sector risk score (1-5 scale, lower = safer)."""
    if not sector:
        return 3.0  # default moderate
    # Try exact match first, then fuzzy
    for key, score in SECTOR_RISK.items():
        if key.upper() in sector.upper():
            return score
    return 3.0


# ---------------------------------------------------------------------------
# Risk-adjusted metric
# ---------------------------------------------------------------------------
def calc_risk_adjusted_metric(
    ytm: float | None,
    credit_risk_score: float | None,
    zakat_adjusted_ytm: float | None,
    sector_risk_score: float,
) -> float | None:
    """Composite risk-return metric.

    Formula: zakat_adjusted_ytm - (sector_risk_score * 0.3) + (credit_risk_score / 21 * 2)
    Higher = more attractive on a risk-adjusted basis.
    """
    if zakat_adjusted_ytm is None:
        return None
    credit_bonus = (credit_risk_score / 21.0 * 2.0) if credit_risk_score else 0.0
    return round(zakat_adjusted_ytm - (sector_risk_score * 0.3) + credit_bonus, 4)


# ---------------------------------------------------------------------------
# Main enrichment function
# ---------------------------------------------------------------------------
def enrich_row(row: dict) -> dict:
    """Enrich a single parsed sukuk row. Returns the enrichment fields."""
    sukuk_type_detected = detect_sukuk_type(row.get("sukuk_type"))
    zakat_rate = get_zakat_rate(sukuk_type_detected)
    ytm = row.get("ytm")
    zakat_adj_ytm = calc_zakat_adjusted_ytm(ytm, zakat_rate)
    credit_score = calc_credit_risk_score(
        row.get("sp_rating"), row.get("moodys_rating"), row.get("fitch_rating")
    )
    sector_score = calc_sector_risk_score(row.get("sector"))
    risk_metric = calc_risk_adjusted_metric(
        ytm, credit_score, zakat_adj_ytm, sector_score
    )

    return {
        "sukuk_type_detected": sukuk_type_detected,
        "zakat_rate": zakat_rate,
        "zakat_adjusted_ytm": zakat_adj_ytm,
        "credit_risk_score": credit_score,
        "sector_risk_score": sector_score,
        "risk_adjusted_metric": risk_metric,
    }
