# Sukuk Screener & Daily Tracker — Lightweight PRD v0.1

| Field | Value |
|---|---|
| **Author** | Talal Mufti |
| **Status** | Draft |
| **Last Updated** | March 17, 2026 |
| **Classification** | Personal / Internal Use |

## Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 0.1 | March 17, 2026 | Talal Mufti | Initial draft |

---

## 1. Problem Statement

The author actively invests in traditional sukuk through Emirates Islamic Bank. The bank publishes a daily PDF with indicative prices and yields for approximately 140–160 sukuk instruments. A working Python pipeline (`pdf_to_csv_enriched.py`) currently downloads, parses, and enriches this data into timestamped CSVs, orchestrated through an n8n workflow on WSL/Docker.

Despite this pipeline, significant gaps remain. There is no existing tool — personal or commercial — that:

1. Tracks Emirates Islamic sukuk prices historically over time
2. Calculates zakat-adjusted yields by sukuk type per AAOIFI guidelines
3. Allows compound screening for portfolio construction considering diversification across country, sector, and credit rating
4. Aggregates relevant news for issuers in the portfolio

**Existing platforms are inadequate for this use case:**

- **LSEG Sukuk Now / Bloomberg** — institutional pricing, prohibitively expensive for a personal investor
- **Musaffa / HalalWallet** — focused on equity/fund halal screening, not traditional sukuk
- **Tabadulat** — fractional/retail sukuk platform, different universe of instruments
- **Emirates Islamic's own PDF** — static, no history, no screening, no enrichment

The result: the investor spends ~30 minutes daily on manual CSV manipulation in Excel to answer basic questions like "which investment-grade sukuk in a non-GCC country offers the best zakat-adjusted yield with maturity under 3 years?"

---

## 2. Goals

- **Automate end-to-end:** Replace the manual Python + n8n + CSV + Excel pipeline with a single self-contained web application that handles PDF ingestion, enrichment, persistent storage, and interactive UI.
- **Accumulate history:** Build a forward-looking daily time series of sukuk prices, yields, and ratings from day one — enabling trend analysis that is currently impossible.
- **Enable intelligent screening:** Reduce the time from "I want to find sukuk" to "I have a diversified shortlist" from ~30 minutes to under 5 minutes through compound filters, side-by-side comparison, and portfolio construction.
- **Zakat-aware returns:** Calculate accurate zakat-adjusted YTM by sukuk structure type (Ijara, Murabaha, Musharaka/Mudaraba/Wakala, hybrid) per AAOIFI guidelines, making true after-zakat returns immediately visible.
- **Surface relevant news:** Aggregate issuer-specific news from GCC/Islamic finance RSS feeds so that material events are visible alongside pricing data.

---

## 3. Non-Goals

- **Multi-user support or authentication** — This is a personal tool running on a local LAN. Adding auth adds complexity with zero benefit.
- **Real-time prices** — The Emirates Islamic PDF is indicative and updated once daily. There is no real-time data source to consume.
- **Fractional sukuk tracking** — Emirates Islamic publishes a separate PDF for fractional sukuk. This is a different product with different characteristics and is out of scope.
- **Order execution or brokerage integration** — This is a screening and analytics tool only. Trades are executed through the bank's relationship manager.
- **Native mobile app** — Responsive web design is sufficient for quick mobile checks. A dedicated app would be over-engineering.
- **Backtesting or algorithmic trading** — Premature without sufficient historical data. May revisit once 6+ months of data has accumulated.

---

## 4. User Stories

