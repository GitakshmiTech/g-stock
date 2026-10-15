#!/usr/bin/env python3
"""Comprehensive Historical Backfill Engine (2001 to Present).

Downloads and ingests all historical NSE Bhavcopy archives (legacy cmDDMMMYYYYbhav
and modern UDiFF formats) from January 2001 to current date into both
SQLite/MySQL and MongoDB.

Usage:
    py scripts/run_historical_backfill_2001_to_present.py
    py scripts/run_historical_backfill_2001_to_present.py --start 2001-01-01 --end 2026-10-15
    py scripts/run_historical_backfill_2001_to_present.py --status
    py scripts/run_historical_backfill_2001_to_present.py --year 2001
"""

import argparse
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

# Add project root and src to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "backend" / "src"))

from nse_pipeline.core.clock import parse_date
from nse_pipeline.core.constants import FileStatus, JobStatus, JobType
from nse_pipeline.core.logging import get_logger
from nse_pipeline.database.mongo import get_mongo_db
from nse_pipeline.database.repositories.ingestion_repository import IngestionRepository
from nse_pipeline.database.repositories.price_repository import PriceRepository
from nse_pipeline.database.session import get_db_session
from nse_pipeline.downloader.download_manager import DownloadManager
from nse_pipeline.scheduler.trading_calendar import NSETradingCalendar
from nse_pipeline.services.ingestion_service import IngestionService

logger = get_logger("backfill.runner")

STATUS_FILE = PROJECT_ROOT / "logs" / "backfill_progress.json"


if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def get_progress_status():
    """Calculates year-by-year ingestion statistics across SQLite and MongoDB."""
    start_year = 2001
    end_year = date.today().year

    stats = []
    with get_db_session() as session:
        price_repo = PriceRepository(session)
        all_imported_dates = set(price_repo.get_distinct_dates(
            start_date=date(2001, 1, 1),
            end_date=date(end_year, 12, 31)
        ))

        for y in range(start_year, end_year + 1):
            y_start = date(y, 1, 1)
            y_end = min(date(y, 12, 31), date.today())
            trading_days = NSETradingCalendar.get_trading_days(y_start, y_end)
            imported_days = [d for d in trading_days if d in all_imported_dates]

            pct = (len(imported_days) / len(trading_days) * 100) if trading_days else 0.0
            stats.append({
                "year": y,
                "trading_days": len(trading_days),
                "imported_days": len(imported_days),
                "percent_complete": round(pct, 1),
                "status": "COMPLETED" if pct >= 95.0 else ("IN_PROGRESS" if pct > 0 else "PENDING"),
            })

    # MongoDB total count
    mongo_count = 0
    try:
        db = get_mongo_db()
        mongo_count = db.stock_daily_history.count_documents({})
    except Exception as e:
        mongo_count = f"Error: {e}"

    return {
        "updated_at": datetime.now().isoformat(),
        "years": stats,
        "total_trading_days": sum(s["trading_days"] for s in stats),
        "total_imported_days": sum(s["imported_days"] for s in stats),
        "total_mongo_records": mongo_count,
    }


def print_status_table():
    """Prints a clean ASCII progress summary table to console."""
    prog = get_progress_status()
    print("=" * 80)
    print(f"  NSE Market Data Backfill Progress (2001 - {date.today().year})")
    print(f"  Updated At: {prog['updated_at']}")
    print(f"  Total MongoDB Records: {prog['total_mongo_records']:,}" if isinstance(prog['total_mongo_records'], int) else f"  MongoDB: {prog['total_mongo_records']}")
    print(f"  Total Trading Days: {prog['total_imported_days']} / {prog['total_trading_days']} ({(prog['total_imported_days']/prog['total_trading_days']*100):.1f}%)")
    print("=" * 80)
    print(f"{'Year':<8} {'Expected':<12} {'Imported':<12} {'Completion':<16} {'Status':<12}")
    print("-" * 80)
    for s in prog["years"]:
        bar_len = int(s["percent_complete"] / 10)
        bar = "[" + "#" * bar_len + "-" * (10 - bar_len) + "]"
        print(f"{s['year']:<8} {s['trading_days']:<12} {s['imported_days']:<12} {bar} {s['percent_complete']:>5.1f}%   {s['status']}")
    print("=" * 80)


