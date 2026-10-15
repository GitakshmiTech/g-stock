# NSE Market Data Pipeline (2001–2026)

A production-grade Python 3.12+ and MySQL 8.0+ historical market data downloader and automated End-of-Day (EOD) ingestion platform for the National Stock Exchange of India (NSE).

Designed as a modular market data platform with traceable ingestion audit logs, duplicate prevention, multi-format parsing (Legacy Bhavcopy & modern UDiFF), security master management, corporate actions, data validation, and future paid feed extensibility.

---

## Key Features

- **Historical Backfill (2001–2026)**: Resumable, batch-oriented historical backfill with exchange calendar awareness (weekends & holidays).
- **Automated Daily EOD Updater (4:00 PM IST)**: Asia/Kolkata timezone scheduled ingestion with bounded exponential backoff retries for publication delays.
- **Multi-Format Parsers**: Transparent parsing of Legacy Bhavcopy (`cmDDMMMYYYYbhav.csv.zip`) and modern UDiFF Bhavcopy (`BhavCopy_NSE_CM_...`).
- **Data Quality & Validation**: OHLC integrity checking, zero/negative price guards, extreme price swing tracking, and duplicate rejection.
- **Security Master & Symbol History**: Longitudinal tracking of company ticker changes, ISINs, and series.
- **Idempotent MySQL Upsert**: High-performance bulk `ON DUPLICATE KEY UPDATE` preventing duplicate records upon reimport.
- **Audit Trail & Provenance**: SHA-256 checksums, row-level counts, and stage-by-stage ingestion logs.
- **REST API & Export Tooling**: FastAPI query service and CSV/Excel exporters.

---

## Technology Stack

- **Python**: 3.12+ (tested on Python 3.14)
- **Database**: MySQL 8.0+ (with SQLite fallback for local test execution)
- **ORM / SQL Toolkit**: SQLAlchemy 2.x, PyMySQL
- **Data Processing**: pandas, openpyxl
- **Networking & Retries**: httpx, tenacity
- **CLI**: Typer, Rich
- **API**: FastAPI, Pydantic 2.x
- **Scheduler**: APScheduler, launchd (macOS), systemd (Linux)
- **Testing**: pytest

---

## Directory Structure

```
nse_market_data_pipeline/
├── config/              # App, logging, and parser profile YAMLs
├── migrations/          # Versioned SQL migrations (001-004)
├── sql/                 # Supplementary and analytical SQL queries
├── src/nse_pipeline/    # Python source package
│   ├── api/             # FastAPI app and routes
│   ├── cli/             # Typer CLI commands
│   ├── clients/         # HTTP archive clients & paid feed stub
│   ├── core/            # Configuration, logging, clock, exceptions
│   ├── database/        # Connection, models, repositories, bulk upsert
│   ├── downloader/      # Download manager, resolvers, checksums
│   ├── normalization/   # Canonical field & date/numeric normalizers
│   ├── notifications/   # Email and alert managers
│   ├── parsers/         # Legacy & UDiFF archive parsers
│   ├── scheduler/       # APScheduler & trading calendar
│   ├── services/        # Backfill, daily update, ingestion, export
│   └── validation/      # Schema, price, and duplicate validators
├── tests/               # Unit and integration tests with fixtures
├── scripts/             # Operational and database scripts
├── deployment/          # Docker, launchd plist, systemd service
└── docs/                # Architecture and operations documentation
```

---

## Quickstart

### 1. Environment Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
cp .env.example .env
```

### 2. Initialize Database & Calendar
```bash
python -m nse_pipeline.cli.setup_database
```

### 3. Run Historical Backfill
```bash
# Backfill representative date range
python -m nse_pipeline.cli.backfill --start 2024-07-08 --end 2024-07-12
```

### 4. Run Daily EOD Ingestion
```bash
python -m nse_pipeline.cli.daily_update --date 2026-10-08
```

### 5. Start Daily Scheduler (4:00 PM IST)
```bash
python -m nse_pipeline.cli.commands start-scheduler
```

### 6. Start Financial Terminal & REST API
```bash
uvicorn nse_pipeline.api.app:app --host 0.0.0.0 --port 8000
```
- **Interactive Financial Analytics Terminal**: Navigate to [http://localhost:8000/dashboard](http://localhost:8000/dashboard) or [http://localhost:8000/](http://localhost:8000/) for the dark-navy terminal UI featuring:
  - **Market Overview**: Advances/Declines, turnover, traded volume, top gainers/losers.
  - **Stock Explorer**: Interactive Plotly candlestick charts with Volume subplots, SMA 20, SMA 50, and SMA 200 overlays.
  - **Seasonal Analysis**: Monthly return heatmaps (Year × Month), average monthly returns, and positive-month frequency win rates.
  - **Stock Comparison**: Multi-stock normalized performance (rebased to 100), cumulative returns, annualized volatility, and maximum drawdowns.
  - **Data Management**: Ingestion job logs, calendar audits, missing-date reconciliation, and manual backfill/update controls.
- **Interactive Swagger API Documentation**: Navigate to [http://localhost:8000/docs](http://localhost:8000/docs).

---

## React + TypeScript Frontend

The project includes a standalone modern financial analytics frontend built with React 19, TypeScript, Vite, and Plotly.js in `frontend/`:

```bash
cd frontend
npm install
npm run dev
```

The frontend connects directly to the FastAPI backend at `http://localhost:8000/api/v1` and provides:
- Clean light workspace with dark navy sidebar navigation
- Dynamic Stock Explorer with autocomplete search
- Seasonality matrix and interactive win rate gauges
- Cross-stock relative strength and drawdown charts
- Ingestion telemetry and data quality inspection

---

## Analytics Methodology

1. **Daily Return**:
   $$R_t = \left(\frac{P_t}{P_{t-1}} - 1\right) \times 100$$
2. **Monthly Seasonality**:
   Compares the first and last available closing prices within each calendar month across 2001–2026.
3. **Positive-Month Frequency (Win Rate)**:
   $$\text{Win Rate}_m = \left(\frac{\text{Years with } R_{y,m} > 0}{\text{Total Years}}\right) \times 100$$
4. **Annualized Volatility**:
   $$\sigma_{\text{ann}} = \text{std}(R_{\text{daily}}) \times \sqrt{252}$$
5. **Maximum Drawdown**:
   $$\text{MDD} = \min\left(\frac{P_t - \max_{\tau \le t} P_\tau}{\max_{\tau \le t} P_\tau}\right) \times 100$$

---

## Running with Docker Compose

```bash
docker compose up -d
```
Spins up MySQL 8.0, applies schema migrations, seeds the calendar, runs the 4:00 PM IST scheduler daemon, and launches the FastAPI service and Dashboard on port 8000.

# g-stock
