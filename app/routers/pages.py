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
)

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _db(request: Request):
    return request.app.state.db


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
    ytm_min: float | None = Query(None),
    ytm_max: float | None = Query(None),
    search: str | None = Query(None),
    document_date: date | None = Query(None),
):
    """Main screener table page."""
    conn = _db(request)

    filters = {}
    for key in ("country", "sector", "sukuk_type", "ccy", "profit_type"):
        val = locals().get(key)
        if val:
            filters[key] = val
    if ytm_min is not None:
        filters["ytm_min"] = ytm_min
    if ytm_max is not None:
        filters["ytm_max"] = ytm_max
    if search:
        filters["search"] = search

    rows = get_sukuk_list(
        conn, document_date=document_date,
        sort_by=sort_by, sort_dir=sort_dir, filters=filters,
    )
    filter_opts = get_filter_options(conn)
    latest = get_latest_date(conn)
    avail_dates = get_available_dates(conn)

    # Compute next sort direction toggle
    next_dir = "ASC" if sort_dir == "DESC" else "DESC"

    return templates.TemplateResponse("index.html", {
        "request": request,
        "rows": rows,
        "count": len(rows),
        "filter_opts": filter_opts,
        "latest_date": latest,
        "available_dates": avail_dates,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "next_dir": next_dir,
        "filters": filters,
        "search": search or "",
        "document_date": document_date,
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
    ytm_min: float | None = Query(None),
    ytm_max: float | None = Query(None),
    search: str | None = Query(None),
    document_date: date | None = Query(None),
):
    """HTMX partial: just the table body rows for live filtering."""
    conn = _db(request)
    filters = {}
    for key in ("country", "sector", "sukuk_type", "ccy", "profit_type"):
        val = locals().get(key)
        if val:
            filters[key] = val
    if ytm_min is not None:
        filters["ytm_min"] = ytm_min
    if ytm_max is not None:
        filters["ytm_max"] = ytm_max
    if search:
        filters["search"] = search

    rows = get_sukuk_list(
        conn, document_date=document_date,
        sort_by=sort_by, sort_dir=sort_dir, filters=filters,
    )
    next_dir = "ASC" if sort_dir == "DESC" else "DESC"

    return templates.TemplateResponse("_table_rows.html", {
        "request": request,
        "rows": rows,
        "count": len(rows),
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "next_dir": next_dir,
    })