def save_progress(prog_dict):
    """Saves progress dictionary to logs/backfill_progress.json."""
    try:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(prog_dict, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to write progress status file: {e}")


def run_backfill(
    start_date: date,
    end_date: date,
    resume: bool = True,
    recent_first: bool = True,
):
    """Executes the full historical backfill with resilient batching and checkpointing."""
    from concurrent.futures import ThreadPoolExecutor

    download_manager = DownloadManager()

    job_id = f"backfill_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}_{int(time.time())}"
    print(f"\n[+] Starting Historical Backfill: {start_date} -> {end_date}")
    print(f"[+] Master Job ID: {job_id}")
    print(f"[+] Strategy: {'Recent Years First (fast UI populate)' if recent_first else 'Chronological (2001 -> 2026)'}")
    print(f"[+] Resume mode: {'ENABLED (skipping existing days)' if resume else 'DISABLED'}\n")

    # Determine trading days
    all_trading_days = NSETradingCalendar.get_trading_days(start_date, end_date)
    if recent_first:
        all_trading_days = list(reversed(all_trading_days))

    print(f"[*] Total expected trading calendar days: {len(all_trading_days):,}")

    with get_db_session() as session:
        price_repo = PriceRepository(session)
        ingestion_repo = IngestionRepository(session)
        ingestion_service = IngestionService(session)

        ingestion_repo.create_job(
            job_id=job_id,
            job_type=JobType.BACKFILL,
            start_date=start_date,
            end_date=end_date,
            total_dates=len(all_trading_days),
        )

        existing_dates = set()
        if resume:
            existing_dates = set(price_repo.get_distinct_dates(start_date=start_date, end_date=end_date))
            print(f"[*] Found {len(existing_dates):,} days already present in database.")

        dates_to_process = [d for d in all_trading_days if d not in existing_dates]
        print(f"[*] Remaining days to download & ingest: {len(dates_to_process):,}\n")

        if not dates_to_process:
            print("[OK] All requested dates are already present in database! Nothing to do.")
            return

        total_imported_rows = 0
        successful_dates = 0
        failed_or_holiday_dates = 0
        start_time = time.time()

        # Sliding window parallel prefetcher
        CHUNK_SIZE = 100
        for chunk_start in range(0, len(dates_to_process), CHUNK_SIZE):
            chunk_dates = dates_to_process[chunk_start : chunk_start + CHUNK_SIZE]

            # 1. Parallel pre-download chunk
            print(f"[*] Pre-fetching {len(chunk_dates)} archives in parallel with 12 workers...")
            def _dl_worker(d):
                try:
                    return download_manager.download_for_date(d)
                except Exception:
                    return None

            with ThreadPoolExecutor(max_workers=12) as executor:
                list(executor.map(_dl_worker, chunk_dates))

            # 2. Fast ingestion from local cache
            for c_idx, target_date in enumerate(chunk_dates):
                idx = chunk_start + c_idx + 1
                t0 = time.time()
                dl_result = download_manager.download_for_date(target_date)
                if not dl_result:
                    failed_or_holiday_dates += 1
                    print(f"[{idx:>4}/{len(dates_to_process):<4}] {target_date} -> No archive (Holiday / 404)")
                    continue

                # Ingest
                try:
                    res = ingestion_service.ingest_download_result(dl_result, job_id=job_id)
                    elapsed = time.time() - t0
                    if res.status == FileStatus.IMPORTED:
                        successful_dates += 1
                        total_imported_rows += res.inserted_count
                        rate = idx / (time.time() - start_time) if (time.time() - start_time) > 0 else 0
                        print(
                            f"[{idx:>4}/{len(dates_to_process):<4}] {target_date} -> "
                            f"[OK] {res.inserted_count:,} rows upserted ({elapsed:.2f}s) "
                            f"[Total rows: {total_imported_rows:,} | {rate:.1f} days/s]"
                        )
                    else:
                        failed_or_holiday_dates += 1
                        print(f"[{idx:>4}/{len(dates_to_process):<4}] {target_date} -> [FAIL] Ingest status: {res.status} ({res.error_message})")
                except Exception as e:
                    failed_or_holiday_dates += 1
                    session.rollback()
                    print(f"[{idx:>4}/{len(dates_to_process):<4}] {target_date} -> [ERR] Error: {e}")
                finally:
                    session.expunge_all()

                # Periodic checkpoint every 10 days
                if idx % 10 == 0 or idx == len(dates_to_process):
                    try:
                        ingestion_repo.update_job_status(
                            job_id=job_id,
                            status=JobStatus.RUNNING,
                            successful_dates=successful_dates,
                            failed_dates=failed_or_holiday_dates,
                            total_rows=total_imported_rows,
                        )
                        session.commit()
                    except Exception as e:
                        session.rollback()

                    # Update status JSON file
                    save_progress({
                        "job_id": job_id,
                        "last_processed_date": str(target_date),
                        "successful_dates": successful_dates,
                        "failed_or_holiday_dates": failed_or_holiday_dates,
                        "total_imported_rows": total_imported_rows,
                        "progress_percent": round(idx / len(dates_to_process) * 100, 2),
                        "updated_at": datetime.now().isoformat(),
                    })

        final_status = JobStatus.SUCCESS if failed_or_holiday_dates == 0 else JobStatus.PARTIAL
        ingestion_repo.update_job_status(
            job_id=job_id,
            status=final_status,
            successful_dates=successful_dates,
            failed_dates=failed_or_holiday_dates,
            total_rows=total_imported_rows,
        )
        session.commit()

        total_time = time.time() - start_time
        print("\n" + "=" * 60)
        print(f"  Historical Backfill Run Completed")
        print(f"  Successful Dates Imported: {successful_dates:,}")
        print(f"  Total Stock Price Rows:    {total_imported_rows:,}")
        print(f"  Total Time Elapsed:        {total_time/60:.1f} minutes")
        print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="NSE Historical Backfill (2001 to Present)")
    parser.add_argument("--start", type=str, default="2001-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=date.today().isoformat(), help="End date (YYYY-MM-DD)")
    parser.add_argument("--year", type=int, default=None, help="Process a single specific year (e.g. 2005)")
    parser.add_argument("--chronological", action="store_true", help="Process from 2001 forward instead of recent years first")
    parser.add_argument("--no-resume", action="store_true", help="Force re-import of existing dates")
    parser.add_argument("--status", action="store_true", help="Print current ingestion status and exit")

    args = parser.parse_args()

    if args.status:
        print_status_table()
        sys.exit(0)

    if args.year:
        s_date = date(args.year, 1, 1)
        e_date = min(date(args.year, 12, 31), date.today())
    else:
        s_date = parse_date(args.start)
        e_date = parse_date(args.end)

    run_backfill(
        start_date=s_date,
        end_date=e_date,
        resume=not args.no_resume,
        recent_first=not args.chronological,
    )


if __name__ == "__main__":
    main()