1. **Daily ingestion:** As the investor, I want the app to automatically download and parse the Emirates Islamic sukuk PDF each business day so that I have up-to-date pricing data without any manual intervention.
2. **Browse today's list:** As the investor, I want to see all sukuk from today's PDF in a sortable, filterable table so that I can quickly scan the universe and spot opportunities.
3. **Compound filtering:** As the investor, I want to apply multiple filters simultaneously (e.g., YTM > 5%, S&P rating ≥ BBB-, sector = Financial, maturity < 2028) so that I can narrow down to sukuk that match my specific investment criteria.
4. **Price history:** As the investor, I want to view a historical chart of bid price, ask price, and YTM for any individual sukuk so that I can identify trends and determine whether current pricing represents a good entry point.
5. **Portfolio comparison:** As the investor, I want to select 2–5 sukuk and view them side-by-side (price, yield, rating, maturity, country, sector) so that I can construct a diversified portfolio avoiding concentration risk.
6. **Zakat calculation:** As the investor, I want to see the zakat-adjusted YTM for each sukuk, calculated according to its structural type, so that I can compare true after-zakat returns.
7. **Issuer news:** As the investor, I want to see recent news headlines related to issuers in my watchlist or comparison view so that I can be aware of material events affecting my positions or prospective investments.
8. **Saved presets:** As the investor, I want to save my most-used filter combinations as named presets so that I can instantly apply them each day without reconfiguring the screener.
9. **Export data:** As the investor, I want to export the filtered screener results to CSV so that I can perform ad-hoc analysis in Excel or share a shortlist with my advisor.
10. **Mobile quick check:** As the investor, I want to check today's prices and my comparison view on my phone so that I can stay informed while away from my desk.

---

## 5. Requirements

### P0 — Must-Have (V1 Launch)

#### 5.1 Automated Daily PDF Ingestion
- Download the Emirates Islamic traditional sukuk PDF daily from the published URL
- Extract the document date from the PDF content (not from download timestamp)
- Parse all pages (typically 5–6) using pdfplumber to extract ~140–160 sukuk rows
- Columns extracted: ISIN, Issuer, Profit Rate (%), Profit Type, BID Price, ASK Price, Indicative YTM (%), Maturity, Maturity Type, CCY, S&P Rating, Moody's Rating, Fitch Rating, Min Investment Piece, Country Risk, Sector, TYPE_OF_Sukuk
- Skip UAE weekends (Saturday–Sunday) and UAE public holidays
- Idempotent ingestion: re-running for the same document date should upsert, not duplicate

#### 5.2 Data Enrichment
- Credit risk score: composite numeric score derived from S&P, Moody's, and Fitch ratings
- Sector risk score: categorical risk assigned to each sector
- Zakat-adjusted YTM: apply type-based zakat rates per AAOIFI guidelines:

| Sukuk Type | Zakat Rate | Rationale |
|---|---|---|
| Ijara | 0% | Issuer pays zakat on underlying asset; investor only pays on rental income |
| Murabaha | 2.5% | Full principal is zakatable (trade debt) |
| Musharaka / Mudaraba / Wakala | 0.625% | ~25% liquid portion × 2.5% |
| Hybrid / Unknown | 1.25% | Conservative 50% liquid estimate |

- Risk-adjusted metric: composite score combining YTM, credit risk, and zakat adjustment

#### 5.3 Persistent Historical Storage
- Store all daily snapshots in DuckDB with full historical retention
- Forward-only accumulation — no backfill required. History starts from day one of deployment
- Maintain a deduplicated sukuk master table (by ISIN) with first_seen, last_seen, and latest metrics

#### 5.4 Interactive Data Table
- Display all sukuk from the latest ingestion date in a responsive, sortable table
- Column sorting on all fields (ascending/descending toggle)
- Inline filtering per column (text search, numeric ranges, dropdown for categorical fields)
- Responsive layout: horizontal scroll on mobile, sticky headers

#### 5.5 Individual Sukuk Detail View
- Dedicated page per ISIN showing full current data plus historical price/yield charts
- TradingView Lightweight Charts for bid price, ask price, and YTM time series
- Display all rating agency scores, enrichment data, and zakat-adjusted metrics

#### 5.6 Compound Filter Builder
- Stackable filters with AND logic across: country, sector, sukuk type, YTM range, credit rating range, maturity date range, currency, profit type
- Dynamic result count updates as filters are applied
- Clear all / reset filters button

#### 5.7 Portfolio / Comparison View
- Select 2–5 sukuk for side-by-side comparison
- Show key metrics in a comparison table: price, YTM, zakat-adjusted YTM, rating, maturity, country, sector
- Visual indicators for diversification: flag when multiple selections share the same country, sector, or rating band

