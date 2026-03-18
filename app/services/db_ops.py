"""Database operations: upsert sukuk data, query for UI."""
import logging
from datetime import date, datetime, timezone
from typing import Any

import duckdb

from app.services.enrichment import enrich_row

logger = logging.getLogger(__name__)


def upsert_daily(
    conn: duckdb.DuckDBPyConnection,
    rows: list[dict],
    document_date: date,
    source_url: str,
) -> int:
    """Insert or replace daily sukuk rows. Returns count of rows upserted."""
    if not rows:
        return 0

    # Delete existing rows for this date (idempotent upsert)
    conn.execute(
        "DELETE FROM sukuk_daily WHERE document_date = ?", [document_date]
    )
    conn.execute(
        "DELETE FROM sukuk_enriched WHERE document_date = ?", [document_date]
    )

    # Deduplicate: if the PDF has the same ISIN twice, keep the last occurrence
    seen: dict[str, dict] = {}
    for row in rows:
        isin = row.get("isin")
        if isin:
            seen[isin] = row
    deduped_rows = list(seen.values())
    logger.info(
        f"Deduped {len(rows)} parsed rows to {len(deduped_rows)} unique ISINs"
    )

    count = 0
    for row in deduped_rows:
        isin = row["isin"]

        conn.execute(
            """
            INSERT INTO sukuk_daily (
                isin, document_date, issuer, profit_rate, profit_type,
                bid_price, ask_price, ytm, maturity, maturity_type,
                ccy, sp_rating, moodys_rating, fitch_rating,
                min_investment, country_risk, sector, sukuk_type,
                ingestion_ts, source_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                isin, document_date, row.get("issuer"),
                row.get("profit_rate"), row.get("profit_type"),
                row.get("bid_price"), row.get("ask_price"),
                row.get("ytm"), row.get("maturity"), row.get("maturity_type"),
                row.get("ccy"), row.get("sp_rating"), row.get("moodys_rating"),
                row.get("fitch_rating"), row.get("min_investment"),
                row.get("country_risk"), row.get("sector"), row.get("sukuk_type"),
                datetime.now(timezone.utc), source_url,
            ],
        )

        # Compute and insert enrichment
        enriched = enrich_row(row)
        conn.execute(
            """
            INSERT INTO sukuk_enriched (
                isin, document_date, credit_risk_score, sector_risk_score,
                zakat_rate, zakat_adjusted_ytm, risk_adjusted_metric,
                sukuk_type_detected
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                isin, document_date,
                enriched["credit_risk_score"], enriched["sector_risk_score"],
                enriched["zakat_rate"], enriched["zakat_adjusted_ytm"],
                enriched["risk_adjusted_metric"], enriched["sukuk_type_detected"],
            ],
        )
        count += 1

    # Update master table
    _update_master(conn, document_date)

    logger.info(f"Upserted {count} sukuk rows for {document_date}")
    return count


def _update_master(conn: duckdb.DuckDBPyConnection, document_date: date) -> None:
    """Update sukuk_master from the latest daily data."""
    # Mark all as inactive first
    conn.execute("UPDATE sukuk_master SET is_active = false")

    # Upsert from today's data
    conn.execute("""
        INSERT INTO sukuk_master (isin, issuer, first_seen, last_seen,
                                  latest_ytm, latest_bid, latest_ask,
                                  sukuk_type, is_active)
        SELECT
            d.isin, d.issuer, ?, ?,
            d.ytm, d.bid_price, d.ask_price,
            e.sukuk_type_detected, true
        FROM sukuk_daily d
        LEFT JOIN sukuk_enriched e ON d.isin = e.isin AND d.document_date = e.document_date
        WHERE d.document_date = ?
        ON CONFLICT (isin) DO UPDATE SET
            issuer = EXCLUDED.issuer,
            last_seen = EXCLUDED.last_seen,
            latest_ytm = EXCLUDED.latest_ytm,
            latest_bid = EXCLUDED.latest_bid,
            latest_ask = EXCLUDED.latest_ask,
            sukuk_type = EXCLUDED.sukuk_type,
            is_active = true
    """, [document_date, document_date, document_date])

    # For existing ISINs, keep their original first_seen
    conn.execute("""
        UPDATE sukuk_master SET first_seen = (
            SELECT MIN(document_date) FROM sukuk_daily WHERE sukuk_daily.isin = sukuk_master.isin
        )
    """)


