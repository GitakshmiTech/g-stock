"""Historical backfill service for date ranges from 2001 to 2026."""

import uuid
from dataclasses import dataclass, field
from datetime import date

from nse_pipeline.core.clock import parse_date
from nse_pipeline.core.config import get_settings
from nse_pipeline.core.constants import FileStatus, JobStatus, JobType
from nse_pipeline.core.logging import get_logger
from nse_pipeline.database.repositories.ingestion_repository import IngestionRepository
from nse_pipeline.database.repositories.price_repository import PriceRepository
from nse_pipeline.database.session import get_db_session
from nse_pipeline.downloader.download_manager import DownloadManager
from nse_pipeline.scheduler.trading_calendar import NSETradingCalendar
from nse_pipeline.services.ingestion_service import IngestionService

logger = get_logger("services.backfill")


@dataclass
class BackfillSummary:
    job_id: str
    start_date: date
    end_date: date
    total_dates_requested: int = 0
    trading_dates_count: int = 0
    already_imported_count: int = 0
    successful_dates_count: int = 0
    failed_dates_count: int = 0
    total_rows_imported: int = 0
    missing_dates: list[date] = field(default_factory=list)


class BackfillService:
    def __init__(self):
        self.settings = get_settings()
        self.download_manager = DownloadManager()

    def run_backfill(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        resume: bool = True,
        batch_size: int | None = None,
    ) -> BackfillSummary:
        """Executes historical backfill for the requested date range."""
        start = start_date or parse_date(self.settings.data_start_date)
        end = end_date or parse_date(self.settings.data_end_date)
        batch_days = batch_size or self.settings.backfill_batch_days
        job_id = f"backfill_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}"

        logger.info(f"Starting historical backfill from {start} to {end} (Job: {job_id})")

        # 1. Determine eligible trading dates
        all_trading_days = NSETradingCalendar.get_trading_days(start, end)
        summary = BackfillSummary(
            job_id=job_id,
            start_date=start,
            end_date=end,
            total_dates_requested=(end - start).days + 1,
            trading_dates_count=len(all_trading_days),
        )

        with get_db_session() as session:
            ingestion_repo = IngestionRepository(session)
            price_repo = PriceRepository(session)
            ingestion_service = IngestionService(session)

            ingestion_repo.create_job(
                job_id=job_id,
                job_type=JobType.BACKFILL,
                start_date=start,
                end_date=end,
                total_dates=len(all_trading_days),
            )

            # Check existing imported dates if resume requested
            existing_dates = set()
            if resume:
                existing_dates = set(price_repo.get_distinct_dates(start_date=start, end_date=end))
                summary.already_imported_count = len([d for d in all_trading_days if d in existing_dates])
                logger.info(f"Resume enabled: {summary.already_imported_count} trading dates already present.")

            # Filter remaining dates to process
            dates_to_process = [d for d in all_trading_days if d not in existing_dates]

            for idx, target_date in enumerate(dates_to_process, 1):
                logger.info(f"Processing date [{idx}/{len(dates_to_process)}]: {target_date}")

                # Download file
                dl_result = self.download_manager.download_for_date(target_date)
                if not dl_result:
                    logger.warning(f"Archive not available for {target_date}")
                    summary.missing_dates.append(target_date)
                    summary.failed_dates_count += 1
                    continue

                # Ingest file
                try:
                    res = ingestion_service.ingest_download_result(dl_result, job_id=job_id)
                    if res.status == FileStatus.IMPORTED:
                        summary.successful_dates_count += 1
                        summary.total_rows_imported += res.inserted_count
                    else:
                        summary.failed_dates_count += 1
                except Exception as ex:
                    logger.error(f"Unexpected error ingesting date {target_date}: {ex}")
                    session.rollback()
                    summary.missing_dates.append(target_date)
                    summary.failed_dates_count += 1
                finally:
                    session.expunge_all()

                # Update progress periodically
                if idx % batch_days == 0 or idx == len(dates_to_process):
                    try:
                        ingestion_repo.update_job_status(
                            job_id=job_id,
                            status=JobStatus.RUNNING,
                            successful_dates=summary.successful_dates_count,
                            failed_dates=summary.failed_dates_count,
                            total_rows=summary.total_rows_imported,
                        )
                        session.commit()
                    except Exception as e:
                        logger.warning(f"Failed to update job status in DB: {e}")
                        session.rollback()

            final_status = JobStatus.SUCCESS if summary.failed_dates_count == 0 else JobStatus.PARTIAL
            ingestion_repo.update_job_status(
                job_id=job_id,
                status=final_status,
                successful_dates=summary.successful_dates_count,
                failed_dates=summary.failed_dates_count,
                total_rows=summary.total_rows_imported,
            )
            session.commit()

        logger.info(
            f"Backfill finished: {summary.successful_dates_count} dates imported, "
            f"{summary.failed_dates_count} missing/failed, {summary.total_rows_imported} total rows."
        )
        return summary