#### 5.8 Business Day Awareness
- UAE weekends are Saturday–Sunday (changed in January 2022)
- Configurable list of UAE public holidays (manually maintained or fetched from a reliable source)
- Scheduler skips non-business days; UI shows the most recent business day's data on weekends/holidays

### P1 — Nice-to-Have

- **Saved screener presets:** name, save, load, and delete filter combinations
- **RSS news feed:** aggregate headlines from Reuters Islamic Finance, Gulf News Business, Arabian Business, and Zawya by matching issuer names
- **CSV export:** export current filtered view to a downloadable CSV file
- **Price change alerts:** configurable thresholds that trigger a daily email summary when a watched sukuk's YTM or price moves beyond a threshold
- **Diversification scoring:** for a selected portfolio, show concentration percentages by country, sector, and rating band with visual indicators (pie/bar)

### P2 — Future Considerations

- Web search enrichment for issuer-specific news beyond RSS feeds
- AI-powered news summarization: LLM-generated summaries of aggregated news per issuer
- Duration and convexity calculations for more sophisticated fixed-income analytics
- Yield curve visualization: plot YTM vs. maturity for the full universe, segmented by rating
- Benchmark comparison: overlay S&P Sukuk Index or similar benchmarks on portfolio performance
- Sukuk maturity/delisting detection: auto-flag when a sukuk drops off the PDF

---

## 6. Recommended Tech Stack

The following stack is recommended based on the constraints of a single-user personal tool, the existing Python enrichment logic, and the analytical nature of the workload.

| Component | Technology | Justification |
|---|---|---|
| **Backend** | FastAPI (Python) | Existing enrichment logic is Python. Async, well-typed, fast. No need for a separate Node.js backend. |
| **Frontend** | HTMX + Jinja2 + Tailwind CSS | Server-rendered HTML with HTMX for interactivity (sort, filter, lazy load). Eliminates SPA build pipeline. Tailwind via CDN for responsive styling. |
| **Database** | DuckDB | Columnar, vectorized analytics on growing time-series. Embeddable, single file, zero config. Native Parquet support. Better than SQLite for aggregation-heavy workloads. |
| **Charts** | TradingView Lightweight Charts | Purpose-built for financial data. ~40KB footprint, line/area/candlestick support, fast rendering. Free and open source. |
| **Scheduler** | APScheduler | Built-in Python scheduler with cron expressions. Replaces n8n entirely. Configurable, skips weekends/holidays. |
| **PDF Parsing** | pdfplumber | Already proven in the existing pipeline. Reliable extraction of tabular data from multi-page PDFs. |
| **Deployment** | Docker Compose | Single `docker-compose up` to run everything. DuckDB file mounted as a volume for persistence. LAN-only access. |

### Alternatives Considered

- **SQLite:** Solid for OLTP workloads but slower for the analytical queries (aggregations, group-bys, window functions) that dominate this use case as historical data grows.
- **React / Next.js:** Overkill for a single-user personal tool. Adds a build pipeline, Node.js dependency, and significant frontend complexity without proportional benefit.
- **Streamlit / Dash:** Fast for prototyping but limited customization for screener UX. No proper URL routing, poor mobile experience, constrained layout control.
- **PostgreSQL:** Too heavy for a personal local tool. Requires its own container, configuration, and maintenance. DuckDB delivers better analytical performance with zero operational overhead.

---

## 7. Proposed Architecture

The application is deployed as a single Docker Compose stack running on WSL, accessible over the local LAN. All components — backend, scheduler, and database — run in a single container for simplicity.

