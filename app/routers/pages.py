"""HTML page routes rendered via Jinja2 + HTMX."""
from datetime import date

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR
from app.services.db_ops import (
    get_sukuk_list,
    get_sukuk_detail,
    get_sukuk_history,
    get_filter_options,
    get_latest_date,
    get_available_dates,
    list_presets,
)

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _db(request: Request):
    return request.app.state.db


def _build_filters(
    country: str | None,
    sector: str | None,
    sukuk_type: str | None,
    ccy: str | None,
    profit_type: str | None,
    ytm_min: str | None,
    ytm_max: str | None,
    search: str | None,
    maturity_after: str | None = None,
    maturity_before: str | None = None,
    rating_min: str | None = None,
) -> dict:
    """Build a filters dict, ignoring empty strings."""
    filters = {}
    for key, val in [
        ("country", country), ("sector", sector), ("sukuk_type", sukuk_type),
        ("ccy", ccy), ("profit_type", profit_type), ("search", search),
    ]:
        if val and val.strip():
            filters[key] = val.strip()
    # Numeric: only set if non-empty and parseable
    for key, val in [("ytm_min", ytm_min), ("ytm_max", ytm_max), ("rating_min", rating_min)]:
        if val and val.strip():
            try:
                filters[key] = float(val.strip())
            except ValueError:
                pass
    # Date: only set if non-empty and parseable
    for key, val in [("maturity_after", maturity_after), ("maturity_before", maturity_before)]:
        if val and val.strip():
            try:
                filters[key] = date.fromisoformat(val.strip())
            except ValueError:
                pass
    return filters


def _get_total_count(conn, document_date=None) -> int:
    """Get total sukuk count (unfiltered) for the given date."""
    rows = get_sukuk_list(conn, document_date=document_date)
    return len(rows)


def _compute_diversification(sukuk_list: list[dict]) -> dict:
    """Compute diversification analysis for a portfolio of sukuk.

    Returns dict with:
      - country: {name: pct, ...}
      - sector: {name: pct, ...}
      - rating_band: {band: pct, ...}
      - warnings: [{category, value, pct}, ...]
      - overall: "good" | "warning" | "moderate"
    """
    if not sukuk_list:
        return {"country": {}, "sector": {}, "rating_band": {}, "warnings": [], "overall": "moderate"}

    n = len(sukuk_list)
    THRESHOLD = 50.0

    # Count by category
    country_counts: dict[str, int] = {}
    sector_counts: dict[str, int] = {}
    rating_band_counts: dict[str, int] = {}

    for s in sukuk_list:
        # Country
        c = s.get("country_risk") or "Unknown"
        country_counts[c] = country_counts.get(c, 0) + 1

        # Sector
        sec = s.get("sector") or "Unknown"
        sector_counts[sec] = sector_counts.get(sec, 0) + 1

        # Rating band
        score = s.get("credit_risk_score")
        if score is None:
            band = "Unrated"
        elif score >= 18:
            band = "AAA-AA"
        elif score >= 15:
            band = "A"
        elif score >= 12:
            band = "BBB"
        elif score >= 6:
            band = "BB-B"
        else:
            band = "Below B"
        rating_band_counts[band] = rating_band_counts.get(band, 0) + 1

    def _to_pct(counts: dict) -> dict:
        return {k: round(v / n * 100, 1) for k, v in counts.items()}

    country_pct = _to_pct(country_counts)
    sector_pct = _to_pct(sector_counts)
    rating_pct = _to_pct(rating_band_counts)

    # Warnings
    warnings = []
    for category, pct_dict in [("country", country_pct), ("sector", sector_pct), ("rating_band", rating_pct)]:
        for val, pct in pct_dict.items():
            if pct > THRESHOLD:
                warnings.append({"category": category, "value": val, "pct": pct})

    # Overall assessment
    if warnings:
        overall = "warning"
    elif any(pct > 40 for pct in list(country_pct.values()) + list(sector_pct.values())):
        overall = "moderate"
    else:
        overall = "good"

    return {
        "country": country_pct,
        "sector": sector_pct,
        "rating_band": rating_pct,
        "warnings": warnings,
        "overall": overall,
    }


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    sort_by: str = Query("ytm"),
    sort_dir: str = Query("DESC"),
    country: str | None = Query(None),
    sector: str | None = Query(None),
    sukuk_type: str | None = Query(None),
    ccy: str | None = Query(None),
    profit_type: str | None = Query(None),
    ytm_min: str | None = Query(None),
    ytm_max: str | None = Query(None),
    search: str | None = Query(None),
    maturity_after: str | None = Query(None),
    maturity_before: str | None = Query(None),
    rating_min: str | None = Query(None),
    document_date: date | None = Query(None),
):
    """Main screener table page."""
    conn = _db(request)

    filters = _build_filters(
        country, sector, sukuk_type, ccy, profit_type,
        ytm_min, ytm_max, search, maturity_after, maturity_before, rating_min,
    )

    rows = get_sukuk_list(
        conn, document_date=document_date,
        sort_by=sort_by, sort_dir=sort_dir, filters=filters,
    )
    filter_opts = get_filter_options(conn)
    latest = get_latest_date(conn)
    avail_dates = get_available_dates(conn)
    total = _get_total_count(conn, document_date=document_date)
    presets = list_presets(conn)

    # Compute next sort direction toggle
    next_dir = "ASC" if sort_dir == "DESC" else "DESC"

    return templates.TemplateResponse("index.html", {
        "request": request,
        "rows": rows,
        "count": len(rows),
        "total_count": total,
        "filter_opts": filter_opts,
        "latest_date": latest,
        "available_dates": avail_dates,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "next_dir": next_dir,
        "filters": filters,
        "search": search or "",
        "document_date": document_date,
        "presets": presets,
    })


