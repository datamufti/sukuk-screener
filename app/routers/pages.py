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
    # Date filters: only set if non-empty and parseable
    for key, val in [("maturity_after", maturity_after), ("maturity_before", maturity_before)]:
        if val and val.strip():
            try:
                filters[key] = date.fromisoformat(val.strip())
            except ValueError:
                pass
    return filters


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
    document_date: date | None = Query(None),
    maturity_after: str | None = Query(None),
    maturity_before: str | None = Query(None),
    rating_min: str | None = Query(None),
):
    """Main screener table page."""
    conn = _db(request)

    filters = _build_filters(
        country, sector, sukuk_type, ccy, profit_type,
        ytm_min, ytm_max, search,
        maturity_after, maturity_before, rating_min,
    )

    rows = get_sukuk_list(
        conn, document_date=document_date,
        sort_by=sort_by, sort_dir=sort_dir, filters=filters,
    )
    total_count = len(get_sukuk_list(conn, document_date=document_date))
    filter_opts = get_filter_options(conn)
    latest = get_latest_date(conn)
    avail_dates = get_available_dates(conn)
    presets = list_presets(conn)

    # Compute next sort direction toggle
    next_dir = "ASC" if sort_dir == "DESC" else "DESC"

    return templates.TemplateResponse("index.html", {
        "request": request,
        "rows": rows,
        "count": len(rows),
        "total_count": total_count,
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


@router.get("/sukuk/{isin}", response_class=HTMLResponse)
def detail(request: Request, isin: str):
    """Detail page for a single sukuk."""
    conn = _db(request)
    detail_data = get_sukuk_detail(conn, isin)
    history = get_sukuk_history(conn, isin)

    return templates.TemplateResponse("detail.html", {
        "request": request,
        "sukuk": detail_data,
        "history": history,
        "isin": isin,
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
    document_date: date | None = Query(None),
    maturity_after: str | None = Query(None),
    maturity_before: str | None = Query(None),
    rating_min: str | None = Query(None),
):
    """HTMX partial: just the table body rows for live filtering."""
    conn = _db(request)
    filters = _build_filters(
        country, sector, sukuk_type, ccy, profit_type,
        ytm_min, ytm_max, search,
        maturity_after, maturity_before, rating_min,
    )

    rows = get_sukuk_list(
        conn, document_date=document_date,
        sort_by=sort_by, sort_dir=sort_dir, filters=filters,
    )
    total_count = len(get_sukuk_list(conn, document_date=document_date))
    next_dir = "ASC" if sort_dir == "DESC" else "DESC"

    return templates.TemplateResponse("_table_rows.html", {
        "request": request,
        "rows": rows,
        "count": len(rows),
        "total_count": total_count,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "next_dir": next_dir,
    })


def _compute_diversification(sukuk_list: list[dict]) -> dict:
    """Compute concentration analysis for a portfolio."""
    if not sukuk_list:
        return {"country": {}, "sector": {}, "rating_band": {}, "warnings": []}

    total = len(sukuk_list)

    # Country concentration
    country_counts: dict[str, int] = {}
    for s in sukuk_list:
        c = s.get("country_risk") or "Unknown"
        country_counts[c] = country_counts.get(c, 0) + 1
    country_pcts = {k: round(v / total * 100, 1) for k, v in country_counts.items()}

    # Sector concentration
    sector_counts: dict[str, int] = {}
    for s in sukuk_list:
        sec = s.get("sector") or "Unknown"
        sector_counts[sec] = sector_counts.get(sec, 0) + 1
    sector_pcts = {k: round(v / total * 100, 1) for k, v in sector_counts.items()}

    # Rating band concentration
    def _rating_band(score):
        if score is None:
            return "Unrated"
        if score >= 18:
            return "AAA-AA"
        if score >= 15:
            return "A"
        if score >= 12:
            return "BBB"
        if score >= 6:
            return "BB-B"
        return "Below B"

    band_counts: dict[str, int] = {}
    for s in sukuk_list:
        band = _rating_band(s.get("credit_risk_score"))
        band_counts[band] = band_counts.get(band, 0) + 1
    band_pcts = {k: round(v / total * 100, 1) for k, v in band_counts.items()}

    # Warnings
    warnings = []
    for label, pcts in [("country", country_pcts), ("sector", sector_pcts), ("rating_band", band_pcts)]:
        for cat, pct in pcts.items():
            if pct > 50:
                warnings.append({"category": label, "value": cat, "pct": pct, "level": "warning"})

    # Overall diversification status
    max_pct = max(
        (max(country_pcts.values()) if country_pcts else 0),
        (max(sector_pcts.values()) if sector_pcts else 0),
        (max(band_pcts.values()) if band_pcts else 0),
    )
    overall = "good" if max_pct <= 40 else ("warning" if max_pct > 50 else "moderate")

    return {
        "country": country_pcts,
        "sector": sector_pcts,
        "rating_band": band_pcts,
        "warnings": warnings,
        "overall": overall,
    }


@router.get("/compare", response_class=HTMLResponse)
def compare(
    request: Request,
    isins: str = Query(""),
):
    """Comparison page for selected sukuk."""
    conn = _db(request)
    latest = get_latest_date(conn)
    isin_list = [i.strip() for i in isins.split(",") if i.strip()][:5]

    sukuk_list = []
    for isin in isin_list:
        detail_data = get_sukuk_detail(conn, isin)
        if detail_data:
            sukuk_list.append(detail_data)

    diversification = _compute_diversification(sukuk_list)

    return templates.TemplateResponse("compare.html", {
        "request": request,
        "sukuk_list": sukuk_list,
        "diversification": diversification,
        "latest_date": latest,
    })
