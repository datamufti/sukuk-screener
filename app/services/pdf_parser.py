"""Download and parse the Emirates Islamic sukuk PDF into structured rows."""
import io
import re
import logging
from datetime import date, datetime
from typing import Any

import httpx
import pdfplumber

from app.config import PDF_URL

logger = logging.getLogger(__name__)

# Expected column headers (order matters — matches PDF table layout)
EXPECTED_COLUMNS = [
    "isin", "issuer", "profit_rate", "profit_type",
    "bid_price", "ask_price", "ytm", "maturity", "maturity_type",
    "ccy", "sp_rating", "moodys_rating", "fitch_rating",
    "min_investment", "country_risk", "sector", "sukuk_type",
]


def download_pdf(url: str = PDF_URL, timeout: float = 30.0) -> bytes:
    """Download the PDF and return raw bytes."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.emiratesislamic.ae/",
    }
    resp = httpx.get(url, timeout=timeout, follow_redirects=True, headers=headers)
    resp.raise_for_status()
    return resp.content


def _parse_pdf_metadata_date(raw: str) -> date | None:
    """Parse a PDF metadata date string like 'D:20260313090752+04\'00\'' into a date."""
    if not raw:
        return None
    # Strip the "D:" prefix if present
    s = raw.strip()
    if s.startswith("D:"):
        s = s[2:]
    # We need at least 8 digits: YYYYMMDD
    m = re.match(r"(\d{4})(\d{2})(\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def extract_document_date(pdf_bytes: bytes) -> date:
    """Extract the document date from PDF metadata or first-page text.

    Primary: reads CreationDate / ModDate from PDF metadata.
    Fallback: looks for 'Date: DD Month YYYY' patterns in page text.
    """
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        metadata = pdf.metadata or {}

        # --- Primary: PDF metadata ---
        for key in ("CreationDate", "ModDate"):
            raw = metadata.get(key)
            if raw:
                parsed = _parse_pdf_metadata_date(str(raw))
                if parsed:
                    logger.info(f"Extracted date from PDF metadata '{key}': {parsed}")
                    return parsed

        # --- Fallback: text patterns ---
        first_page_text = pdf.pages[0].extract_text() or ""

    # Pattern 1: "Date: 17 March 2026" or "Date : 17 March 2026"
    m = re.search(
        r"Date\s*:\s*(\d{1,2}\s+\w+\s+\d{4})", first_page_text, re.IGNORECASE
    )
    if m:
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                return datetime.strptime(m.group(1).strip(), fmt).date()
            except ValueError:
                continue

    # Pattern 2: "Date: 17-Mar-2026"
    m = re.search(
        r"Date\s*:\s*(\d{1,2}-\w{3}-\d{4})", first_page_text, re.IGNORECASE
    )
    if m:
        return datetime.strptime(m.group(1).strip(), "%d-%b-%Y").date()

    raise ValueError(
        f"Could not extract document date from PDF. "
        f"Metadata: {metadata}; First 500 chars: {first_page_text[:500]}"
    )


def _safe_float(val: Any) -> float | None:
    """Convert a value to float, returning None on failure."""
    if val is None:
        return None
    s = str(val).strip().replace(",", "")
    if s in ("", "-", "N/A", "n/a", "NR", "WR"):
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> int | None:
    """Convert a value to int, returning None on failure."""
    if val is None:
        return None
    s = str(val).strip().replace(",", "").replace(" ", "")
    if s in ("", "-", "N/A"):
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _parse_maturity(val: Any) -> date | None:
    """Parse a maturity date string, returning None for perpetuals / unparseable."""
    if val is None:
        return None
    s = str(val).strip().upper()
    if s in ("PERP", "PERPETUAL", "PERP/CALL", "", "-"):
        return None
    # Try common date formats
    for fmt in ("%d-%b-%y", "%d-%b-%Y", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(str(val).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _clean_string(val: Any) -> str | None:
    """Clean a string value."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s and s not in ("-", "N/A") else None


def parse_pdf(pdf_bytes: bytes) -> list[dict]:
    """Parse all pages of the sukuk PDF into a list of row dicts.

    Returns a list of dicts with keys matching EXPECTED_COLUMNS.
    """
    rows = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            for table in tables:
                if not table:
                    continue
                for row_idx, row in enumerate(table):
                    if not row or len(row) < 10:
                        continue
                    # Skip header rows
                    first_cell = str(row[0] or "").strip().upper()
                    if first_cell in ("ISIN", "ISSUER", "") or "INDICATIVE" in first_cell:
                        continue
                    if "DATE" in first_cell or "PAGE" in first_cell:
                        continue
                    if "SUKUK" in first_cell and "PRICES" in str(row).upper():
                        continue
                    # Skip disclaimer/footer rows
                    joined = " ".join(str(c or "") for c in row).upper()
                    if "DISCLAIMER" in joined or "PAST PERFORMANCE" in joined:
                        continue

                    parsed = _parse_row(row)
                    if parsed and parsed.get("isin"):
                        rows.append(parsed)

    logger.info(f"Parsed {len(rows)} sukuk rows from PDF ({len(pdf.pages) if pdf_bytes else 0} pages)")
    return rows


def _parse_row(row: list) -> dict | None:
    """Parse a single table row into a structured dict.

    The PDF table has these columns (some may be merged/split):
    ISIN | Issuer | Profit Rate | Profit Type | BID Price | ASK Price |
    Indicative YTM | Maturity | Maturity Type | CCY | S&P | Moody's |
    Fitch | Min Piece | Country Risk | Sector | TYPE_OF_Sukuk
    """
    # Pad row to expected length
    while len(row) < 17:
        row.append(None)

    isin = _clean_string(row[0])
    if not isin or not re.match(r"^[A-Z0-9]{12}$", str(isin).replace(" ", "")):
        return None

    return {
        "isin": isin.replace(" ", ""),
        "issuer": _clean_string(row[1]),
        "profit_rate": _safe_float(row[2]),
        "profit_type": _clean_string(row[3]),
        "bid_price": _safe_float(row[4]),
        "ask_price": _safe_float(row[5]),
        "ytm": _safe_float(row[6]),
        "maturity": _parse_maturity(row[7]),
        "maturity_type": _clean_string(row[8]),
        "ccy": _clean_string(row[9]),
        "sp_rating": _clean_string(row[10]),
        "moodys_rating": _clean_string(row[11]),
        "fitch_rating": _clean_string(row[12]),
        "min_investment": _safe_int(row[13]),
        "country_risk": _clean_string(row[14]),
        "sector": _clean_string(row[15]),
        "sukuk_type": _clean_string(row[16]),
    }
