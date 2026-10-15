"""FastAPI application for the NSE Market Data Pipeline."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from nse_pipeline.api.routes import (
    analytics,
    auth,
    dashboard,
    health,
    ingestion,
    prices,
    securities,
    stocks,
    users,
    mongo,
)

app = FastAPI(
    title="NSE Market Data Platform API",
    description="Professional historical market data pipeline, analytics terminal & EOD updater.",
    version="2.0.0",
)

# Enable CORS for external React UI / local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(dashboard.router)
app.include_router(stocks.router)
app.include_router(analytics.router)
app.include_router(prices.router)
app.include_router(securities.router)
app.include_router(ingestion.router)
app.include_router(mongo.router)


@app.on_event("startup")
def startup_event():
    """Initializes tables, seeds default admin credentials, and starts daily scheduler."""
    import logging
    app_logger = logging.getLogger("nse_pipeline.api.app")

    from nse_pipeline.database.session import init_db, get_db_session
    from nse_pipeline.database.repositories.user_repository import UserRepository

    try:
        init_db()
        with get_db_session() as session:
            repo = UserRepository(session)
            repo.seed_default_admin()
    except Exception as e:
        app_logger.error(f"Error during database initialization/seeding: {e}")

    # Auto-hydrate SQL database from MongoDB if SQL is empty and MongoDB has data
    try:
        from nse_pipeline.services.mongo_sync_service import MongoSyncService
        sync_svc = MongoSyncService()
        sync_svc.ensure_sql_hydrated_from_mongo()
    except Exception as e:
        app_logger.warning(f"MongoDB auto-hydration check skipped: {e}")

    from nse_pipeline.scheduler.daily_scheduler import init_background_scheduler
    init_background_scheduler()


@app.get("/dashboard", response_class=HTMLResponse, tags=["Dashboard UI"])
@app.get("/", response_class=HTMLResponse, tags=["Dashboard UI"])
def render_terminal_ui():
    """Serves the standalone Financial Terminal UI connected to the backend API."""
    return get_terminal_html()


def get_terminal_html() -> str:
    """Returns the single-page Financial Analytics Terminal interface."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NSE Market Intelligence Terminal (2001–2028)</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      /* Default: Professional Clean White Institutional Theme */
      --bg-base: #f8fafc;
      --bg-surface: #ffffff;
      --bg-card: #ffffff;
      --bg-hover: #f1f5f9;
      --border: #e2e8f0;
      --border-subtle: #f1f5f9;
      --text-main: #0f172a;
      --text-muted: #64748b;
      --text-dim: #94a3b8;
      --green: #16a34a;
      --green-glow: rgba(22, 163, 74, 0.12);
      --red: #dc2626;
      --red-glow: rgba(220, 38, 38, 0.12);
      --accent: #2563eb;
      --accent-hover: #1d4ed8;
      --gold: #d97706;
      --sidebar-w: 260px;
      --table-th-bg: #f8fafc;
      --nav-active-bg: #eff6ff;
      --nav-active-color: #2563eb;
      --card-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);

      /* Heatmap Tiles */
      --tile-pos-bg: #dcfce7;
      --tile-pos-color: #15803d;
      --tile-pos-border: #bbf7d0;
      --tile-neg-bg: #fee2e2;
      --tile-neg-color: #b91c1c;
      --tile-neg-border: #fecaca;
      --tile-summary-bg: #f1f5f9;
      --tile-summary-color: #0f172a;
      --tile-win-bg: #e0f2fe;
      --tile-win-color: #0369a1;
    }

    [data-theme="dark"] {
      --bg-base: #0b0f19;
      --bg-surface: #111827;
      --bg-card: #162032;
      --bg-hover: #1f2d47;
      --border: #24344d;
      --border-subtle: #1c2b42;
      --text-main: #f3f4f6;
      --text-muted: #9ca3af;
      --text-dim: #6b7280;
      --green: #10b981;
      --green-glow: rgba(16, 185, 129, 0.2);
      --red: #ef4444;
      --red-glow: rgba(239, 68, 68, 0.2);
      --accent: #3b82f6;
      --accent-hover: #2563eb;
      --gold: #f59e0b;
      --table-th-bg: #151d2e;
      --nav-active-bg: #1e3a5f;
      --nav-active-color: #60a5fa;
      --card-shadow: none;

      /* Heatmap Tiles */
      --tile-pos-bg: #064e3b;
      --tile-pos-color: #6ee7b7;
      --tile-pos-border: #047857;
      --tile-neg-bg: #7f1d1d;
      --tile-neg-color: #fca5a5;
      --tile-neg-border: #991b1b;
      --tile-summary-bg: #334155;
      --tile-summary-color: #f8fafc;
      --tile-win-bg: #1e293b;
      --tile-win-color: #38bdf8;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background-color: var(--bg-base);
      color: var(--text-main);
      display: flex;
      height: 100vh;
      overflow: hidden;
      -webkit-font-smoothing: antialiased;
    }

    /* Terminal Sidebar */
    .sidebar {
      width: var(--sidebar-w);
      background-color: var(--bg-surface);
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      flex-shrink: 0;
    }

    .brand {
      padding: 20px;
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .brand-badge {
      background: linear-gradient(135deg, #2563eb, #10b981);
      color: #fff;
      font-weight: 700;
      font-size: 14px;
      padding: 6px 10px;
      border-radius: 6px;
      font-family: 'JetBrains Mono', monospace;
      letter-spacing: 0.5px;
    }

    .brand-title {
      font-size: 14px;
      font-weight: 700;
      letter-spacing: 0.5px;
      color: #fff;
    }
    .brand-subtitle {
      font-size: 11px;
      color: var(--text-dim);
      font-family: 'JetBrains Mono', monospace;
    }

    .nav-links {
      list-style: none;
      padding: 16px 12px;
      display: flex;
      flex-direction: column;
      gap: 4px;
      flex: 1;
    }

    .nav-item {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 10px 14px;
      border-radius: 6px;
      cursor: pointer;
      color: var(--text-muted);
      font-size: 13px;
      font-weight: 500;
      transition: all 0.15s ease;
    }

    .nav-item:hover {
      background-color: var(--bg-hover);
      color: var(--text-main);
    }

    .nav-item.active {
      background-color: #1e3a5f;
      color: #60a5fa;
      font-weight: 600;
      border-left: 3px solid #3b82f6;
    }

    .sidebar-footer {
      padding: 16px;
      border-top: 1px solid var(--border);
      font-size: 11px;
      color: var(--text-dim);
      font-family: 'JetBrains Mono', monospace;
    }

    /* Main Content Area */
    .main {
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow-y: auto;
      background-color: var(--bg-base);
    }

    .topbar {
      height: 60px;
      background-color: var(--bg-surface);
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 24px;
      flex-shrink: 0;
    }

    .topbar-left {
      display: flex;
      align-items: center;
      gap: 16px;
    }

    .badge-status {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background-color: rgba(16, 185, 129, 0.12);
      color: var(--green);
      border: 1px solid rgba(16, 185, 129, 0.3);
      padding: 4px 10px;
      border-radius: 9999px;
      font-size: 11px;
      font-family: 'JetBrains Mono', monospace;
    }

    .status-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background-color: var(--green);
      box-shadow: 0 0 8px var(--green);
    }

    .workspace {
      padding: 24px;
      flex: 1;
      max-width: 1440px;
      margin: 0 auto;
      width: 100%;
    }

    /* Grid & Cards */
    .metrics-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }

    .card {
      background-color: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 18px 20px;
      position: relative;
    }

    .card-label {
      font-size: 12px;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 6px;
      font-family: 'JetBrains Mono', monospace;
    }

    .card-value {
      font-size: 24px;
      font-weight: 700;
      color: #fff;
      font-family: 'JetBrains Mono', monospace;
    }

    .card-subtext {
      font-size: 11px;
      color: var(--text-dim);
      margin-top: 4px;
    }

    .section-title {
      font-size: 16px;
      font-weight: 600;
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .chart-container {
      background-color: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 24px;
    }

    /* Tables */
    .table-container {
      background-color: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow: hidden;
      margin-bottom: 24px;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      text-align: left;
    }

    th {
      background-color: #151d2e;
      color: var(--text-muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      padding: 12px 16px;
      border-bottom: 1px solid var(--border);
      font-family: 'JetBrains Mono', monospace;
    }

    td {
      padding: 12px 16px;
      border-bottom: 1px solid var(--border-subtle);
      color: var(--text-main);
    }

    tr:hover td {
      background-color: var(--bg-hover);
    }

    .gainer-tag {
      color: var(--green);
      font-family: 'JetBrains Mono', monospace;
      font-weight: 600;
    }

    .loser-tag {
      color: var(--red);
      font-family: 'JetBrains Mono', monospace;
      font-weight: 600;
    }

    /* Search & Inputs */
    .search-input {
      background-color: var(--bg-card);
      border: 1px solid var(--border);
      color: var(--text-main);
      padding: 8px 14px;
      border-radius: 6px;
      font-size: 13px;
      outline: none;
      font-family: 'Inter', sans-serif;
    }
    .search-input:focus {
      border-color: var(--accent);
    }

    .btn {
      background-color: var(--accent);
      color: #fff;
      border: none;
      padding: 8px 16px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: background-color 0.15s;
    }
    .btn:hover {
      background-color: var(--accent-hover);
    }

    .btn-outline {
      background-color: transparent;
      border: 1px solid var(--border);
      color: var(--text-main);
    }
    .btn-outline:hover {
      background-color: var(--bg-hover);
    }

    .tab-pane {
      display: none;
    }
    .tab-pane.active {
      display: block;
    }

    /* Seasonal Matrix Styles */
    .period-pill-group {
      display: inline-flex;
      background-color: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 3px;
      gap: 3px;
    }
    .period-pill-btn {
      border: none;
      background: transparent;
      color: var(--text-muted);
      font-size: 12px;
      font-weight: 500;
      padding: 7px 14px;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.18s ease;
      font-family: 'Inter', sans-serif;
    }
    .period-pill-btn:hover {
      color: var(--text-main);
      background-color: rgba(255, 255, 255, 0.05);
    }
    .period-pill-btn.active {
      background-color: #ffffff;
      color: #0f172a;
      font-weight: 600;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
    }
    .seasonal-matrix-table {
      width: 100%;
      border-collapse: separate;
      border-spacing: 5px 6px;
      min-width: 900px;
    }
    .seasonal-matrix-table th {
      padding: 10px 8px;
      color: var(--text-muted);
      font-size: 12px;
      font-weight: 600;
      text-align: center;
      text-transform: capitalize;
    }
    .seasonal-matrix-table th.time-th {
      text-align: left;
      padding-left: 12px;
      width: 70px;
      font-weight: 700;
    }
    .matrix-row-year {
      font-family: 'JetBrains Mono', monospace;
      font-size: 13px;
      font-weight: 700;
      color: var(--text-main);
      padding: 8px 12px;
      text-align: left;
    }
    .matrix-tile {
      text-align: center;
      padding: 11px 4px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      font-weight: 600;
      border-radius: 5px;
      transition: transform 0.15s ease;
      user-select: none;
    }
    .matrix-tile:hover {
      transform: translateY(-2px);
      box-shadow: 0 4px 10px rgba(0,0,0,0.4);
    }
    .tile-positive {
      background-color: #34d399;
      color: #064e3b;
      font-weight: 700;
    }
    .tile-negative {
      background-color: #f87171;
      color: #7f1d1d;
      font-weight: 700;
    }
    .tile-empty {
      background-color: rgba(255, 255, 255, 0.02);
      border: 1.5px solid rgba(255, 255, 255, 0.12);
      color: transparent;
    }
    .matrix-summary-label {
      font-size: 13px;
      font-weight: 700;
      color: var(--text-main);
      padding: 8px 12px;
      text-align: left;
    }
    .matrix-summary-tile {
      background-color: #94a3b8;
      color: #0f172a;
      text-align: center;
      padding: 10px 4px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      font-weight: 700;
      border-radius: 5px;
    }
    .matrix-winrate-tile {
      background-color: #334155;
      color: #38bdf8;
      text-align: center;
      padding: 10px 4px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      font-weight: 700;
      border-radius: 5px;
    }
    .seasonal-filter-panel {
      background-color: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px 16px;
      margin-bottom: 20px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .filter-row {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 14px;
    }
    .filter-label-group {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 11px;
      font-weight: 700;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      min-width: 140px;
    }
    .filter-pills-row {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 6px;
    }
    .filter-chip-btn {
      border: 1px solid var(--border);
      background-color: rgba(255, 255, 255, 0.03);
      color: var(--text-muted);
      font-size: 11px;
      font-weight: 600;
      padding: 5px 12px;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s ease;
      font-family: 'Inter', sans-serif;
    }
    .filter-chip-btn:hover {
      background-color: rgba(255, 255, 255, 0.08);
      color: var(--text-main);
      border-color: #3b82f6;
    }
    .filter-chip-btn.active {
      background-color: var(--accent);
      color: #ffffff;
      border-color: var(--accent);
      box-shadow: 0 1px 6px rgba(59, 130, 246, 0.35);
    }
    .filter-num-input {
      background-color: var(--bg-surface);
      border: 1px solid var(--border);
      color: var(--text-main);
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      font-weight: 600;
      padding: 5px 8px;
      border-radius: 6px;
      width: 76px;
      outline: none;
    }
    .filter-num-input:focus { border-color: var(--accent); }
    .filter-stats-badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 4px 10px;
      border-radius: 6px;
      background-color: rgba(59, 130, 246, 0.12);
      border: 1px solid rgba(59, 130, 246, 0.3);
      color: #93c5fd;
      font-size: 11px;
      font-family: 'JetBrains Mono', monospace;
      font-weight: 600;
    }
    .filter-reset-btn {
      background: transparent;
      border: 1px solid var(--border);
      color: var(--text-dim);
      font-size: 11px;
      font-weight: 600;
      padding: 5px 12px;
      border-radius: 6px;
      cursor: pointer;
    }
    .filter-reset-btn:hover {
      color: var(--red);
      border-color: var(--red);
      background-color: rgba(239, 68, 68, 0.1);
    }
    .matrix-tile.tile-dimmed {
      opacity: 0.18;
      filter: grayscale(80%);
      transform: none !important;
      box-shadow: none !important;
    }
    .matrix-tile.tile-highlighted {
      box-shadow: 0 0 10px rgba(52, 211, 153, 0.65);
      transform: scale(1.03);
      z-index: 2;
      position: relative;
    }
    .matrix-tile.tile-filtered-out {
      background-color: rgba(255, 255, 255, 0.02) !important;
      border: 1px dashed rgba(255, 255, 255, 0.1) !important;
      color: transparent !important;
      box-shadow: none !important;
    }
  </style>
</head>
<body>

  <!-- Sidebar -->
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-badge">NSE</div>
      <div>
        <div class="brand-title">ANALYTICS TERMINAL</div>
        <div class="brand-subtitle">MARKET INTELLIGENCE</div>
      </div>
    </div>

    <ul class="nav-links">
      <li class="nav-item active" onclick="switchTab('dashboard')">
        <span>📊</span> <span>Main Dashboard</span>
      </li>
      <li class="nav-item" onclick="switchTab('explorer')">
        <span>📈</span> <span>Stock Explorer</span>
      </li>
      <li class="nav-item" onclick="switchTab('seasonality')">
        <span>📅</span> <span>Seasonal Analysis</span>
      </li>
      <li class="nav-item" onclick="switchTab('comparison')">
        <span>⚖️</span> <span>Stock Comparison</span>
      </li>
      <li class="nav-item" onclick="switchTab('data-mgmt')">
        <span>⚙️</span> <span>Data Management</span>
      </li>
    </ul>

    <div class="sidebar-footer">
      <div>SCHEDULE: 16:00 IST</div>
      <div style="margin-top: 4px;">MYSQL: 8.0+ PERSISTENT</div>
    </div>
  </aside>

  <!-- Main Content -->
  <main class="main">
    <div class="topbar">
      <div class="topbar-left">
        <div class="badge-status">
          <div class="status-dot"></div>
          <span id="top-status">EOD FEED: ACTIVE</span>
        </div>
        <span style="font-size: 13px; color: var(--text-muted); font-family: 'JetBrains Mono', monospace;" id="top-date-banner">
          LATEST TRADED DATE: LOADING...
        </span>
      </div>
      <div style="display: flex; align-items: center; gap: 10px;">
        <button class="btn btn-outline" id="theme-btn" onclick="toggleAppTheme()">🌙 Dark Mode</button>
        <button class="btn btn-outline" onclick="loadDashboardData()">↻ Refresh</button>
      </div>
    </div>

    <div class="workspace">

      <!-- 1. MAIN DASHBOARD TAB -->
      <div id="tab-dashboard" class="tab-pane active">
        <div class="metrics-grid">
          <div class="card">
            <div class="card-label">Securities Tracked</div>
            <div class="card-value" id="m-securities">--</div>
            <div class="card-subtext">Active equity master</div>
          </div>
          <div class="card">
            <div class="card-label">Market Advances / Declines</div>
            <div class="card-value" id="m-adv-dec">-- / --</div>
            <div class="card-subtext"><span class="gainer-tag" id="m-adv">--</span> vs <span class="loser-tag" id="m-dec">--</span></div>
          </div>
          <div class="card">
            <div class="card-label">Daily Turnover</div>
            <div class="card-value" id="m-turnover">--</div>
            <div class="card-subtext">Gross equity segment turnover</div>
          </div>
          <div class="card">
            <div class="card-label">Traded Volume</div>
            <div class="card-value" id="m-volume">--</div>
            <div class="card-subtext">Total traded shares</div>
          </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
          <div>
            <div class="section-title">🚀 Top Market Gainers</div>
            <div class="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Close Price</th>
                    <th>Prev Close</th>
                    <th>Change %</th>
                  </tr>
                </thead>
                <tbody id="tbl-gainers"><tr><td colspan="4">Loading gainers...</td></tr></tbody>
              </table>
            </div>
          </div>

          <div>
            <div class="section-title">📉 Top Market Losers</div>
            <div class="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Close Price</th>
                    <th>Prev Close</th>
                    <th>Change %</th>
                  </tr>
                </thead>
                <tbody id="tbl-losers"><tr><td colspan="4">Loading losers...</td></tr></tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <!-- 2. STOCK EXPLORER TAB -->
      <div id="tab-explorer" class="tab-pane">
        <div style="display: flex; gap: 12px; margin-bottom: 20px; align-items: center;">
          <input type="text" id="explorer-symbol" class="search-input" value="RELIANCE" placeholder="Enter symbol (e.g. TCS, INFY)" style="width: 240px; text-transform: uppercase;">
          <button class="btn" onclick="loadStockChart()">Load Chart</button>
        </div>

        <div class="metrics-grid" id="explorer-metrics" style="display: none;">
          <div class="card">
            <div class="card-label">Latest Close</div>
            <div class="card-value" id="exp-close">--</div>
          </div>
          <div class="card">
            <div class="card-label">Total Return</div>
            <div class="card-value" id="exp-return">--</div>
          </div>
          <div class="card">
            <div class="card-label">Annualized Volatility</div>
            <div class="card-value" id="exp-vol">--</div>
          </div>
          <div class="card">
            <div class="card-label">Max Drawdown</div>
            <div class="card-value" id="exp-dd">--</div>
          </div>
        </div>

        <div class="chart-container">
          <div id="plot-candlestick" style="height: 480px;"></div>
        </div>
        <div class="chart-container">
          <div id="plot-volume" style="height: 220px;"></div>
        </div>
      </div>

      <!-- 3. SEASONAL ANALYSIS TAB -->
      <div id="tab-seasonality" class="tab-pane">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px; margin-bottom: 20px;">
          <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
            <select id="season-quick-select" class="search-input" style="min-width: 320px; max-width: 440px; font-weight: 700; font-family: 'JetBrains Mono';" onchange="document.getElementById('season-symbol').value = this.value; loadSeasonalityChart();">
              <option value="RELIANCE">RELIANCE — Reliance Industries Limited</option>
              <option value="TCS">TCS — Tata Consultancy Services Limited</option>
              <option value="INFY">INFY — Infosys Limited</option>
              <option value="HDFCBANK">HDFCBANK — HDFC Bank Limited</option>
              <option value="ICICIBANK">ICICIBANK — ICICI Bank Limited</option>
              <option value="TATAMOTORS">TATAMOTORS — Tata Motors Limited</option>
              <option value="SBIN">SBIN — State Bank of India</option>
              <option value="SECURKLOUD">SECURKLOUD — SecureKloud Technologies Limited</option>
            </select>
            <input type="text" id="season-search-box" class="filter-num-input" placeholder="🔍 Search stock / company..." style="width: 210px;" oninput="filterSeasonSecurities(this.value)">
            <input type="text" id="season-symbol" class="search-input" value="RELIANCE" placeholder="Symbol" style="width: 110px; text-transform: uppercase;">
            <button class="btn" onclick="loadSeasonalityChart()">Analyze</button>
          </div>

          <div class="period-pill-group">
            <button id="p-pill-weekly" class="period-pill-btn" onclick="setSeasonPeriod('weekly')">Weekly returns(%)</button>
            <button id="p-pill-monthly" class="period-pill-btn active" onclick="setSeasonPeriod('monthly')">Monthly returns(%)</button>
            <button id="p-pill-quarterly" class="period-pill-btn" onclick="setSeasonPeriod('quarterly')">Quarterly returns(%)</button>
          </div>
        </div>

        <!-- Interactive Date & Return % Filter Toolbar -->
        <div class="seasonal-filter-panel">
          <!-- A. DATE FILTER ROW WITH CUSTOM DATE PICKER -->
          <div class="filter-row">
            <div class="filter-label-group"><span>📅 Date Filter:</span></div>
            <div class="filter-pills-row">
              <button class="filter-chip-btn active" id="btn-yr-all" onclick="setAppYearPreset('all')">All Years</button>
              <button class="filter-chip-btn" id="btn-yr-last3" onclick="setAppYearPreset('last3')">Last 3Y</button>
              <button class="filter-chip-btn" id="btn-yr-last5" onclick="setAppYearPreset('last5')">Last 5Y</button>
              <button class="filter-chip-btn" id="btn-yr-last10" onclick="setAppYearPreset('last10')">Last 10Y</button>
              <button class="filter-chip-btn" id="btn-yr-2020" onclick="setAppYearPreset('2020-2024')">2020–2024</button>
            </div>
            <div style="display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-muted);">
              <span>From Yr:</span>
              <select id="season-from-year" class="filter-num-input" style="width: 85px;" onchange="onAppYearChange()">
                <option value="">Start</option>
              </select>
              <span>To Yr:</span>
              <select id="season-to-year" class="filter-num-input" style="width: 85px;" onchange="onAppYearChange()">
                <option value="">End</option>
              </select>
            </div>

            <!-- Custom Date Picker -->
            <div style="display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-muted); border-left: 1px solid var(--border); padding-left: 10px;">
              <span>From Date:</span>
              <input type="date" id="season-from-date" class="filter-num-input" style="width: 135px;">
              <span>To Date:</span>
              <input type="date" id="season-to-date" class="filter-num-input" style="width: 135px;">
              <button class="filter-chip-btn active" style="padding: 4px 10px;" onclick="applyAppCustomDates()">Apply Range</button>
            </div>
          </div>

          <!-- B. RETURN % FILTER ROW -->
          <div class="filter-row">
            <div class="filter-label-group"><span>⚡ Return % Filter:</span></div>
            <div class="filter-pills-row">
              <button class="filter-chip-btn active" id="btn-ret-all" onclick="setAppReturnPreset('all')">All Returns</button>
              <button class="filter-chip-btn" id="btn-ret-pos" onclick="setAppReturnPreset('pos')">Gains (&gt; 0%)</button>
              <button class="filter-chip-btn" id="btn-ret-neg" onclick="setAppReturnPreset('neg')">Losses (&lt; 0%)</button>
              <button class="filter-chip-btn" id="btn-ret-gain5" onclick="setAppReturnPreset('gain5')">Big Gains (≥ +5%)</button>
              <button class="filter-chip-btn" id="btn-ret-loss5" onclick="setAppReturnPreset('loss5')">Big Losses (≤ -5%)</button>
              <button class="filter-chip-btn" id="btn-ret-extreme" onclick="setAppReturnPreset('extreme')">Extreme (|Ret| ≥ 10%)</button>
            </div>
            <div style="display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-muted);">
              <span>Min %:</span>
              <input type="number" step="0.5" id="season-min-ret" placeholder="-5.0" class="filter-num-input" oninput="onAppReturnCustomChange()">
              <span>Max %:</span>
              <input type="number" step="0.5" id="season-max-ret" placeholder="10.0" class="filter-num-input" oninput="onAppReturnCustomChange()">
            </div>
            <div style="display: flex; align-items: center; gap: 6px; font-size: 12px;">
              <span style="color: var(--text-muted);">Mode:</span>
              <button class="filter-chip-btn active" id="btn-mode-dim" onclick="setAppFilterMode('dim')">Dim Non-Match</button>
              <button class="filter-chip-btn" id="btn-mode-hide" onclick="setAppFilterMode('hide')">Hide Non-Match</button>
            </div>
          </div>

          <!-- C. LIVE FILTER STATS BADGE & RESET -->
          <div id="season-filter-stats-bar" style="display: none; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; border-top: 1px solid var(--border); padding-top: 10px;">
            <div class="filter-stats-badge" id="season-filter-stats-text">
              🎯 Matched: --
            </div>
            <button class="filter-reset-btn" onclick="resetAppSeasonFilters()">✕ Reset All Filters</button>
          </div>
        </div>

        <div class="chart-container" style="overflow-x: auto; padding: 20px 16px;">
          <div class="section-title" id="season-table-title">📊 Monthly Returns Matrix (%)</div>
          <table class="seasonal-matrix-table" id="tbl-season-matrix">
            <thead id="tbl-season-head">
              <tr>
                <th class="time-th">Time</th>
                <th>January</th><th>February</th><th>March</th><th>April</th><th>May</th><th>June</th>
                <th>July</th><th>August</th><th>September</th><th>October</th><th>November</th><th>December</th>
              </tr>
            </thead>
            <tbody id="tbl-season-body">
              <tr><td colspan="13" style="text-align: center; padding: 20px; color: var(--text-dim);">Loading seasonal performance matrix...</td></tr>
            </tbody>
            <tfoot id="tbl-season-foot"></tfoot>
          </table>
        </div>

        <div class="chart-container">
          <div class="section-title">📅 Average Historical Seasonality (%)</div>
          <div id="plot-seasonality" style="height: 380px;"></div>
        </div>
      </div>

      <!-- 4. STOCK COMPARISON TAB -->
      <div id="tab-comparison" class="tab-pane">
        <div style="display: flex; gap: 12px; margin-bottom: 12px; align-items: center; flex-wrap: wrap;">
          <input type="text" id="compare-symbols" class="search-input" value="RELIANCE,TCS,INFY" placeholder="Comma-separated symbols" style="width: 280px; text-transform: uppercase;">
          <button class="btn" onclick="loadComparisonChart()">Compare Performance</button>
        </div>

        <!-- Date Range Filter & Quick Presets -->
        <div style="background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; margin-bottom: 20px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;">
          <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
            <span style="font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-right: 4px;">📅 Presets:</span>
            <button class="btn btn-outline" style="padding: 4px 8px; font-size: 11px;" onclick="setComparePreset('all')">All (2001–2026)</button>
            <button class="btn btn-outline" style="padding: 4px 8px; font-size: 11px;" onclick="setComparePreset('1y')">Last 1Y</button>
            <button class="btn btn-outline" style="padding: 4px 8px; font-size: 11px;" onclick="setComparePreset('3y')">Last 3Y</button>
            <button class="btn btn-outline" style="padding: 4px 8px; font-size: 11px;" onclick="setComparePreset('5y')">Last 5Y</button>
            <button class="btn btn-outline" style="padding: 4px 8px; font-size: 11px;" onclick="setComparePreset('2020-2024')">2020–2024</button>
            <button class="btn btn-outline" style="padding: 4px 8px; font-size: 11px;" onclick="setComparePreset('ytd')">YTD (2026)</button>
          </div>

          <div style="display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-muted); border-left: 1px solid var(--border); padding-left: 14px; flex-wrap: wrap;">
            <span style="font-weight: 600;">From Date:</span>
            <input type="date" id="compare-from" class="search-input" style="width: 135px; padding: 4px 8px; color-scheme: dark;" value="">
            <span style="font-weight: 600;">To Date:</span>
            <input type="date" id="compare-to" class="search-input" style="width: 135px; padding: 4px 8px; color-scheme: dark;" value="">
            <button class="btn" style="padding: 4px 10px; font-size: 11px;" onclick="loadComparisonChart()">Apply Range</button>
            <button class="btn btn-outline" style="padding: 4px 8px; font-size: 11px; color: #ef4444;" onclick="resetCompareDates()">✕ Clear</button>
          </div>
        </div>

        <div class="chart-container">
          <div class="section-title">⚖️ Normalized Price Performance (Base = 100)</div>
          <div id="plot-comparison" style="height: 450px;"></div>
        </div>

        <div class="section-title">Comparison Statistics</div>
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Base Price</th>
                <th>Latest Close</th>
                <th>Cumulative Return %</th>
                <th>Volatility (Ann.)</th>
                <th>Max Drawdown</th>
              </tr>
            </thead>
            <tbody id="tbl-compare-stats"><tr><td colspan="6">Click compare to view metrics...</td></tr></tbody>
          </table>
        </div>
      </div>

      <!-- 5. DATA MANAGEMENT TAB -->
      <div id="tab-data-mgmt" class="tab-pane">
        <div class="section-title">⚙️ Automated 4:00 PM EOD Scheduler & Ingestion Controls</div>
        <div style="background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 16px 20px; margin-bottom: 24px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px;">
          <div>
            <div style="font-weight: 700; color: #10b981; font-size: 14px; display: flex; align-items: center; gap: 8px;">
              <span style="display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #10b981; box-shadow: 0 0 8px #10b981;"></span>
              Automated 4:00 PM EOD Scheduler: ACTIVE
            </div>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;" id="sched-status-subtext">
              Scheduled Daily Ingestion: <b>16:00 IST</b> • Next Run: <b>Today at 4:00 PM IST (16:00:00)</b>
            </div>
          </div>
          <div style="display: flex; gap: 12px;">
            <button class="btn" onclick="triggerDailyUpdate()">⚡ Trigger EOD Update Now</button>
            <button class="btn btn-outline" onclick="loadIngestionJobs()">Refresh Jobs List</button>
          </div>
        </div>

        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>Job ID</th>
                <th>Job Type</th>
                <th>Status</th>
                <th>Total Dates</th>
                <th>Rows Imported</th>
                <th>Started At</th>
                <th>Completed At</th>
              </tr>
            </thead>
            <tbody id="tbl-jobs"><tr><td colspan="7">Loading jobs...</td></tr></tbody>
          </table>
        </div>
      </div>

    </div>
  </main>

  <script>
    function getPlotlyThemeLayout() {
      const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
      return {
        paper_bgcolor: isDark ? '#111827' : '#ffffff',
        plot_bgcolor: isDark ? '#111827' : '#ffffff',
        font: { color: isDark ? '#9ca3af' : '#475569', family: 'JetBrains Mono' },
        gridcolor: isDark ? '#1f2d47' : '#f1f5f9'
      };
    }

    function toggleAppTheme() {
      const cur = document.documentElement.getAttribute('data-theme') || 'light';
      const nxt = cur === 'light' ? 'dark' : 'light';
      document.documentElement.setAttribute('data-theme', nxt);
      localStorage.setItem('nse_app_theme', nxt);
      const btn = document.getElementById('theme-btn');
      if (btn) btn.innerHTML = nxt === 'light' ? '🌙 Dark Mode' : '☀️ Light Mode';

      const activeTabEl = document.querySelector('.tab-pane.active');
      if (activeTabEl) {
        const id = activeTabEl.id.replace('tab-', '');
        if (id === 'explorer') loadStockChart();
        if (id === 'seasonality') loadSeasonalityTable();
        if (id === 'comparison') loadComparisonChart();
      }
    }

    // Init theme
    (function initTheme() {
      const saved = localStorage.getItem('nse_app_theme') || 'light';
      document.documentElement.setAttribute('data-theme', saved);
      window.addEventListener('DOMContentLoaded', () => {
        const btn = document.getElementById('theme-btn');
        if (btn) btn.innerHTML = saved === 'light' ? '🌙 Dark Mode' : '☀️ Light Mode';
      });
    })();
    function switchTab(tabName) {
      document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
      document.getElementById('tab-' + tabName).classList.add('active');

      const idx = ['dashboard', 'explorer', 'seasonality', 'comparison', 'data-mgmt'].indexOf(tabName);
      if (idx >= 0) {
        document.querySelectorAll('.nav-item')[idx].classList.add('active');
      }

      if (tabName === 'explorer') loadStockChart();
      if (tabName === 'seasonality') loadSeasonalityChart();
      if (tabName === 'comparison') loadComparisonChart();
      if (tabName === 'data-mgmt') loadIngestionJobs();
    }

    async function loadDashboardData() {
      try {
        const res = await fetch('/api/v1/dashboard/summary');
        const data = await res.json();

        document.getElementById('m-securities').innerText = data.total_securities_count.toLocaleString();
        document.getElementById('m-adv-dec').innerText = `${data.advances} / ${data.declines}`;
        document.getElementById('m-adv').innerText = `+${data.advances} Adv`;
        document.getElementById('m-dec').innerText = `-${data.declines} Dec`;
        document.getElementById('m-turnover').innerText = '₹' + (data.total_turnover / 1e7).toFixed(2) + ' Cr';
        document.getElementById('m-volume').innerText = (data.total_volume / 1e6).toFixed(2) + ' M';

        if (data.latest_date) {
          document.getElementById('top-date-banner').innerText = `LATEST TRADED DATE: ${data.latest_date}`;
        }

        // Render gainers
        const gBody = document.getElementById('tbl-gainers');
        gBody.innerHTML = (data.top_gainers || []).map(g => `
          <tr>
            <td><strong>${g.symbol}</strong></td>
            <td>₹${g.close_price.toFixed(2)}</td>
            <td>₹${g.prev_close.toFixed(2)}</td>
            <td class="gainer-tag">+${g.change_pct}%</td>
          </tr>
        `).join('') || '<tr><td colspan="4">No data</td></tr>';

        // Render losers
        const lBody = document.getElementById('tbl-losers');
        lBody.innerHTML = (data.top_losers || []).map(l => `
          <tr>
            <td><strong>${l.symbol}</strong></td>
            <td>₹${l.close_price.toFixed(2)}</td>
            <td>₹${l.prev_close.toFixed(2)}</td>
            <td class="loser-tag">${l.change_pct}%</td>
          </tr>
        `).join('') || '<tr><td colspan="4">No data</td></tr>';

      } catch (err) {
        console.error('Failed to load dashboard:', err);
      }
    }

    async function loadStockChart() {
      const sym = document.getElementById('explorer-symbol').value.trim().toUpperCase() || 'RELIANCE';
      try {
        const res = await fetch(`/api/v1/stocks/${sym}/prices`);
        const json = await res.json();
        const records = json.data || [];

        if (records.length === 0) {
          alert('No records found for ' + sym);
          return;
        }

        document.getElementById('explorer-metrics').style.display = 'grid';
        document.getElementById('exp-close').innerText = '₹' + json.summary.latest_close.toFixed(2);
        document.getElementById('exp-return').innerText = json.summary.total_return_pct + '%';
        document.getElementById('exp-vol').innerText = json.summary.annualized_volatility_pct + '%';
        document.getElementById('exp-dd').innerText = json.summary.max_drawdown_pct + '%';

        const dates = records.map(r => r.trade_date);
        const opens = records.map(r => r.open);
        const highs = records.map(r => r.high);
        const lows = records.map(r => r.low);
        const closes = records.map(r => r.close);
        const sma20 = records.map(r => r.sma_20);
        const sma50 = records.map(r => r.sma_50);
        const volumes = records.map(r => r.volume);

        const traceCandle = {
          x: dates, open: opens, high: highs, low: lows, close: closes,
          type: 'candlestick', name: sym,
          increasing: { line: { color: '#10b981' } },
          decreasing: { line: { color: '#ef4444' } }
        };

        const traceSMA20 = {
          x: dates, y: sma20, type: 'scatter', mode: 'lines', name: 'SMA 20',
          line: { color: '#f59e0b', width: 1.5 }
        };

        const traceSMA50 = {
          x: dates, y: sma50, type: 'scatter', mode: 'lines', name: 'SMA 50',
          line: { color: '#3b82f6', width: 1.5 }
        };

        const candleLayout = {
          title: `${sym} OHLC Price & Moving Averages`,
          paper_bgcolor: '#111827', plot_bgcolor: '#111827',
          font: { color: '#9ca3af', family: 'JetBrains Mono' },
          xaxis: { rangeslider: { visible: false }, gridcolor: '#1f2d47' },
          yaxis: { gridcolor: '#1f2d47' },
          margin: { t: 40, r: 20, l: 50, b: 30 }
        };

        Plotly.newPlot('plot-candlestick', [traceCandle, traceSMA20, traceSMA50], candleLayout, {responsive: true});

        const traceVol = {
          x: dates, y: volumes, type: 'bar', name: 'Volume',
          marker: { color: '#3b82f6' }
        };
        const volLayout = {
          title: 'Daily Traded Volume',
          paper_bgcolor: '#111827', plot_bgcolor: '#111827',
          font: { color: '#9ca3af', family: 'JetBrains Mono' },
          xaxis: { gridcolor: '#1f2d47' },
          yaxis: { gridcolor: '#1f2d47' },
          margin: { t: 30, r: 20, l: 50, b: 30 }
        };
        Plotly.newPlot('plot-volume', [traceVol], volLayout, {responsive: true});

      } catch (err) {
        console.error('Failed to load chart:', err);
      }
    }

    let currentSeasonPeriod = 'monthly';
    let cachedSeasonData = null;
    let appYearPreset = 'all';
    let appStartYear = null;
    let appEndYear = null;
    let appReturnPreset = 'all';
    let appMinReturn = null;
    let appMaxReturn = null;
    let appFilterMode = 'dim';
    let allAppSecurities = [];

    async function loadSecuritiesDropdown() {
      try {
        const res = await fetch('/api/v1/securities?limit=5000');
        allAppSecurities = await res.json();
        renderSecuritiesOptions(allAppSecurities);
      } catch (err) {
        console.error('Failed to load securities dropdown:', err);
      }
    }

    function renderSecuritiesOptions(list) {
      const sel = document.getElementById('season-quick-select');
      if (!sel) return;
      const currentVal = document.getElementById('season-symbol').value || 'RELIANCE';
      sel.innerHTML = (list || []).map(s => {
        const label = s.company_name ? `${s.symbol} — ${s.company_name}` : s.symbol;
        const isSel = s.symbol === currentVal ? 'selected' : '';
        return `<option value="${s.symbol}" ${isSel}>${label}</option>`;
      }).join('');
    }

    function filterSeasonSecurities(query) {
      if (!allAppSecurities || allAppSecurities.length === 0) return;
      const q = (query || '').trim().toUpperCase();
      const filtered = q ? allAppSecurities.filter(s => 
        s.symbol.toUpperCase().includes(q) || (s.company_name && s.company_name.toUpperCase().includes(q))
      ) : allAppSecurities;
      renderSecuritiesOptions(filtered);
    }

    function setSeasonPeriod(period) {
      currentSeasonPeriod = period;
      document.querySelectorAll('.period-pill-btn').forEach(btn => btn.classList.remove('active'));
      const activeBtn = document.getElementById(`p-pill-${period}`);
      if (activeBtn) activeBtn.classList.add('active');
      if (cachedSeasonData) renderSeasonalMatrix(cachedSeasonData);
    }

    function getRawSeasonRows(data) {
      if (currentSeasonPeriod === 'weekly' && data.weekly) return data.weekly.rows || [];
      if (currentSeasonPeriod === 'quarterly' && data.quarterly) return data.quarterly.rows || [];
      if (data.monthly && data.monthly.rows) return data.monthly.rows;
      return (data.heatmap || []).map(r => ({
        year: r.year,
        January: r.Jan, February: r.Feb, March: r.Mar, April: r.Apr, May: r.May, June: r.Jun,
        July: r.Jul, August: r.Aug, September: r.Sep, October: r.Oct, November: r.Nov, December: r.Dec
      }));
    }

    function setAppYearPreset(preset) {
      appYearPreset = preset;
      document.querySelectorAll('#tab-seasonality .filter-row:first-child .filter-chip-btn').forEach(b => b.classList.remove('active'));
      const btn = document.getElementById(`btn-yr-${preset}`);
      if (btn) btn.classList.add('active');

      if (!cachedSeasonData) return;
      const rows = getRawSeasonRows(cachedSeasonData);
      const yrs = rows.map(r => r.year).sort((a,b) => b-a);
      const maxY = yrs.length > 0 ? yrs[0] : 2026;

      if (preset === 'all') {
        appStartYear = null; appEndYear = null;
      } else if (preset === 'last3') {
        appStartYear = maxY - 2; appEndYear = maxY;
      } else if (preset === 'last5') {
        appStartYear = maxY - 4; appEndYear = maxY;
      } else if (preset === 'last10') {
        appStartYear = maxY - 9; appEndYear = maxY;
      } else if (preset === '2020-2024') {
        appStartYear = 2020; appEndYear = 2024;
      }
      document.getElementById('season-from-year').value = appStartYear || '';
      document.getElementById('season-to-year').value = appEndYear || '';
      document.getElementById('season-from-date').value = '';
      document.getElementById('season-to-date').value = '';
      renderSeasonalMatrix(cachedSeasonData);
    }

    function onAppYearChange() {
      appYearPreset = 'custom';
      document.querySelectorAll('#tab-seasonality .filter-row:first-child .filter-chip-btn').forEach(b => b.classList.remove('active'));
      const fy = document.getElementById('season-from-year').value;
      const ty = document.getElementById('season-to-year').value;
      appStartYear = fy ? parseInt(fy) : null;
      appEndYear = ty ? parseInt(ty) : null;
      if (cachedSeasonData) renderSeasonalMatrix(cachedSeasonData);
    }

    async function applyAppCustomDates() {
      const fromD = document.getElementById('season-from-date').value;
      const toD = document.getElementById('season-to-date').value;
      if (!fromD && !toD) return;

      document.querySelectorAll('#tab-seasonality .filter-row:first-child .filter-chip-btn').forEach(b => b.classList.remove('active'));
      appYearPreset = 'custom';

      if (fromD) {
        const fy = parseInt(fromD.split('-')[0]);
        appStartYear = fy;
        const fromSel = document.getElementById('season-from-year');
        if (fromSel) fromSel.value = fy;
      }
      if (toD) {
        const ty = parseInt(toD.split('-')[0]);
        appEndYear = ty;
        const toSel = document.getElementById('season-to-year');
        if (toSel) toSel.value = ty;
      }

      const sym = document.getElementById('season-symbol').value.trim().toUpperCase() || 'RELIANCE';
      try {
        const params = new URLSearchParams();
        if (fromD) params.set('start_date', fromD);
        if (toD) params.set('end_date', toD);
        const res = await fetch(`/api/v1/analytics/seasonality/${sym}?${params.toString()}`);
        const data = await res.json();
        cachedSeasonData = data;
        renderSeasonalMatrix(data);
      } catch (err) {
        console.error('Failed to apply custom date range:', err);
      }
    }

    function setAppReturnPreset(preset) {
      appReturnPreset = preset;
      document.querySelectorAll('#tab-seasonality .filter-row:nth-child(2) .filter-chip-btn').forEach(b => b.classList.remove('active'));
      const btn = document.getElementById(`btn-ret-${preset}`);
      if (btn) btn.classList.add('active');

      if (preset === 'all') {
        appMinReturn = null; appMaxReturn = null;
      } else if (preset === 'pos') {
        appMinReturn = 0.01; appMaxReturn = null;
      } else if (preset === 'neg') {
        appMinReturn = null; appMaxReturn = -0.01;
      } else if (preset === 'gain5') {
        appMinReturn = 5.0; appMaxReturn = null;
      } else if (preset === 'loss5') {
        appMinReturn = null; appMaxReturn = -5.0;
      } else if (preset === 'extreme') {
        appMinReturn = 10.0; appMaxReturn = null;
      }
      document.getElementById('season-min-ret').value = appMinReturn !== null ? appMinReturn : '';
      document.getElementById('season-max-ret').value = appMaxReturn !== null ? appMaxReturn : '';
      if (cachedSeasonData) renderSeasonalMatrix(cachedSeasonData);
    }

    function onAppReturnCustomChange() {
      appReturnPreset = 'custom';
      document.querySelectorAll('#tab-seasonality .filter-row:nth-child(2) .filter-chip-btn').forEach(b => b.classList.remove('active'));
      const minV = document.getElementById('season-min-ret').value;
      const maxV = document.getElementById('season-max-ret').value;
      appMinReturn = minV !== '' ? parseFloat(minV) : null;
      appMaxReturn = maxV !== '' ? parseFloat(maxV) : null;
      if (cachedSeasonData) renderSeasonalMatrix(cachedSeasonData);
    }

    function setAppFilterMode(mode) {
      appFilterMode = mode;
      document.getElementById('btn-mode-dim').classList.toggle('active', mode === 'dim');
      document.getElementById('btn-mode-hide').classList.toggle('active', mode === 'hide');
      if (cachedSeasonData) renderSeasonalMatrix(cachedSeasonData);
    }

    function resetAppSeasonFilters() {
      const fromD = document.getElementById('season-from-date');
      const toD = document.getElementById('season-to-date');
      if (fromD) fromD.value = '';
      if (toD) toD.value = '';
      setAppYearPreset('all');
      setAppReturnPreset('all');
      setAppFilterMode('dim');
      loadSeasonalityChart();
    }

    function checkCellReturnMatch(val) {
      if (val === null || val === undefined) return false;
      if (appReturnPreset === 'extreme') return Math.abs(val) >= 10.0;
      if (appMinReturn !== null && val < appMinReturn) return false;
      if (appMaxReturn !== null && val > appMaxReturn) return false;
      return true;
    }

    async function loadSeasonalityChart() {
      const sym = document.getElementById('season-symbol').value.trim().toUpperCase() || 'RELIANCE';
      try {
        const res = await fetch(`/api/v1/analytics/seasonality/${sym}`);
        const data = await res.json();
        cachedSeasonData = data;
        populateYearDropdowns(data);
        renderSeasonalMatrix(data);
      } catch (err) {
        console.error('Failed to load seasonality:', err);
      }
    }

    function populateYearDropdowns(data) {
      const rows = getRawSeasonRows(data);
      const yrs = Array.from(new Set(rows.map(r => r.year))).sort((a,b) => b-a);
      const fromSel = document.getElementById('season-from-year');
      const toSel = document.getElementById('season-to-year');
      if (fromSel && fromSel.options.length <= 1) {
        fromSel.innerHTML = '<option value="">Start</option>' + yrs.map(y => `<option value="${y}">${y}</option>`).join('');
        toSel.innerHTML = '<option value="">End</option>' + yrs.map(y => `<option value="${y}">${y}</option>`).join('');
      }
    }

    function renderSeasonalMatrix(data) {
      const sym = data.symbol;
      const thead = document.getElementById('tbl-season-head');
      const tbody = document.getElementById('tbl-season-body');
      const tfoot = document.getElementById('tbl-season-foot');
      const title = document.getElementById('season-table-title');

      let cols = ['January','February','March','April','May','June','July','August','September','October','November','December'];
      let rawRows = getRawSeasonRows(data);
      let avgs = {};

      if (currentSeasonPeriod === 'weekly') {
        cols = Array.from({length: 52}, (_, i) => `W${i + 1}`);
        title.innerText = `📊 ${sym} — Weekly Returns Matrix (%) [W1 – W52]`;
        avgs = data.weekly ? (data.weekly.averages || {}) : {};
      } else if (currentSeasonPeriod === 'quarterly') {
        cols = ['Q1', 'Q2', 'Q3', 'Q4'];
        title.innerText = `📊 ${sym} — Quarterly Returns Matrix (%)`;
        avgs = data.quarterly ? (data.quarterly.averages || {}) : {};
      } else {
        title.innerText = `📊 ${sym} — Monthly Returns Matrix (%)`;
        avgs = data.monthly ? (data.monthly.averages || {}) : {};
      }

      // Filter rows by Date Range
      const filteredRows = rawRows.filter(r => {
        if (appStartYear !== null && r.year < appStartYear) return false;
        if (appEndYear !== null && r.year > appEndYear) return false;
        return true;
      });

      const isReturnFilterActive = appReturnPreset !== 'all' || appMinReturn !== null || appMaxReturn !== null;

      // Calculate matching statistics
      let totalCells = 0;
      let matchedCells = 0;
      let sumMatched = 0;

      filteredRows.forEach(r => {
        cols.forEach(c => {
          const val = r[c];
          if (val !== null && val !== undefined) {
            totalCells++;
            if (checkCellReturnMatch(val)) {
              matchedCells++;
              sumMatched += val;
            }
          }
        });
      });

      const statsBar = document.getElementById('season-filter-stats-bar');
      const statsText = document.getElementById('season-filter-stats-text');
      if (statsBar && statsText) {
        if (isReturnFilterActive || appYearPreset !== 'all' || appStartYear !== null || appEndYear !== null) {
          statsBar.style.display = 'flex';
          const matchPct = totalCells > 0 ? (matchedCells / totalCells * 100).toFixed(1) : 0;
          const avgM = matchedCells > 0 ? (sumMatched / matchedCells).toFixed(2) : 0;
          const pName = currentSeasonPeriod.charAt(0).toUpperCase() + currentSeasonPeriod.slice(1);
          statsText.innerHTML = `🎯 Matched (${pName}): <b>${matchedCells} / ${totalCells}</b> cells (${matchPct}%) • Filtered Avg: <b>${avgM >= 0 ? '+' : ''}${avgM}%</b> • Filtered Years: <b>${filteredRows.length} yrs</b>`;
        } else {
          statsBar.style.display = 'none';
        }
      }

      // 1. Header
      const thStyle = currentSeasonPeriod === 'weekly' ? 'style="min-width: 42px; padding: 6px 2px;"' : '';
      thead.innerHTML = `<tr><th class="time-th">Time</th>${cols.map(c => `<th ${thStyle}>${c}</th>`).join('')}</tr>`;

      // 2. Rows
      const fontSz = currentSeasonPeriod === 'weekly' ? '10px' : '12px';
      const padSz = currentSeasonPeriod === 'weekly' ? '7px 2px' : '11px 4px';

      if (filteredRows && filteredRows.length > 0) {
        tbody.innerHTML = filteredRows.map(r => `
          <tr>
            <td class="matrix-row-year">${r.year}</td>
            ${cols.map(c => {
              const val = r[c];
              if (val === null || val === undefined) {
                return '<td style="padding:0"><div class="matrix-tile tile-empty"></div></td>';
              }
              const isMatch = checkCellReturnMatch(val);
              let tileClass = val > 0 ? 'tile-positive' : (val < 0 ? 'tile-negative' : '');

              if (isReturnFilterActive) {
                if (!isMatch) {
                  if (appFilterMode === 'hide') {
                    return '<td style="padding:0"><div class="matrix-tile tile-filtered-out"></div></td>';
                  }
                  tileClass += ' tile-dimmed';
                } else {
                  tileClass += ' tile-highlighted';
                }
              }

              const formatted = (val > 0 ? '+' : '') + Number(val).toFixed(2) + '%';
              return `<td style="padding:0"><div class="matrix-tile ${tileClass}" style="font-size: ${fontSz}; padding: ${padSz};" title="${r.year} ${c}: ${formatted}">${formatted}</div></td>`;
            }).join('')}
          </tr>
        `).join('');
      } else {
        tbody.innerHTML = `<tr><td colspan="${cols.length + 1}" style="text-align:center; padding:20px; color:var(--text-dim);">No matching records found for ${sym} in selected date range.</td></tr>`;
      }

      // 3. Dynamic Summary (Average, Median, Win Rate for filtered rows)
      const dynamicAvg = {};
      const dynamicMed = {};
      const dynamicWin = {};

      cols.forEach(c => {
        const vals = [];
        filteredRows.forEach(r => {
          const v = r[c];
          if (v !== null && v !== undefined) vals.push(Number(v));
        });
        if (vals.length > 0) {
          const sum = vals.reduce((a, b) => a + b, 0);
          dynamicAvg[c] = sum / vals.length;
          const s = [...vals].sort((a,b) => a-b);
          const mid = Math.floor(s.length / 2);
          dynamicMed[c] = s.length % 2 !== 0 ? s[mid] : (s[mid-1] + s[mid]) / 2;
          const pos = vals.filter(v => v > 0).length;
          dynamicWin[c] = (pos / vals.length) * 100;
        }
      });

      tfoot.innerHTML = `
        <tr class="matrix-summary-row">
          <td class="matrix-summary-label">Average</td>
          ${cols.map(c => {
            const val = dynamicAvg[c];
            const formatted = val !== undefined ? ((val > 0 ? '+' : '') + Number(val).toFixed(2) + '%') : '--';
            return `<td style="padding:0"><div class="matrix-summary-tile" style="font-size: ${fontSz}; padding: ${padSz};" title="Average across ${filteredRows.length} filtered years">${formatted}</div></td>`;
          }).join('')}
        </tr>
        <tr class="matrix-summary-row">
          <td class="matrix-summary-label">Median</td>
          ${cols.map(c => {
            const val = dynamicMed[c];
            const formatted = val !== undefined ? ((val > 0 ? '+' : '') + Number(val).toFixed(2) + '%') : '--';
            return `<td style="padding:0"><div class="matrix-summary-tile" style="font-size: ${fontSz}; padding: ${padSz};" title="Median across ${filteredRows.length} filtered years">${formatted}</div></td>`;
          }).join('')}
        </tr>
        <tr class="matrix-summary-row">
          <td class="matrix-summary-label" style="color: var(--accent); font-weight:700;">Win Prob (%)</td>
          ${cols.map(c => {
            const val = dynamicWin[c];
            const formatted = val !== undefined ? Number(val).toFixed(1) + '%' : '--';
            const colorClass = val >= 60 ? 'tile-positive' : (val >= 50 ? 'tile-win' : 'tile-negative');
            return `<td style="padding:0"><div class="matrix-tile ${colorClass}" style="font-size: ${fontSz}; padding: ${padSz}; font-weight: 700;" title="Historical Win Probability across ${filteredRows.length} filtered years: ${formatted}">${formatted}</div></td>`;
          }).join('')}
        </tr>
        <tr class="matrix-summary-row">
          <td class="matrix-summary-label" style="color: var(--text-muted);">Loss Prob (%)</td>
          ${cols.map(c => {
            const val = dynamicWin[c];
            const lossVal = val !== undefined ? (100 - val).toFixed(1) + '%' : '--';
            return `<td style="padding:0"><div class="matrix-summary-tile" style="font-size: ${fontSz}; padding: ${padSz}; color: var(--text-muted);" title="Historical Loss Probability: ${lossVal}">${lossVal}</div></td>`;
          }).join('')}
        </tr>
      `;

      // 4. Bar Chart & Win Probability Line
      const chartCols = cols;
      const chartVals = cols.map(c => dynamicAvg[c] !== undefined ? dynamicAvg[c] : (avgs[c] || 0));
      const chartColors = chartVals.map(v => v >= 0 ? '#16a34a' : '#dc2626');
      const traceBar = {
        x: chartCols, y: chartVals, type: 'bar',
        name: 'Avg Return %',
        marker: { color: chartColors },
        yaxis: 'y1'
      };
      const traceLine = {
        x: chartCols,
        y: cols.map(c => dynamicWin[c] !== undefined ? dynamicWin[c] : null),
        type: 'scatter', mode: 'lines+markers',
        name: 'Win Prob %',
        line: { color: '#2563eb', width: 2 },
        yaxis: 'y2'
      };

      const themeCfg = getPlotlyThemeLayout();
      const layout = {
        title: `${sym} Average Historical Return (%) & Win Probability`,
        paper_bgcolor: themeCfg.paper_bgcolor, plot_bgcolor: themeCfg.plot_bgcolor,
        font: themeCfg.font,
        xaxis: { gridcolor: themeCfg.gridcolor },
        yaxis: { gridcolor: themeCfg.gridcolor, ticksuffix: '%', title: 'Avg Return %' },
        yaxis2: { overlaying: 'y', side: 'right', range: [0, 100], ticksuffix: '%', title: 'Win Prob %', gridcolor: 'transparent' },
        margin: { t: 40, r: 40, l: 50, b: 30 },
        legend: { orientation: 'h', y: 1.12, x: 0 }
      };
      Plotly.newPlot('plot-seasonality', [traceBar, traceLine], layout, {responsive: true});
    }

    function setComparePreset(preset) {
      const fromEl = document.getElementById('compare-from');
      const toEl = document.getElementById('compare-to');
      const maxDate = '2026-10-09';
      if (preset === 'all') {
        fromEl.value = '';
        toEl.value = '';
      } else if (preset === '1y') {
        fromEl.value = '2025-10-09';
        toEl.value = maxDate;
      } else if (preset === '3y') {
        fromEl.value = '2023-10-09';
        toEl.value = maxDate;
      } else if (preset === '5y') {
        fromEl.value = '2021-10-09';
        toEl.value = maxDate;
      } else if (preset === '2020-2024') {
        fromEl.value = '2020-01-01';
        toEl.value = '2024-12-31';
      } else if (preset === 'ytd') {
        fromEl.value = '2026-01-01';
        toEl.value = maxDate;
      }
      loadComparisonChart();
    }

    function resetCompareDates() {
      document.getElementById('compare-from').value = '';
      document.getElementById('compare-to').value = '';
      loadComparisonChart();
    }

    async function loadComparisonChart() {
      const syms = document.getElementById('compare-symbols').value.trim().toUpperCase() || 'RELIANCE,TCS,INFY';
      const fromD = document.getElementById('compare-from').value;
      const toD = document.getElementById('compare-to').value;
      let url = `/api/v1/analytics/compare?symbols=${syms}`;
      if (fromD) url += `&start=${fromD}`;
      if (toD) url += `&end=${toD}`;

      try {
        const res = await fetch(url);
        const data = await res.json();

        const traces = [];
        for (const [stock, points] of Object.entries(data.series || {})) {
          traces.push({
            x: points.map(p => p.trade_date),
            y: points.map(p => p.normalized_price),
            type: 'scatter', mode: 'lines', name: stock,
            line: { width: 2 }
          });
        }

        const dateSub = fromD && toD ? ` (${fromD} to ${toD})` : (fromD ? ` (From ${fromD})` : (toD ? ` (Up to ${toD})` : ''));
        const layout = {
          title: `Cross-Stock Normalized Comparison (Base = 100)${dateSub}`,
          paper_bgcolor: '#111827', plot_bgcolor: '#111827',
          font: { color: '#9ca3af', family: 'JetBrains Mono' },
          xaxis: { gridcolor: '#1f2d47' },
          yaxis: { gridcolor: '#1f2d47', title: 'Performance (Base = 100)' },
          margin: { t: 40, r: 20, l: 50, b: 30 }
        };
        Plotly.newPlot('plot-comparison', traces, layout, {responsive: true});

        // Table
        const sBody = document.getElementById('tbl-compare-stats');
        sBody.innerHTML = (data.summary || []).map(s => `
          <tr>
            <td><strong>${s.symbol}</strong></td>
            <td>₹${s.base_price.toFixed(2)}</td>
            <td>₹${s.latest_close.toFixed(2)}</td>
            <td class="${s.cumulative_return_pct >= 0 ? 'gainer-tag' : 'loser-tag'}">${s.cumulative_return_pct >= 0 ? '+' : ''}${s.cumulative_return_pct}%</td>
            <td>${s.annualized_volatility_pct}%</td>
            <td class="loser-tag">${s.max_drawdown_pct}%</td>
          </tr>
        `).join('') || '<tr><td colspan="6">No comparison data</td></tr>';

      } catch (err) {
        console.error('Failed to load comparison:', err);
      }
    }

    async function loadIngestionJobs() {
      try {
        const res = await fetch('/api/v1/ingestion/jobs');
        const jobs = await res.json();
        const jBody = document.getElementById('tbl-jobs');
        jBody.innerHTML = jobs.map(j => `
          <tr>
            <td><code>${j.job_id}</code></td>
            <td>${j.job_type}</td>
            <td><span class="badge-status" style="font-size:10px;">${j.status}</span></td>
            <td>${j.total_dates}</td>
            <td>${(j.total_rows_imported || 0).toLocaleString()}</td>
            <td>${j.started_at ? j.started_at.substring(0, 19).replace('T', ' ') : '-'}</td>
            <td>${j.completed_at ? j.completed_at.substring(0, 19).replace('T', ' ') : '-'}</td>
          </tr>
        `).join('') || '<tr><td colspan="7">No ingestion jobs yet.</td></tr>';
      } catch (err) {
        console.error('Failed to load jobs:', err);
      }
    }

    async function triggerDailyUpdate() {
      if (!confirm('Trigger incremental daily update for today?')) return;
      try {
        const res = await fetch('/api/v1/daily-update', { method: 'POST' });
        alert('Daily update triggered. Check Data Management tab for progress.');
        loadIngestionJobs();
      } catch (e) {
        alert('Trigger sent: Check logs.');
      }
    }

    async function loadSchedulerStatus() {
      try {
        const res = await fetch('/api/v1/scheduler/status');
        const data = await res.json();
        const el = document.getElementById('sched-status-subtext');
        if (el && data.next_run_time) {
          el.innerHTML = `Scheduled Daily Ingestion: <b>${data.configured_time}</b> • Next Scheduled Run: <b>${data.next_run_time}</b>`;
        }
      } catch (e) {
        console.error('Failed to load scheduler status:', e);
      }
    }

    // Auto load dashboard data on startup
    window.addEventListener('DOMContentLoaded', () => {
      loadDashboardData();
      loadSecuritiesDropdown();
      loadSchedulerStatus();
    });
  </script>
</body>
</html>
"""