# ---------------------------------------------------------------------------
# Query helpers for the UI
# ---------------------------------------------------------------------------

def get_latest_date(conn: duckdb.DuckDBPyConnection) -> date | None:
    """Return the most recent document_date in the database."""
    result = conn.execute(
        "SELECT MAX(document_date) FROM sukuk_daily"
    ).fetchone()
    return result[0] if result and result[0] else None


def get_available_dates(conn: duckdb.DuckDBPyConnection) -> list[date]:
    """Return all distinct dates in descending order."""
    rows = conn.execute(
        "SELECT DISTINCT document_date FROM sukuk_daily ORDER BY document_date DESC"
    ).fetchall()
    return [r[0] for r in rows]


def get_sukuk_list(
    conn: duckdb.DuckDBPyConnection,
    document_date: date | None = None,
    sort_by: str = "ytm",
    sort_dir: str = "DESC",
    filters: dict | None = None,
) -> list[dict]:
    """Get the sukuk list for a given date with optional filters.

    Returns joined data from sukuk_daily + sukuk_enriched.
    """
    if document_date is None:
        document_date = get_latest_date(conn)
    if document_date is None:
        return []

    # Validate sort column to prevent injection
    allowed_sort = {
        "isin", "issuer", "profit_rate", "bid_price", "ask_price", "ytm",
        "maturity", "ccy", "sp_rating", "moodys_rating", "fitch_rating",
        "country_risk", "sector", "sukuk_type", "zakat_adjusted_ytm",
        "credit_risk_score", "risk_adjusted_metric", "sukuk_type_detected",
        "min_investment", "sector_risk_score", "zakat_rate",
    }
    if sort_by not in allowed_sort:
        sort_by = "ytm"
    if sort_dir.upper() not in ("ASC", "DESC"):
        sort_dir = "DESC"

    where_clauses = ["d.document_date = ?"]
    params: list[Any] = [document_date]

    if filters:
        if filters.get("country"):
            where_clauses.append("d.country_risk = ?")
            params.append(filters["country"])
        if filters.get("sector"):
            where_clauses.append("d.sector = ?")
            params.append(filters["sector"])
        if filters.get("sukuk_type"):
            where_clauses.append("e.sukuk_type_detected = ?")
            params.append(filters["sukuk_type"])
        if filters.get("ccy"):
            where_clauses.append("d.ccy = ?")
            params.append(filters["ccy"])
        if filters.get("profit_type"):
            where_clauses.append("d.profit_type = ?")
            params.append(filters["profit_type"])
        if filters.get("ytm_min"):
            where_clauses.append("d.ytm >= ?")
            params.append(float(filters["ytm_min"]))
        if filters.get("ytm_max"):
            where_clauses.append("d.ytm <= ?")
            params.append(float(filters["ytm_max"]))
        if filters.get("maturity_before"):
            where_clauses.append("d.maturity <= ?")
            params.append(filters["maturity_before"])
        if filters.get("maturity_after"):
            where_clauses.append("d.maturity >= ?")
            params.append(filters["maturity_after"])
        if filters.get("rating_min"):
            where_clauses.append("e.credit_risk_score >= ?")
            params.append(float(filters["rating_min"]))
        if filters.get("search"):
            where_clauses.append("(d.issuer ILIKE ? OR d.isin ILIKE ?)")
            term = f"%{filters['search']}%"
            params.extend([term, term])

    where_sql = " AND ".join(where_clauses)

    query = f"""
        SELECT
            d.isin, d.issuer, d.profit_rate, d.profit_type,
            d.bid_price, d.ask_price, d.ytm,
            d.maturity, d.maturity_type, d.ccy,
            d.sp_rating, d.moodys_rating, d.fitch_rating,
            d.min_investment, d.country_risk, d.sector, d.sukuk_type,
            e.credit_risk_score, e.sector_risk_score,
            e.zakat_rate, e.zakat_adjusted_ytm,
            e.risk_adjusted_metric, e.sukuk_type_detected
        FROM sukuk_daily d
        LEFT JOIN sukuk_enriched e
            ON d.isin = e.isin AND d.document_date = e.document_date
        WHERE {where_sql}
        ORDER BY {sort_by} {sort_dir} NULLS LAST
    """

    result = conn.execute(query, params)
    columns = [desc[0] for desc in result.description]
    return [dict(zip(columns, row)) for row in result.fetchall()]


