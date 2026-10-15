"""High-performance dialect-aware bulk upsert for stock daily price history."""

from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from nse_pipeline.core.logging import get_logger
from nse_pipeline.database.models import StockDailyHistory

logger = get_logger("database.bulk_upsert")


def bulk_upsert_stock_history(
    session: Session,
    records: list[dict[str, Any]],
    batch_size: int = 1000,
) -> int:
    """Performs an idempotent bulk upsert of daily stock records.

    If MySQL is used, utilizes ON DUPLICATE KEY UPDATE.
    If SQLite is used, utilizes ON CONFLICT DO UPDATE.
    """
    if not records:
        return 0

    valid_cols = {c.name for c in StockDailyHistory.__table__.columns}
    sanitized_records = [{k: v for k, v in r.items() if k in valid_cols} for r in records]

    engine = session.get_bind()
    dialect_name = engine.dialect.name.lower()

    total_processed = 0

    for i in range(0, len(sanitized_records), batch_size):
        chunk = sanitized_records[i : i + batch_size]

        if "mysql" in dialect_name:
            _bulk_upsert_mysql(session, chunk)
        else:
            _bulk_upsert_sqlite(session, chunk)

        total_processed += len(chunk)

    # Automatic dual-write to MongoDB if enabled
    try:
        from nse_pipeline.core.config import get_settings
        if get_settings().enable_mongodb:
            from nse_pipeline.database.mongo import bulk_upsert_stock_history_mongo
            bulk_upsert_stock_history_mongo(sanitized_records)
    except Exception as e:
        logger.warning(f"Failed to dual-write daily stock records to MongoDB: {e}")

    return total_processed


def _bulk_upsert_mysql(session: Session, records: list[dict[str, Any]]) -> None:
    """Executes MySQL ON DUPLICATE KEY UPDATE raw statement for maximum throughput."""
    raw_query = text("""
        INSERT INTO stock_daily_history (
            trade_date, security_id, symbol, series,
            prev_close, open_price, high_price, low_price, last_price, close_price, vwap,
            traded_quantity, turnover, no_of_trades, deliverable_quantity, deliverable_pct,
            source_format, source_file
        ) VALUES (
            :trade_date, :security_id, :symbol, :series,
            :prev_close, :open_price, :high_price, :low_price, :last_price, :close_price, :vwap,
            :traded_quantity, :turnover, :no_of_trades, :deliverable_quantity, :deliverable_pct,
            :source_format, :source_file
        )
        ON DUPLICATE KEY UPDATE
            prev_close = VALUES(prev_close),
            open_price = VALUES(open_price),
            high_price = VALUES(high_price),
            low_price = VALUES(low_price),
            last_price = VALUES(last_price),
            close_price = VALUES(close_price),
            vwap = VALUES(vwap),
            traded_quantity = VALUES(traded_quantity),
            turnover = VALUES(turnover),
            no_of_trades = VALUES(no_of_trades),
            deliverable_quantity = VALUES(deliverable_quantity),
            deliverable_pct = VALUES(deliverable_pct),
            source_format = VALUES(source_format),
            source_file = VALUES(source_file),
            updated_at = CURRENT_TIMESTAMP
    """)

    session.execute(raw_query, records)


def _bulk_upsert_sqlite(session: Session, records: list[dict[str, Any]]) -> None:
    """Executes SQLite ON CONFLICT DO UPDATE in batch for maximum throughput."""
    if not records:
        return
    cols = [
        "trade_date", "security_id", "symbol", "series",
        "prev_close", "open_price", "high_price", "low_price", "last_price", "close_price", "vwap",
        "traded_quantity", "turnover", "no_of_trades", "deliverable_quantity", "deliverable_pct",
        "source_format", "source_file",
    ]
    batch_records = [{c: r.get(c, None) for c in cols} for r in records]
    raw_query = text("""
        INSERT INTO stock_daily_history (
            trade_date, security_id, symbol, series,
            prev_close, open_price, high_price, low_price, last_price, close_price, vwap,
            traded_quantity, turnover, no_of_trades, deliverable_quantity, deliverable_pct,
            source_format, source_file
        ) VALUES (
            :trade_date, :security_id, :symbol, :series,
            :prev_close, :open_price, :high_price, :low_price, :last_price, :close_price, :vwap,
            :traded_quantity, :turnover, :no_of_trades, :deliverable_quantity, :deliverable_pct,
            :source_format, :source_file
        )
        ON CONFLICT(trade_date, security_id, series) DO UPDATE SET
            close_price = excluded.close_price,
            open_price = excluded.open_price,
            high_price = excluded.high_price,
            low_price = excluded.low_price,
            prev_close = excluded.prev_close,
            last_price = excluded.last_price,
            vwap = excluded.vwap,
            traded_quantity = excluded.traded_quantity,
            turnover = excluded.turnover,
            no_of_trades = excluded.no_of_trades,
            deliverable_quantity = excluded.deliverable_quantity,
            deliverable_pct = excluded.deliverable_pct,
            source_format = excluded.source_format,
            source_file = excluded.source_file,
            updated_at = CURRENT_TIMESTAMP
    """)
    session.execute(raw_query, batch_records)

