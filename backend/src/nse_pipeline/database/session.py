"""Database session management and context helpers."""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy.orm import Session, sessionmaker

from nse_pipeline.core.logging import get_logger
from nse_pipeline.database.connection import Base, get_engine

logger = get_logger("database.session")

_session_factory = None


def get_session_factory() -> sessionmaker:
    """Returns the singleton sessionmaker instance."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return _session_factory


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager for acquiring and safely committing or rolling back a database session."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Transaction rolled back due to error: {e}")
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for database sessions."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def init_db(engine=None) -> None:
    """Initializes tables using metadata reflection/creation."""
    import nse_pipeline.database.models  # noqa: F401 - register models on Base
    eng = engine or get_engine()
    logger.info(f"Initializing database schema on {eng.url}...")
    Base.metadata.create_all(bind=eng)
    logger.info("Database schema initialized successfully.")
