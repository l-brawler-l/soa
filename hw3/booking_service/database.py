"""Database connection and session management."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Generator
import logging

from .config import settings
from .models import Base

logger = logging.getLogger(__name__)

# Create engine
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize database - tables are created via Alembic migrations."""
    # Note: Database schema is now managed by Alembic migrations
    # Tables are created by running: alembic upgrade head
    # This is done automatically in the Docker CMD
    logger.info("Database connection ready (schema managed by Alembic)")


def get_db() -> Generator[Session, None, None]:
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
