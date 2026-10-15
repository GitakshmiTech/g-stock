"""High-performance synchronization service from SQL (SQLite/MySQL) to MongoDB.

Allows migrating and streaming all historical securities, trading calendar,
and stock daily price history records into MongoDB collections for MongoDB Compass.
"""

from datetime import date, datetime
import logging
import time
from typing import Callable, Any

from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from pymongo import UpdateOne

from nse_pipeline.core.config import get_settings
from nse_pipeline.database.mongo import (
    get_mongo_db,
    init_mongo_indexes,
    sanitize_doc,
    get_mongo_stats,
)
from nse_pipeline.database.session import get_db_session

logger = logging.getLogger("nse_pipeline.services.mongo_sync")


class MongoSyncService:
    """Orchestrates syncing data from the primary SQL store to MongoDB."""

    def __init__(self, session: Session | None = None):
        self._provided_session = session
        try:
            settings = get_settings()
            if settings.enable_mongodb:
                init_mongo_indexes()
        except Exception as e:
            logger.warning(f"Could not initialize MongoDB indexes: {e}")

    def sync_securities(self, on_progress: Callable[[int, int], None] | None = None) -> int:
        """Syncs all securities metadata into the MongoDB 'securities' collection."""
        db = get_mongo_db()
        col = db.securities

        with (self._provided_session if self._provided_session else get_db_session()) as session:
            rows = session.execute(
                text("SELECT id, symbol, series, company_name, isin, status, first_traded_date, last_traded_date FROM securities")
            ).mappings().all()

        total = len(rows)
        logger.info(f"Syncing {total:,} securities to MongoDB...")

        ops = []
        for r in rows:
            doc = sanitize_doc(dict(r))
            sym = doc.get("symbol")
            ser = doc.get("series", "EQ")
            if not sym:
                continue
            ops.append(
                UpdateOne(
                    {"symbol": sym, "series": ser},
                    {"$set": doc},
                    upsert=True,
                )
            )

        if ops:
            col.bulk_write(ops, ordered=False)

        if on_progress:
            on_progress(total, total)

        logger.info(f"Successfully synced {total:,} securities to MongoDB collection 'securities'.")
        return total

    def sync_trading_calendar(self) -> int:
        """Syncs trading calendar dates and holiday flags into MongoDB 'trading_calendar'."""
        db = get_mongo_db()
        col = db.trading_calendar

        with (self._provided_session if self._provided_session else get_db_session()) as session:
            rows = session.execute(
                text("SELECT trade_date, session_type, is_trading_day, is_holiday, holiday_name, is_weekend FROM trading_calendar")
            ).mappings().all()

        total = len(rows)
        logger.info(f"Syncing {total:,} calendar days to MongoDB...")

        ops = []
        for r in rows:
            doc = sanitize_doc(dict(r))
            c_date = doc.get("trade_date")
            if not c_date:
                continue
            ops.append(
                UpdateOne(
                    {"trade_date": c_date},
                    {"$set": doc},
                    upsert=True,
                )
            )

        if ops:
            col.bulk_write(ops, ordered=False)

        logger.info(f"Successfully synced {total:,} calendar records to MongoDB collection 'trading_calendar'.")
        return total

    def sync_stock_history(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        symbols: list[str] | None = None,
        batch_size: int = 10000,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> int:
        """Streams stock daily history from SQL to MongoDB in high-throughput bulk batches."""
        db = get_mongo_db()
        col = db.stock_daily_history

        where_clauses = []
        params: dict[str, Any] = {}

        if start_date:
            where_clauses.append("trade_date >= :start_date")
            params["start_date"] = start_date
        if end_date:
            where_clauses.append("trade_date <= :end_date")
            params["end_date"] = end_date
        if symbols:
            clean_syms = [s.strip().upper() for s in symbols]
            where_clauses.append(f"symbol IN ({', '.join(repr(s) for s in clean_syms)})")

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        with (self._provided_session if self._provided_session else get_db_session()) as session:
            count_query = text(f"SELECT COUNT(*) FROM stock_daily_history {where_sql}")
            total_rows = session.execute(count_query, params).scalar() or 0

            logger.info(f"Preparing to sync {total_rows:,} daily price records to MongoDB (Batch size: {batch_size:,})...")

            select_sql = text(f"""
                SELECT trade_date, symbol, series, prev_close, open_price, high_price,
                       low_price, last_price, close_price, vwap, traded_quantity, turnover,
                       no_of_trades, deliverable_quantity, deliverable_pct
                FROM stock_daily_history
                {where_sql}
                ORDER BY trade_date ASC
            """)

            result_proxy = session.execute(select_sql, params)

            processed = 0
            start_time = time.time()

            while True:
                chunk = result_proxy.fetchmany(batch_size)
                if not chunk:
                    break

                ops = []
                for row in chunk:
                    doc = sanitize_doc(dict(row._mapping))
                    sym = doc.get("symbol")
                    ser = doc.get("series", "EQ")
                    t_date = doc.get("trade_date")
                    if not sym or not t_date:
                        continue

                    ops.append(
                        UpdateOne(
                            {"symbol": sym, "series": ser, "trade_date": t_date},
                            {"$set": doc},
                            upsert=True,
                        )
                    )

                if ops:
                    col.bulk_write(ops, ordered=False)

                processed += len(chunk)
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                msg = f"Synced {processed:,}/{total_rows:,} ({processed/total_rows*100:.1f}%) at {rate:.0f} docs/sec"
                logger.info(msg)

                if on_progress:
                    on_progress(processed, total_rows, msg)

        logger.info(f"Finished syncing {processed:,} stock price records to MongoDB collection 'stock_daily_history'.")
        return processed

    def sync_from_mongo_to_sql(
        self,
        batch_size: int = 5000,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> dict[str, int]:
        """Pulls all securities, trading calendar, and daily stock price records from MongoDB into SQL."""
        settings = get_settings()
        if not settings.enable_mongodb:
            logger.info("MongoDB is disabled in settings. Skipping pull from MongoDB.")
            return {"securities": 0, "calendar": 0, "prices": 0}

        try:
            db = get_mongo_db()
        except Exception as e:
            logger.warning(f"Could not connect to MongoDB for pull: {e}")
            return {"securities": 0, "calendar": 0, "prices": 0}

        with (self._provided_session if self._provided_session else get_db_session()) as session:
            # 1. Pull Securities
            sec_docs = list(db.securities.find({}))
            sec_count = len(sec_docs)
            logger.info(f"Pulling {sec_count:,} securities from MongoDB to SQL...")
            if sec_docs:
                from nse_pipeline.database.bulk_upsert import bulk_upsert_securities
                clean_secs = []
                for d in sec_docs:
                    clean_secs.append({
                        "id": int(d.get("id")) if d.get("id") else None,
                        "symbol": d.get("symbol"),
                        "series": d.get("series", "EQ"),
                        "company_name": d.get("company_name"),
                        "isin": d.get("isin"),
                        "status": d.get("status", "ACTIVE"),
                        "first_traded_date": d.get("first_traded_date"),
                        "last_traded_date": d.get("last_traded_date"),
                    })
                bulk_upsert_securities(session, clean_secs)
                session.commit()

            # Build securities lookup map (symbol, series) -> id
            rows = session.execute(text("SELECT id, symbol, series FROM securities")).all()
            sec_map = {(r[1], r[2]): r[0] for r in rows}

            # 2. Pull Trading Calendar
            cal_docs = list(db.trading_calendar.find({}))
            cal_count = len(cal_docs)
            logger.info(f"Pulling {cal_count:,} calendar dates from MongoDB to SQL...")
            if cal_docs:
                cal_data = []
                for d in cal_docs:
                    cal_data.append({
                        "trade_date": d.get("trade_date"),
                        "session_type": d.get("session_type", "EQUITY"),
                        "is_trading_day": bool(int(d.get("is_trading_day", 1))),
                        "is_holiday": bool(int(d.get("is_holiday", 0))),
                        "holiday_name": d.get("holiday_name"),
                        "is_weekend": bool(int(d.get("is_weekend", 0))),
                    })
                dialect_name = session.bind.dialect.name if session.bind else "sqlite"
                upsert_cal_sql = text("""
                    INSERT INTO trading_calendar (trade_date, session_type, is_trading_day, is_holiday, holiday_name, is_weekend)
                    VALUES (:trade_date, :session_type, :is_trading_day, :is_holiday, :holiday_name, :is_weekend)
                    ON CONFLICT(trade_date) DO UPDATE SET
                        session_type=excluded.session_type,
                        is_trading_day=excluded.is_trading_day,
                        is_holiday=excluded.is_holiday,
                        holiday_name=excluded.holiday_name,
                        is_weekend=excluded.is_weekend
                """) if "sqlite" in dialect_name else text("""
                    INSERT INTO trading_calendar (trade_date, session_type, is_trading_day, is_holiday, holiday_name, is_weekend)
                    VALUES (:trade_date, :session_type, :is_trading_day, :is_holiday, :holiday_name, :is_weekend)
                    ON DUPLICATE KEY UPDATE
                        session_type=VALUES(session_type),
                        is_trading_day=VALUES(is_trading_day),
                        is_holiday=VALUES(is_holiday),
                        holiday_name=VALUES(holiday_name),
                        is_weekend=VALUES(is_weekend)
                """)
                for c_item in cal_data:
                    session.execute(upsert_cal_sql, c_item)
                session.commit()

            # 3. Pull Stock Daily History
            total_history = db.stock_daily_history.count_documents({})
            logger.info(f"Pulling {total_history:,} daily price records from MongoDB to SQL...")
            cursor = db.stock_daily_history.find({}, batch_size=batch_size)
            hist_chunk = []
            processed = 0

            for d in cursor:
                sym = d.get("symbol")
                ser = d.get("series", "EQ")
                sec_id = sec_map.get((sym, ser)) or sec_map.get((sym, "EQ")) or 1

                hist_chunk.append({
                    "trade_date": d.get("trade_date"),
                    "security_id": sec_id,
                    "symbol": sym,
                    "series": ser,
                    "prev_close": d.get("prev_close"),
                    "open_price": d.get("open_price"),
                    "high_price": d.get("high_price"),
                    "low_price": d.get("low_price"),
                    "last_price": d.get("last_price"),
                    "close_price": d.get("close_price"),
                    "vwap": d.get("vwap"),
                    "traded_quantity": d.get("traded_quantity"),
                    "turnover": d.get("turnover"),
                    "no_of_trades": d.get("no_of_trades"),
                    "deliverable_quantity": d.get("deliverable_quantity"),
                    "deliverable_pct": d.get("deliverable_pct"),
                    "source_format": "MONGODB_SYNC",
                    "source_file": "mongo://nse_market_data/stock_daily_history",
                })

                if len(hist_chunk) >= batch_size:
                    from nse_pipeline.database.bulk_upsert import bulk_upsert_stock_history
                    bulk_upsert_stock_history(session, hist_chunk, batch_size=batch_size)
                    session.commit()
                    processed += len(hist_chunk)
                    msg = f"Imported {processed:,}/{total_history:,} ({processed/total_history*100:.1f}%) stock prices into SQL"
                    logger.info(msg)
                    if on_progress:
                        on_progress(processed, total_history, msg)
                    hist_chunk = []

            if hist_chunk:
                from nse_pipeline.database.bulk_upsert import bulk_upsert_stock_history
                bulk_upsert_stock_history(session, hist_chunk, batch_size=batch_size)
                session.commit()
                processed += len(hist_chunk)

            logger.info(f"Successfully synced {processed:,} stock price records from MongoDB into SQL.")
            return {"securities": sec_count, "calendar": cal_count, "prices": processed}

    def ensure_sql_hydrated_from_mongo(self) -> bool:
        """Checks if SQL database has 0 price records but MongoDB has data, and auto-hydrates."""
        settings = get_settings()
        if not settings.enable_mongodb:
            return False

        try:
            with (self._provided_session if self._provided_session else get_db_session()) as session:
                sql_count = session.execute(text("SELECT COUNT(*) FROM stock_daily_history")).scalar() or 0
                if sql_count > 0:
                    return False  # Already populated

            db = get_mongo_db()
            mongo_count = db.stock_daily_history.count_documents({})
            if mongo_count > 0:
                logger.info(f"SQL database has 0 price records, but MongoDB has {mongo_count:,}. Auto-hydrating SQL from MongoDB...")
                self.sync_from_mongo_to_sql()
                return True
        except Exception as e:
            logger.warning(f"Could not check or hydrate SQL from MongoDB: {e}")
        return False
