"""MongoDB database connection, index management, and bulk operations.

Enables seamless storage of NSE market data into MongoDB so users can
explore, analyze, and visualize all records in MongoDB Compass.
"""

from datetime import date, datetime
import logging
from typing import Any, Generator

from pymongo import MongoClient, UpdateOne, ASCENDING, DESCENDING
from pymongo.database import Database
from pymongo.errors import PyMongoError, BulkWriteError

from nse_pipeline.core.config import get_settings

logger = logging.getLogger("nse_pipeline.database.mongo")

_mongo_client: MongoClient | None = None


def get_mongo_client(force_new: bool = False) -> MongoClient:
    """Returns a singleton MongoDB client configured from settings."""
    global _mongo_client
    if _mongo_client is not None and not force_new:
        return _mongo_client

    settings = get_settings()
    logger.info(f"Connecting to MongoDB at {settings.mongodb_uri}")
    client = MongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=30000,
        maxPoolSize=50,
    )
    # Ping database to verify connection
    client.admin.command("ping")
    logger.info(f"Successfully connected to MongoDB ({settings.mongodb_database})")
    _mongo_client = client
    return _mongo_client


def get_mongo_db() -> Database:
    """Returns the primary NSE MongoDB database."""
    settings = get_settings()
    client = get_mongo_client()
    db = client[settings.mongodb_database]
    return db


def init_mongo_indexes() -> None:
    """Creates performance indexes and unique constraints on MongoDB collections."""
    db = get_mongo_db()

    # 1. Securities Collection
    try:
        db.securities.create_index(
            [("symbol", ASCENDING), ("series", ASCENDING)],
            unique=True,
            name="idx_securities_sym_series_unique",
        )
        db.securities.create_index([("symbol", ASCENDING)], name="idx_securities_symbol")
        db.securities.create_index([("isin", ASCENDING)], name="idx_securities_isin")
        db.securities.create_index([("series", ASCENDING)], name="idx_securities_series")
    except Exception as e:
        logger.warning(f"Could not create securities indexes: {e}")

    # 2. Stock Daily History Collection
    try:
        db.stock_daily_history.create_index(
            [("symbol", ASCENDING), ("series", ASCENDING), ("trade_date", ASCENDING)],
            unique=True,
            name="idx_stock_unique_bar",
        )
        db.stock_daily_history.create_index([("trade_date", DESCENDING)], name="idx_stock_trade_date")
        db.stock_daily_history.create_index([("symbol", ASCENDING), ("trade_date", DESCENDING)], name="idx_stock_sym_date")
        db.stock_daily_history.create_index([("turnover", DESCENDING)], name="idx_stock_turnover")
        db.stock_daily_history.create_index([("trade_date", DESCENDING), ("turnover", DESCENDING)], name="idx_stock_date_turnover")
    except Exception as e:
        logger.warning(f"Could not create stock_daily_history indexes: {e}")

    # 3. Trading Calendar Collection
    try:
        db.trading_calendar.create_index([("trade_date", ASCENDING)], unique=True, name="idx_trade_date_unique")
    except Exception as e:
        logger.warning(f"Could not create trading_calendar indexes: {e}")

    # 4. Ingestion Jobs Collection
    try:
        db.ingestion_jobs.create_index([("job_id", ASCENDING)], unique=True, name="idx_job_id_unique")
        db.ingestion_jobs.create_index([("started_at", DESCENDING)], name="idx_job_started_at")
    except Exception as e:
        logger.warning(f"Could not create ingestion_jobs indexes: {e}")

    logger.info("MongoDB collections and indexes initialized successfully.")


def _clean_doc_value(v: Any) -> Any:
    """Sanitizes python date/decimal/float values for clean BSON storage."""
    if isinstance(v, (date, datetime)):
        return v.strftime("%Y-%m-%d") if isinstance(v, date) and not isinstance(v, datetime) else v.isoformat()
    if hasattr(v, "__float__"):
        try:
            return float(v)
        except (ValueError, TypeError):
            pass
    return v


def sanitize_doc(record: dict[str, Any]) -> dict[str, Any]:
    """Sanitizes a dictionary record for insertion into MongoDB."""
    clean = {}
    for k, v in record.items():
        if k == "_id":
            clean[k] = v
            continue
        clean[k] = _clean_doc_value(v)
    return clean


def bulk_upsert_stock_history_mongo(records: list[dict[str, Any]], batch_size: int = 2000) -> int:
    """Performs high-speed bulk ingestion into MongoDB 'stock_daily_history'."""
    if not records:
        return 0

    settings = get_settings()
    if not settings.enable_mongodb:
        return 0

    db = get_mongo_db()
    collection = db.stock_daily_history

    total_upserted = 0
    clean_docs = []
    for r in records:
        clean = sanitize_doc(r)
        if clean.get("symbol") and clean.get("trade_date"):
            clean_docs.append(clean)

    for i in range(0, len(clean_docs), batch_size):
        chunk = clean_docs[i : i + batch_size]
        try:
            res = collection.insert_many(chunk, ordered=False)
            total_upserted += len(res.inserted_ids)
        except BulkWriteError as bwe:
            # Handle duplicates when re-ingesting or updating existing bars
            write_errors = bwe.details.get("writeErrors", [])
            total_upserted += bwe.details.get("nInserted", 0)
            dup_indices = {err["index"] for err in write_errors if err.get("code") == 11000}
            if dup_indices:
                ops = [
                    UpdateOne(
                        {
                            "symbol": chunk[idx]["symbol"],
                            "series": chunk[idx].get("series", "EQ"),
                            "trade_date": chunk[idx]["trade_date"],
                        },
                        {"$set": chunk[idx]},
                        upsert=True,
                    )
                    for idx in dup_indices
                ]
                if ops:
                    res_upsert = collection.bulk_write(ops, ordered=False)
                    total_upserted += (res_upsert.upserted_count + res_upsert.modified_count + res_upsert.matched_count)
        except Exception as e:
            logger.warning(f"Failed to write daily records to MongoDB: {e}")

    return total_upserted


def bulk_upsert_securities_mongo(records: list[dict[str, Any]]) -> int:
    """Upserts security master metadata into MongoDB 'securities' collection."""
    if not records:
        return 0

    settings = get_settings()
    if not settings.enable_mongodb:
        return 0

    db = get_mongo_db()
    collection = db.securities

    ops = []
    for r in records:
        clean = sanitize_doc(r)
        sym = clean.get("symbol")
        ser = clean.get("series", "EQ")
        if not sym:
            continue
        ops.append(
            UpdateOne(
                {"symbol": sym, "series": ser},
                {"$set": clean},
                upsert=True,
            )
        )

    if ops:
        res = collection.bulk_write(ops, ordered=False)
        return res.upserted_count + res.modified_count + res.matched_count
    return 0


def get_mongo_stats() -> dict[str, Any]:
    """Retrieves document counts and collection stats for MongoDB Compass verification."""
    try:
        db = get_mongo_db()
        return {
            "connected": True,
            "database": db.name,
            "collections": {
                "stock_daily_history": db.stock_daily_history.count_documents({}),
                "securities": db.securities.count_documents({}),
                "trading_calendar": db.trading_calendar.count_documents({}),
                "ingestion_jobs": db.ingestion_jobs.count_documents({}),
                "corporate_actions": db.corporate_actions.count_documents({}),
            },
        }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
        }
