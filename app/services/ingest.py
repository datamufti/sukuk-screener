"""Orchestrate the full ingestion pipeline: download → parse → enrich → store."""
import logging
from datetime import date

import duckdb

from app.config import PDF_URL
from app.services.pdf_parser import download_pdf, extract_document_date, parse_pdf
from app.services.scheduler import is_uae_business_day
from app.services.db_ops import upsert_daily

logger = logging.getLogger(__name__)


def run_ingestion(
    conn: duckdb.DuckDBPyConnection,
    force: bool = False,
    pdf_bytes: bytes | None = None,
) -> dict:
    """Run the full ingestion pipeline.

    Args:
        conn: DuckDB connection
        force: If True, skip business day check
        pdf_bytes: If provided, use these bytes instead of downloading

    Returns:
        dict with keys: success, document_date, row_count, message
    """
    today = date.today()

    if not force and not is_uae_business_day(today):
        msg = f"Skipping ingestion: {today} is not a UAE business day"
        logger.info(msg)
        return {"success": True, "document_date": None, "row_count": 0, "message": msg}

    try:
        # Step 1: Download PDF
        if pdf_bytes is None:
            logger.info("Downloading sukuk PDF...")
            pdf_bytes = download_pdf()
        logger.info(f"PDF downloaded: {len(pdf_bytes)} bytes")

        # Step 2: Extract document date
        doc_date = extract_document_date(pdf_bytes)
        logger.info(f"Document date: {doc_date}")

        # Step 3: Parse rows
        rows = parse_pdf(pdf_bytes)
        if not rows:
            msg = f"No sukuk rows parsed from PDF dated {doc_date}"
            logger.warning(msg)
            return {"success": False, "document_date": doc_date, "row_count": 0, "message": msg}

        # Step 4: Store (enrichment happens inside upsert_daily)
        count = upsert_daily(conn, rows, doc_date, PDF_URL)

        msg = f"Ingested {count} sukuk for {doc_date}"
        logger.info(msg)
        return {"success": True, "document_date": doc_date, "row_count": count, "message": msg}

    except Exception as e:
        msg = f"Ingestion failed: {e}"
        logger.exception(msg)
        return {"success": False, "document_date": None, "row_count": 0, "message": msg}
