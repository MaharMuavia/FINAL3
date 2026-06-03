"""SQLAlchemy ORM models for DataVerse AI.

Simplified to 2 core models: Dataset and QueryHistory.
Uses generic column types for SQLite compatibility.
Single Base registry — no duplicates.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, DateTime, Text, JSON
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class Dataset(Base):
    """Stores metadata for each uploaded dataset.

    Tracks original filename, row/column counts, profile data,
    storage path, and status.
    """
    __tablename__ = "datasets"

    id = Column(String(36), primary_key=True, default=_new_id)
    filename = Column(String(512), nullable=False)
    storage_path = Column(Text, nullable=False)
    file_type = Column(String(10), nullable=False)  # csv, xlsx
    row_count = Column(Integer, nullable=True)
    col_count = Column(Integer, nullable=True)
    columns_json = Column(JSON, nullable=True)  # list of column names
    profile_json = Column(JSON, nullable=True)  # full profile dict
    status = Column(String(50), default="ready", nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class QueryHistory(Base):
    """Stores user queries and their results for audit and history."""
    __tablename__ = "query_history"

    id = Column(String(36), primary_key=True, default=_new_id)
    dataset_id = Column(String(36), nullable=False, index=True)
    prompt = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    result_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
