# Sukuk Screener

A daily tracker and screener for traditional sukuk listed on the Emirates Islamic bank indicative quotes sheet. Built with FastAPI, HTMX, Tailwind CSS, and DuckDB.

## Features

- **Live screener table** with sortable columns and stackable filters (country, sector, currency, profit type, YTM range, maturity range, credit rating)
- **Comparison view** — select up to 5 sukuk for side-by-side analysis with diversification scoring
- **CSV export** — download filtered data with all 19 columns
- **Saved presets** — store and recall favourite filter combinations
- **Enrichment** — automatic sukuk type detection, zakat-adjusted YTM (AAOIFI), composite credit scoring, sector risk, risk-adjusted metric
- **TradingView charts** on individual sukuk detail pages

## Quick Start

### Option A: Run locally (no Docker)

Requirements: **Python 3.11+**

```bash
git clone https://github.com/datamufti/sukuk-screener.git
cd sukuk-screener
./run.sh
```

The script creates a virtual environment, installs dependencies, and starts the server at [http://localhost:8000](http://localhost:8000).

**Custom settings:**

```bash
# Change port
./run.sh --port 9000

# Localhost only (no LAN access)
./run.sh --host 127.0.0.1

# Custom data directory
./run.sh --data /path/to/duckdb/dir

# Or use environment variables
PORT=9000 HOST=127.0.0.1 DATA_DIR=/tmp/sukuk ./run.sh
```

### Option B: Docker Compose

Requirements: **Docker** and **Docker Compose**

```bash
git clone https://github.com/datamufti/sukuk-screener.git
cd sukuk-screener
docker compose up -d
```

The app starts at [http://localhost:8000](http://localhost:8000). Data is persisted in a Docker volume (`sukuk-data`).

To rebuild after code changes:

```bash
docker compose up -d --build
```

## Running Tests

```bash
# With run.sh's venv
source .venv/bin/activate
python -m pytest tests/ -v

# Or directly
pip install -r requirements.txt
python -m pytest tests/ -v
```

## Loading Data

On first launch the database is empty. Click the **Refresh Data** button in the top-right corner to fetch the latest Emirates Islamic sukuk PDF, parse it, and populate the screener. The data is stored in DuckDB under the `data/` directory.

## Project Structure

```
sukuk-screener/
├── app/
│   ├── config.py           # PDF URL, DB path, scheduler settings
│   ├── database.py         # DuckDB schema (5 tables)
│   ├── main.py             # FastAPI app with lifespan
│   ├── routers/
│   │   ├── pages.py        # HTML routes (Jinja2) + HTMX partials
│   │   └── api.py          # JSON API + CSV export + presets CRUD
│   ├── services/
│   │   ├── pdf_parser.py   # PDF download + parse + date extraction
│   │   ├── enrichment.py   # Type detection, zakat, credit/sector risk
│   │   ├── db_ops.py       # Upsert with ISIN dedup, query helpers
│   │   ├── scheduler.py    # UAE business day logic
│   │   └── ingest.py       # Orchestrates download → parse → enrich → store
│   └── templates/          # Jinja2 templates (HTMX-powered)
├── tests/                  # pytest suite (200+ tests)
├── run.sh                  # Local launcher (no Docker)
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python 3.12) |
| Templating | Jinja2 |
| Interactivity | HTMX 2.0.4 |
| Styling | Tailwind CSS (CDN) |
| Database | DuckDB (single-file, columnar) |
| Charts | TradingView Lightweight Charts |
| PDF Parsing | pdfplumber |
| Deployment | Docker Compose or bare-metal via `run.sh` |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Main screener page |
| `GET` | `/compare?isins=...` | Side-by-side comparison (max 5) |
| `GET` | `/sukuk/{isin}` | Detail page with chart |
| `GET` | `/htmx/table` | HTMX partial for live filtering |
| `GET` | `/api/sukuk` | Filtered list (JSON) |
| `GET` | `/api/export/csv` | CSV download |
| `GET` | `/api/presets` | List saved presets |
| `POST` | `/api/presets?name=...&filters=...` | Create preset |
| `DELETE` | `/api/presets/{id}` | Delete preset |
| `POST` | `/api/ingest` | Manually trigger data refresh |
| `GET` | `/api/filters` | Dropdown values |
| `GET` | `/api/latest-date` | Most recent data date |

## License

Private — for personal use.
