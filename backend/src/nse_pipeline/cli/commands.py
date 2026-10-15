"""Master Typer CLI aggregating all pipeline subcommands."""

import typer

from nse_pipeline.cli import (
    backfill,
    daily_update,
    export_data,
    import_file,
    mongo_sync,
    setup_database,
    validate_data,
)
from nse_pipeline.scheduler.daily_scheduler import start_scheduler

cli_app = typer.Typer(
    name="nse-pipeline",
    help="NSE Market Data Pipeline — Historical Backfill & Daily EOD Ingestion Platform",
    add_completion=False,
)

cli_app.add_typer(setup_database.app, name="setup-database")
cli_app.command(name="backfill", help="Historical backfill for NSE market data")(backfill.main)
cli_app.command(name="daily-update", help="Daily end-of-day ingestion")(daily_update.main)
cli_app.add_typer(import_file.app, name="import-file")
cli_app.add_typer(validate_data.app, name="validate-data")
cli_app.add_typer(export_data.app, name="export-data")
cli_app.add_typer(mongo_sync.app, name="mongo")


@cli_app.command(name="start-scheduler")
def run_scheduler_cmd():
    """Starts the 4:00 PM IST daily scheduler daemon."""
    start_scheduler()


if __name__ == "__main__":
    cli_app()
