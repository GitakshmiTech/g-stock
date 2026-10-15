"""CLI command to synchronize market data into MongoDB for MongoDB Compass."""

import os
import subprocess
from typing import Optional
import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn

from nse_pipeline.database.mongo import get_mongo_stats
from nse_pipeline.services.mongo_sync_service import MongoSyncService

app = typer.Typer(help="Synchronize SQL market data to MongoDB collections for MongoDB Compass.")
console = Console()

COMPASS_PATH = r"C:\Users\dhruv\AppData\Local\MongoDBCompass\MongoDBCompass.exe"


@app.command(name="sync")
def sync_cmd(
    all_data: bool = typer.Option(False, "--all", "-a", help="Sync full database (Securities, Calendar, and All Stock History)"),
    securities_only: bool = typer.Option(False, "--securities", help="Sync securities master only"),
    calendar_only: bool = typer.Option(False, "--calendar", help="Sync trading calendar only"),
    start_date: Optional[str] = typer.Option(None, "--start", "-s", help="Start trade date (YYYY-MM-DD)"),
    end_date: Optional[str] = typer.Option(None, "--end", "-e", help="End trade date (YYYY-MM-DD)"),
    symbols: Optional[str] = typer.Option(None, "--symbols", help="Comma-separated symbols to sync (e.g. RELIANCE,TCS,INFY)"),
    launch_compass: bool = typer.Option(False, "--launch-compass", help="Launch MongoDB Compass after synchronization"),
):
    """Synchronize NSE market data into MongoDB collections."""
    console.print("[bold green]NSE MongoDB Synchronization Engine[/bold green]")
    service = MongoSyncService()

    if calendar_only:
        with console.status("[bold blue]Syncing Trading Calendar to MongoDB..."):
            count = service.sync_trading_calendar()
        console.print(f"[green]✓ Synced {count:,} calendar days to 'trading_calendar' collection.[/green]")
        return

    if securities_only:
        with console.status("[bold blue]Syncing Securities Master to MongoDB..."):
            count = service.sync_securities()
        console.print(f"[green]✓ Synced {count:,} securities to 'securities' collection.[/green]")
        return

    # Default / Full flow: sync securities and calendar first
    with console.status("[bold blue]Syncing Securities Master..."):
        sec_count = service.sync_securities()
    console.print(f"[green]✓ Synced {sec_count:,} securities to 'securities' collection.[/green]")

    with console.status("[bold blue]Syncing Trading Calendar..."):
        cal_count = service.sync_trading_calendar()
    console.print(f"[green]✓ Synced {cal_count:,} calendar days to 'trading_calendar' collection.[/green]")

    # Sync price history
    sym_list = [s.strip().upper() for s in symbols.split(",")] if symbols else None
    
    # If no specific filters and not --all, default to latest 1 year for fast response
    effective_start = start_date
    if not all_data and not start_date and not symbols:
        effective_start = "2025-01-01"
        console.print("[yellow]Notice: Defaulting to 2025-01-01 to present for fast initial sync. Use --all to sync all 2001-2026 data.[/yellow]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("[cyan]Syncing Daily Stock History...", total=100)

        def progress_callback(processed: int, total: int, msg: str):
            if total > 0:
                pct = (processed / total) * 100
                progress.update(task_id, completed=pct, description=f"[cyan]{msg}")

        bars_count = service.sync_stock_history(
            start_date=effective_start,
            end_date=end_date,
            symbols=sym_list,
            batch_size=10000,
            on_progress=progress_callback,
        )

    console.print(f"[bold green]✓ Successfully synced {bars_count:,} price records to 'stock_daily_history' collection![/bold green]")

    stats = get_mongo_stats()
    console.print("\n[bold]MongoDB Live Collection Statistics:[/bold]")
    for col, count in stats.get("collections", {}).items():
        console.print(f"  • [bold cyan]{col}[/bold cyan]: {count:,} documents")

    console.print("\n[bold blue]Connection Info for MongoDB Compass:[/bold blue]")
    console.print("  • URI: [bold yellow]mongodb://localhost:27017[/bold yellow]")
    console.print("  • Database: [bold yellow]nse_market_data[/bold yellow]")

    if launch_compass:
        launch_compass_app()


@app.command(name="pull")
def pull_cmd(
    batch_size: int = typer.Option(5000, "--batch-size", "-b", help="Batch size for bulk insertion into SQL"),
):
    """Pulls all securities, calendar dates, and stock price history from MongoDB into SQL (SQLite/MySQL)."""
    console.print("[bold green]Pulling Market Data from MongoDB into SQL...[/bold green]")
    service = MongoSyncService()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("[cyan]Importing from MongoDB...", total=100)

        def progress_callback(processed: int, total: int, msg: str):
            if total > 0:
                pct = (processed / total) * 100
                progress.update(task_id, completed=pct, description=f"[cyan]{msg}")

        results = service.sync_from_mongo_to_sql(batch_size=batch_size, on_progress=progress_callback)

    console.print("\n[bold green]✓ Successfully hydrated SQL database from MongoDB:[/bold green]")
    console.print(f"  • Securities: [bold cyan]{results.get('securities', 0):,}[/bold cyan]")
    console.print(f"  • Calendar Dates: [bold cyan]{results.get('calendar', 0):,}[/bold cyan]")
    console.print(f"  • Price Records: [bold cyan]{results.get('prices', 0):,}[/bold cyan]")


@app.command(name="status")
def status_cmd():
    """Display MongoDB connection status and collection document counts."""
    stats = get_mongo_stats()
    if stats.get("connected"):
        console.print(f"[bold green]Connected to MongoDB ({stats.get('database')})[/bold green]")
        console.print("\n[bold]Collection Document Counts:[/bold]")
        for col, count in stats.get("collections", {}).items():
            console.print(f"  • [bold cyan]{col}[/bold cyan]: {count:,} documents")
        console.print("\n[dim]MongoDB Compass URI: mongodb://localhost:27017[/dim]")
    else:
        console.print(f"[bold red]Failed to connect to MongoDB:[/bold red] {stats.get('error')}")


@app.command(name="launch-compass")
def launch_compass_cmd():
    """Launches MongoDB Compass directly."""
    launch_compass_app()


def launch_compass_app():
    """Launches the MongoDB Compass desktop app."""
    if os.path.exists(COMPASS_PATH):
        console.print(f"[bold green]Launching MongoDB Compass from {COMPASS_PATH}...[/bold green]")
        subprocess.Popen([COMPASS_PATH, "mongodb://localhost:27017"])
    else:
        console.print(f"[yellow]MongoDB Compass not found at default path {COMPASS_PATH}. Please open it manually and connect to mongodb://localhost:27017[/yellow]")