```
┌──────────────────────────────────────────────────────────────┐
│                    Docker Compose Stack                       │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                 FastAPI Application                     │  │
│  │                                                        │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐   │  │
│  │  │   HTMX +     │ │ APScheduler  │ │ RSS Fetcher  │   │  │
│  │  │  Jinja2 UI   │ │ (Cron Jobs)  │ │ (Periodic)   │   │  │
│  │  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘   │  │
│  │         │                │                │            │  │
│  │         ▼                ▼                ▼            │  │
│  │  ┌─────────────────────────────────────────────────┐   │  │
│  │  │          FastAPI Route Handlers                 │   │  │
│  │  │    (Enrichment · Filtering · API Logic)         │   │  │
│  │  └────────────────────┬────────────────────────────┘   │  │
│  │                       │                                │  │
│  │                       ▼                                │  │
│  │  ┌─────────────────────────────────────────────────┐   │  │
│  │  │            DuckDB (File-based)                  │   │  │
│  │  │  sukuk_daily · sukuk_enriched · sukuk_master    │   │  │
│  │  │  screener_presets · news_items                  │   │  │
│  │  └─────────────────────────────────────────────────┘   │  │
│  └────────────────────────────────────────────────────────┘  │
│                          │                                   │
│              Docker Volume Mount                             │
│              ./data:/app/data                                │
└──────────────────────────────────────────────────────────────┘

External Data Sources:

  Emirates Islamic PDF ─── HTTPS GET (daily) ────► APScheduler
  RSS Feeds (Reuters, Gulf News, etc.) ──────────► RSS Fetcher
  LAN Browser ─── HTTP :8000 ────────────────────► HTMX UI
```

---

## 8. Data Model

The database consists of five core tables. DuckDB's columnar storage is optimized for the analytical query patterns (time-series aggregations, multi-column filters) that dominate this workload.

### 8.1 sukuk_daily

Raw daily snapshot from the PDF. One row per ISIN per business day. Primary key: `(isin, document_date)`.

| Column | Type | Description |
|---|---|---|
| `isin` | VARCHAR | ISIN identifier (PK part 1) |
| `document_date` | DATE | Date extracted from PDF content (PK part 2) |
| `issuer` | VARCHAR | Issuer name as printed in the PDF |
| `profit_rate` | DECIMAL(6,3) | Profit rate percentage |
| `profit_type` | VARCHAR | Fixed / Floating |
| `bid_price` | DECIMAL(8,4) | Bid price |
| `ask_price` | DECIMAL(8,4) | Ask price |
| `ytm` | DECIMAL(6,3) | Indicative yield to maturity (%) |
| `maturity` | DATE | Maturity date (NULL for perpetuals) |
| `maturity_type` | VARCHAR | AT MATURITY / CALLABLE / PERP/CALL / SINKABLE |
| `ccy` | VARCHAR(3) | Currency code (USD, AED, SAR, etc.) |
| `sp_rating` | VARCHAR(10) | S&P rating |
| `moodys_rating` | VARCHAR(10) | Moody's rating |
| `fitch_rating` | VARCHAR(10) | Fitch rating |
| `min_investment` | INTEGER | Minimum investment piece |
| `country_risk` | VARCHAR | Country of risk |
| `sector` | VARCHAR | Industry sector |
| `sukuk_type` | VARCHAR | TYPE_OF_Sukuk from PDF |
| `ingestion_ts` | TIMESTAMP | When this row was ingested |
| `source_url` | VARCHAR | URL of the source PDF |

### 8.2 sukuk_enriched

Computed enrichment data. One row per ISIN per business day. Joined to `sukuk_daily` on `(isin, document_date)`.

| Column | Type | Description |
|---|---|---|
| `isin` | VARCHAR | FK to sukuk_daily |
| `document_date` | DATE | FK to sukuk_daily |
| `credit_risk_score` | DECIMAL(4,2) | Composite score from S&P, Moody's, Fitch |
| `sector_risk_score` | DECIMAL(4,2) | Risk score assigned to the sector |
| `zakat_rate` | DECIMAL(5,3) | Zakat rate based on sukuk type (0–2.5%) |
| `zakat_adjusted_ytm` | DECIMAL(6,3) | YTM after zakat deduction |
| `risk_adjusted_metric` | DECIMAL(6,3) | Composite risk-return metric |
| `sukuk_type_detected` | VARCHAR | Classified: Ijara / Murabaha / Partnership / Hybrid |

### 8.3 sukuk_master

Deduplicated reference table. One row per ISIN. Updated on each ingestion.

