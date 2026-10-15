"""Database connection and engine management."""

import logging

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import declarative_base

from nse_pipeline.core.config import get_settings
from nse_pipeline.core.exceptions import DatabaseError

logger = logging.getLogger("nse_pipeline.database.connection")

Base = declarative_base()

_engine: Engine | None = None


def get_engine(force_new: bool = False) -> Engine:
    """Returns the configured SQLAlchemy engine.

    Tries to connect to MySQL first. If MySQL is unreachable and use_sqlite_fallback
    is enabled in settings, smoothly falls back to local SQLite database.
    """
    global _engine
    if _engine is not None and not force_new:
        return _engine

    settings = get_settings()

    # Try MySQL first if configured
    if settings.db_dialect.lower() == "mysql":
        try:
            target_display = (
                settings.mysql_connection_url.split("@")[-1]
                if "@" in settings.mysql_connection_url
                else f"{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}"
            )
            logger.info(f"Attempting connection to MySQL at {target_display}")
            engine = create_engine(
                settings.mysql_connection_url,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
                pool_recycle=3600,
            )
            # Test connection
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Successfully established connection to MySQL.")
            _engine = engine
            return _engine
        except Exception as e:
            logger.warning(f"Could not connect to MySQL: {e}")
            if not settings.use_sqlite_fallback:
                raise DatabaseError(f"Failed to connect to MySQL and SQLite fallback is disabled: {e}") from e
            logger.info("Falling back to SQLite database for development and test execution.")

    # SQLite fallback
    engine = create_engine(
        settings.sqlite_connection_url,
        connect_args={"check_same_thread": False, "timeout": 60},
        pool_pre_ping=True,
    )
    with engine.connect() as conn:
        try:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA synchronous=NORMAL"))
            conn.execute(text("PRAGMA busy_timeout=60000"))
        except Exception:
            pass
        conn.execute(text("SELECT 1"))
    logger.info(f"Connected to SQLite at {settings.sqlite_db_path} (WAL mode enabled)")
    _engine = engine
    return _engine


def is_mysql(engine: Engine | None = None) -> bool:
    """Checks whether the active engine is using MySQL."""
    eng = engine or get_engine()
    return "mysql" in eng.dialect.name.lower()