@router.get("/compare", response_class=HTMLResponse)
def compare(
    request: Request,
    isins: str = Query(""),
):
    """Comparison page for 2-5 sukuk."""
    conn = _db(request)
    latest = get_latest_date(conn)

    isin_list = [s.strip() for s in isins.split(",") if s.strip()][:5]

    sukuk_list = []
    for isin in isin_list:
        detail = get_sukuk_detail(conn, isin)
        if detail:
            sukuk_list.append(detail)

    diversification = _compute_diversification(sukuk_list)

    return templates.TemplateResponse("compare.html", {
        "request": request,
        "sukuk_list": sukuk_list,
        "diversification": diversification,
        "latest_date": latest,
    })


@router.get("/sukuk/{isin}", response_class=HTMLResponse)
def detail(request: Request, isin: str):
    """Detail page for a single sukuk."""
    conn = _db(request)
    detail_data = get_sukuk_detail(conn, isin)
    history = get_sukuk_history(conn, isin)
    latest = get_latest_date(conn)

    return templates.TemplateResponse("detail.html", {
        "request": request,
        "sukuk": detail_data,
        "history": history,
        "isin": isin,
        "latest_date": latest,
    })


@router.get("/htmx/table", response_class=HTMLResponse)
def htmx_table(
    request: Request,
    sort_by: str = Query("ytm"),
    sort_dir: str = Query("DESC"),
    country: str | None = Query(None),
    sector: str | None = Query(None),
    sukuk_type: str | None = Query(None),
    ccy: str | None = Query(None),
    profit_type: str | None = Query(None),
    ytm_min: str | None = Query(None),
    ytm_max: str | None = Query(None),
    search: str | None = Query(None),
    maturity_after: str | None = Query(None),
    maturity_before: str | None = Query(None),
    rating_min: str | None = Query(None),
    document_date: date | None = Query(None),
):
    """HTMX partial: just the table body rows for live filtering."""
    conn = _db(request)
    filters = _build_filters(
        country, sector, sukuk_type, ccy, profit_type,
        ytm_min, ytm_max, search, maturity_after, maturity_before, rating_min,
    )

    rows = get_sukuk_list(
        conn, document_date=document_date,
        sort_by=sort_by, sort_dir=sort_dir, filters=filters,
    )
    total = _get_total_count(conn, document_date=document_date)
    next_dir = "ASC" if sort_dir == "DESC" else "DESC"

    return templates.TemplateResponse("_table_rows.html", {
        "request": request,
        "rows": rows,
        "count": len(rows),
        "total_count": total,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "next_dir": next_dir,
    })
