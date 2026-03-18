"""Application configuration."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR / "data")))
DB_PATH = DATA_DIR / "sukuk.duckdb"

PDF_URL = (
    "https://www.emiratesislamic.ae/-/media/ei/pdfs/general/"
    "sukuk-indicative-quotes/sukuk_indicative_quotes.csv"
)

# Scheduler: daily at 10:00 AM UAE (UTC+4) = 06:00 UTC
INGEST_CRON_HOUR = 6
INGEST_CRON_MINUTE = 0

TEMPLATES_DIR = BASE_DIR / "app" / "templates"
STATIC_DIR = BASE_DIR / "app" / "static"
