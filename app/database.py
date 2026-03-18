"""DuckDB connection management and schema initialization."""
import duckdb
from pathlib import Path
from app.config import DB_PATH, DATA_DIR


def get_connection(db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    """Return a DuckDB connection. Creates the data dir if needed."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path))


def init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create all tables if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sukuk_daily (
            isin              VARCHAR NOT NULL,
            document_date     DATE NOT NULL,
            issuer            VARCHAR,
            profit_rate       DOUBLE,
            profit_type       VARCHAR,
            bid_price         DOUBLE,
            ask_price         DOUBLE,
            ytm               DOUBLE,
            maturity          DATE,
            maturity_type     VARCHAR,
            ccy               VARCHAR,
            sp_rating         VARCHAR,
            moodys_rating     VARCHAR,
            fitch_rating      VARCHAR,
            min_investment    INTEGER,
            country_risk      VARCHAR,
            sector            VARCHAR,
            sukuk_type        VARCHAR,
            ingestion_ts      TIMESTAMP DEFAULT current_timestamp,
            source_url        VARCHAR,
            PRIMARY KEY (isin, document_date)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sukuk_enriched (
            isin                VARCHAR NOT NULL,
            document_date       DATE NOT NULL,
            credit_risk_score   DOUBLE,
            sector_risk_score   DOUBLE,
            zakat_rate          DOUBLE,
            zakat_adjusted_ytm  DOUBLE,
            risk_adjusted_metric DOUBLE,
            sukuk_type_detected VARCHAR,
            PRIMARY KEY (isin, document_date)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sukuk_master (
            isin         VARCHAR PRIMARY KEY,
            issuer       VARCHAR,
            first_seen   DATE,
            last_seen    DATE,
            latest_ytm   DOUBLE,
            latest_bid   DOUBLE,
            latest_ask   DOUBLE,
            sukuk_type   VARCHAR,
            is_active    BOOLEAN DEFAULT true
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS screener_presets (
            id          INTEGER PRIMARY KEY DEFAULT nextval('preset_seq'),
            name        VARCHAR NOT NULL,
            filters_json VARCHAR,
            created_at  TIMESTAMP DEFAULT current_timestamp,
            updated_at  TIMESTAMP DEFAULT current_timestamp
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS news_items (
            id            INTEGER PRIMARY KEY DEFAULT nextval('news_seq'),
            issuer_match  VARCHAR,
            title         VARCHAR,
            url           VARCHAR,
            source        VARCHAR,
            published_at  TIMESTAMP,
            fetched_at    TIMESTAMP DEFAULT current_timestamp
        )
    """)


def init_sequences(conn: duckdb.DuckDBPyConnection) -> None:
    """Create sequences for auto-increment columns."""
    conn.execute("CREATE SEQUENCE IF NOT EXISTS preset_seq START 1")
    conn.execute("CREATE SEQUENCE IF NOT EXISTS news_seq START 1")


def setup_database(db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    """Full database setup: connect, create sequences, create tables."""
    conn = get_connection(db_path)
    init_sequences(conn)
    init_schema(conn)
    return conn
