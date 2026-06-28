"""Database session and connection management."""

import logging
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from src.config import DATABASE_URL

logger = logging.getLogger(__name__)

# SQLAlchemy 2.0 Base model
Base = declarative_base()

# Engine configuration with connection pooling
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Initialize the database by ensuring pgvector extension and creating tables."""
    with engine.connect() as conn:
        logger.info("Ensuring PostgreSQL vector extension is enabled...")
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()

    # Import models here to ensure they are registered with Base.metadata
    import src.db.models  # noqa: F401

    logger.info("Creating all database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized successfully.")


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and safely close it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