| Column | Type | Description |
|---|---|---|
| `isin` | VARCHAR | Primary key |
| `issuer` | VARCHAR | Latest issuer name |
| `first_seen` | DATE | First document_date this ISIN appeared |
| `last_seen` | DATE | Most recent document_date |
| `latest_ytm` | DECIMAL(6,3) | Most recent YTM |
| `latest_bid` | DECIMAL(8,4) | Most recent bid price |
| `latest_ask` | DECIMAL(8,4) | Most recent ask price |
| `sukuk_type` | VARCHAR | Detected sukuk structure type |
| `is_active` | BOOLEAN | True if seen in the latest ingestion |

### 8.4 screener_presets

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Auto-increment PK |
| `name` | VARCHAR | User-defined preset name |
| `filters_json` | JSON | Serialized filter configuration |
| `created_at` | TIMESTAMP | When the preset was created |
| `updated_at` | TIMESTAMP | Last modification timestamp |

### 8.5 news_items

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Auto-increment PK |
| `issuer_match` | VARCHAR | Matched issuer name from sukuk_master |
| `title` | VARCHAR | News headline |
| `url` | VARCHAR | Link to the full article |
| `source` | VARCHAR | Feed source (Reuters, Gulf News, etc.) |
| `published_at` | TIMESTAMP | Article publication timestamp |
| `fetched_at` | TIMESTAMP | When the item was fetched |

---

## 9. Success Metrics

As a personal tool, success metrics are pragmatic rather than business-oriented:

| Metric | Target | Measurement |
|---|---|---|
| Ingestion reliability | ≥95% of business days ingested without manual intervention | Count gaps in sukuk_daily date series |
| Data integrity | Zero duplicate rows per (ISIN, document_date) | SQL uniqueness check |
| Screening speed | < 5 min from intent to shortlist (down from ~30 min) | Subjective timing by user |
| Zakat accuracy | 100% match with manual calculation for all sukuk types | Spot-check 10 sukuk across all 4 type categories |
| Mobile usability | Core table and comparison view usable on iPhone/Android | Manual testing on mobile browser |
| Uptime | App accessible on LAN whenever WSL is running | Docker container health check |

---

## 10. Open Questions

| # | Question | Owner |
|---|---|---|
| 1 | Should the app auto-detect when a sukuk drops off the PDF (matured/delisted) and flag it in the UI? If so, after how many consecutive absences? | Product |
| 2 | How should the app handle occasional PDF format changes by Emirates Islamic? Defensive parsing with fallback, or strict schema validation that alerts on failure? | Engineering |
| 3 | Should bid-ask spread trends be tracked as an additional metric? Useful for liquidity analysis but adds complexity. | Product |
| 4 | Which RSS feeds are most reliable for GCC/sukuk news? Candidates: Reuters Islamic Finance, Gulf News Business, Zawya, Arabian Business, IFN (Islamic Finance News). | Research |
| 5 | Should the UAE holiday calendar be hardcoded or fetched from an API? Hardcoded is simpler but requires annual updates. | Engineering |
| 6 | Is DuckDB's single-writer limitation acceptable, or should we add a write queue for concurrent scheduler + user query scenarios? | Engineering |

---

## 11. Timeline & Phasing

Estimated timeline assumes part-time development (evenings/weekends). The phased approach prioritizes the core value loop (ingest → store → view) before adding screening intelligence and polish.

| Phase | Duration | Deliverables |
|---|---|---|
| **Phase 1** | 2–3 weeks | **Core pipeline & basic UI:** Docker Compose setup, PDF download + parse + enrich, DuckDB storage, basic sortable/filterable data table, individual sukuk detail page, APScheduler for daily ingestion. |
| **Phase 2** | 1–2 weeks | **Screening & comparison:** Compound filter builder with AND logic, portfolio/comparison view for 2–5 sukuk, diversification indicators, saved screener presets, CSV export. |
| **Phase 3** | 1–2 weeks | **Charts, news & polish:** TradingView Lightweight Charts for price/yield history, RSS news integration, mobile responsive polish, error handling hardening, documentation. |

---

*— End of Document —*