def get_sukuk_detail(
    conn: duckdb.DuckDBPyConnection, isin: str
) -> dict | None:
    """Get the latest data for a specific ISIN."""
    latest_date = get_latest_date(conn)
    if not latest_date:
        return None

    result = conn.execute("""
        SELECT
            d.*, e.credit_risk_score, e.sector_risk_score,
            e.zakat_rate, e.zakat_adjusted_ytm,
            e.risk_adjusted_metric, e.sukuk_type_detected
        FROM sukuk_daily d
        LEFT JOIN sukuk_enriched e
            ON d.isin = e.isin AND d.document_date = e.document_date
        WHERE d.isin = ? AND d.document_date = ?
    """, [isin, latest_date])

    columns = [desc[0] for desc in result.description]
    row = result.fetchone()
    return dict(zip(columns, row)) if row else None


def get_sukuk_history(
    conn: duckdb.DuckDBPyConnection, isin: str
) -> list[dict]:
    """Get historical data for a specific ISIN for charting."""
    result = conn.execute("""
        SELECT
            d.document_date, d.bid_price, d.ask_price, d.ytm,
            e.zakat_adjusted_ytm
        FROM sukuk_daily d
        LEFT JOIN sukuk_enriched e
            ON d.isin = e.isin AND d.document_date = e.document_date
        WHERE d.isin = ?
        ORDER BY d.document_date ASC
    """, [isin])

    columns = [desc[0] for desc in result.description]
    return [dict(zip(columns, row)) for row in result.fetchall()]


def get_filter_options(conn: duckdb.DuckDBPyConnection) -> dict:
    """Get distinct values for filter dropdowns."""
    latest_date = get_latest_date(conn)
    if not latest_date:
        return {
            "countries": [], "sectors": [], "currencies": [],
            "sukuk_types": [], "profit_types": [],
        }

    def _distinct(col: str, table: str = "sukuk_daily") -> list[str]:
        rows = conn.execute(
            f"SELECT DISTINCT {col} FROM {table} "
            f"WHERE document_date = ? AND {col} IS NOT NULL "
            f"ORDER BY {col}",
            [latest_date],
        ).fetchall()
        return [r[0] for r in rows]

    return {
        "countries": _distinct("country_risk"),
        "sectors": _distinct("sector"),
        "currencies": _distinct("ccy"),
        "sukuk_types": _distinct("sukuk_type_detected", "sukuk_enriched"),
        "profit_types": _distinct("profit_type"),
    }


def get_ingestion_log(conn: duckdb.DuckDBPyConnection) -> list[dict]:
    """Get ingestion stats per date."""
    result = conn.execute("""
        SELECT document_date, COUNT(*) as sukuk_count,
               MIN(ingestion_ts) as ingested_at
        FROM sukuk_daily
        GROUP BY document_date
        ORDER BY document_date DESC
        LIMIT 30
    """)
    columns = [desc[0] for desc in result.description]
    return [dict(zip(columns, row)) for row in result.fetchall()]
