"""SQLAlchemy engine and request-scoped database sessions.

SQLite remains the local default. Hosted deployments use DATABASE_URL with
PostgreSQL and psycopg; Render's internal connection string is normalised here.
"""
import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def normalize_database_url(raw_url: str) -> str:
    """Return a SQLAlchemy URL using psycopg for PostgreSQL."""
    value = raw_url.strip()
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value[len("postgres://"):]
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value[len("postgresql://"):]
    return value


DATABASE_URL = normalize_database_url(
    os.getenv("DATABASE_URL", "sqlite:///./proxyproof.db")
)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=300,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Base class for database models."""


def get_db() -> Generator[Session, None, None]:
    """Yield one database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
