"""JSON API endpoints for HTMX and programmatic access."""
import csv
import io
import json
import logging
from datetime import date

from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse

from app.services.db_ops import (
    get_sukuk_list,
    get_sukuk_detail,
    get_sukuk_history,
    get_filter_options,
    get_latest_date,
    get_available_dates,
    get_ingestion_log,
    list_presets,
    create_preset,
    delete_preset,
)
from app.services.ingest import run_ingestion

logger = logging.getLogger(__name__)
router = APIRouter(tags=["api"])


def _db(request: Request):
    return request.app.state.db


def _build_api_filters(
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
    for key, val in [("ytm_min", ytm_min), ("ytm_max", ytm_max), ("rating_min", rating_min)]:
        if val and val.strip():
            try:
                filters[key] = float(val.strip())
            except ValueError:
                pass
    for key, val in [("maturity_after", maturity_after), ("maturity_before", maturity_before)]:
        if val and val.strip():
            try:
                filters[key] = date.fromisoformat(val.strip())
            except ValueError:
                pass
    return filters


@router.get("/sukuk")
def list_sukuk(
    request: Request,
    sort_by: str = Query("ytm", description="Column to sort by"),
    sort_dir: str = Query("DESC", description="ASC or DESC"),
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
    """Return filtered sukuk list as JSON."""
    filters = _build_api_filters(
        country, sector, sukuk_type, ccy, profit_type,
        ytm_min, ytm_max, search,
        maturity_after, maturity_before, rating_min,
    )

    conn = _db(request)
    rows = get_sukuk_list(conn, document_date=document_date,
                          sort_by=sort_by, sort_dir=sort_dir, filters=filters)

    # Serialise dates to strings for JSON
    for r in rows:
        for k, v in r.items():
            if isinstance(v, date):
                r[k] = v.isoformat()

    return {"count": len(rows), "data": rows}


@router.get("/sukuk/{isin}")
def detail_sukuk(request: Request, isin: str):
    """Return detail for a single ISIN."""
    conn = _db(request)
    detail = get_sukuk_detail(conn, isin)
    if detail is None:
        return {"error": "ISIN not found"}

    for k, v in detail.items():
        if isinstance(v, date):
            detail[k] = v.isoformat()
    return detail


@router.get("/sukuk/{isin}/history")
def history_sukuk(request: Request, isin: str):
    """Return price history for charting."""
    conn = _db(request)
    rows = get_sukuk_history(conn, isin)
    for r in rows:
        for k, v in r.items():
            if isinstance(v, date):
                r[k] = v.isoformat()
    return {"isin": isin, "data": rows}


@router.get("/filters")
def filters(request: Request):
    """Return distinct values for filter drop-downs."""
    conn = _db(request)
    return get_filter_options(conn)


@router.get("/dates")
def dates(request: Request):
    """Return available document dates."""
    conn = _db(request)
    return {"dates": [d.isoformat() for d in get_available_dates(conn)]}


@router.get("/latest-date")
def latest_date(request: Request):
    """Return the most recent document date."""
    conn = _db(request)
    d = get_latest_date(conn)
    return {"latest_date": d.isoformat() if d else None}


@router.get("/ingestion-log")
def ingestion_log(request: Request):
    """Return recent ingestion history."""
    conn = _db(request)
    log = get_ingestion_log(conn)
    for entry in log:
        for k, v in entry.items():
            if isinstance(v, date):
                entry[k] = v.isoformat()
    return {"log": log}


@router.post("/ingest")
def trigger_ingest(request: Request):
    """Manually trigger ingestion."""
    conn = _db(request)
    result = run_ingestion(conn, force=True)
    if result.get("document_date"):
        result["document_date"] = result["document_date"].isoformat()
    return result


# ─── CSV Export ───────────────────────────────────────

CSV_COLUMNS = [
    ("isin", "ISIN"), ("issuer", "Issuer"), ("profit_rate", "Profit Rate"),
    ("profit_type", "Profit Type"), ("bid_price", "Bid"), ("ask_price", "Ask"),
    ("ytm", "YTM"), ("zakat_adjusted_ytm", "Zakat Adj YTM"),
    ("maturity", "Maturity"), ("ccy", "Currency"),
    ("sp_rating", "S&P"), ("moodys_rating", "Moody's"), ("fitch_rating", "Fitch"),
    ("country_risk", "Country"), ("sector", "Sector"),
    ("sukuk_type_detected", "Sukuk Type"), ("zakat_rate", "Zakat Rate"),
    ("credit_risk_score", "Credit Score"),
    ("risk_adjusted_metric", "Risk Adj Metric"),
]


@router.get("/export/csv")
def export_csv(
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
    """Export filtered sukuk list as CSV."""
    filters = _build_api_filters(
        country, sector, sukuk_type, ccy, profit_type,
        ytm_min, ytm_max, search,
        maturity_after, maturity_before, rating_min,
    )
    conn = _db(request)
    rows = get_sukuk_list(conn, document_date=document_date,
                          sort_by=sort_by, sort_dir=sort_dir, filters=filters)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([label for _, label in CSV_COLUMNS])
    for row in rows:
        writer.writerow([
            str(row.get(key, "") or "") for key, _ in CSV_COLUMNS
        ])

    today = date.today().isoformat()
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="sukuk_export_{today}.csv"'},
    )


# ─── Screener Presets ─────────────────────────────────

@router.get("/presets")
def api_list_presets(request: Request):
    """List all saved screener presets."""
    conn = _db(request)
    presets = list_presets(conn)
    for p in presets:
        for k, v in p.items():
            if isinstance(v, date):
                p[k] = v.isoformat()
    return {"presets": presets}


@router.post("/presets")
def api_create_preset(request: Request, name: str = Query(...), filters: str = Query("{}")):
    """Create a new screener preset."""
    conn = _db(request)
    # Validate JSON
    try:
        json.loads(filters)
    except (json.JSONDecodeError, TypeError):
        return {"error": "Invalid filters JSON"}
    preset = create_preset(conn, name, filters)
    return {"preset": preset}


@router.delete("/presets/{preset_id}")
def api_delete_preset(request: Request, preset_id: int):
    """Delete a screener preset."""
    conn = _db(request)
    deleted = delete_preset(conn, preset_id)
    if not deleted:
        return {"error": "Preset not found"}
    return {"deleted": True, "id": preset_id}
