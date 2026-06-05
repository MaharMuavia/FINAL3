"""DatasetAgent for file validation, parsing, normalization, and profiling."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any
import pandas as pd
from fastapi import HTTPException, UploadFile

from ..api.upload_parsing import parse_uploaded_dataframe
from ..services.session_store import create_session_id, persist_dataframe_for_session
from ..services.data_profiler import profile_dataframe
from ..services.data_quality import compute_data_quality
from ..core.config import settings
from ..core.logger import logger


class DatasetAgent:
    """Agent responsible for dataset ingestion, validation, parsing, normalization, and profiling."""

    def __init__(self):
        self.max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    def validate_file(self, filename: str, content_length: int) -> None:
        """Validate filename and file size limits."""
        if content_length <= 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        if content_length > self.max_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit"
            )
        if not filename.lower().endswith((".csv", ".xlsx", ".xls")):
            raise HTTPException(
                status_code=400,
                detail="Only CSV and Excel files are supported"
            )

    def normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize column headers to clean string formats."""
        df = df.copy()
        new_columns = []
        for i, col in enumerate(df.columns):
            col_name = str(col).strip()
            if not col_name:
                col_name = f"unnamed_{i}"
            new_columns.append(col_name)
        df.columns = new_columns
        return df

    def parse_and_process(self, filename: str, contents: bytes) -> tuple[str, pd.DataFrame, dict[str, Any], dict[str, Any]]:
        """Parses contents, normalizes columns, saves session, and returns profile + quality report."""
        self.validate_file(filename, len(contents))
        try:
            df = parse_uploaded_dataframe(filename, contents)
        except Exception as exc:
            logger.exception("Parsing failed in DatasetAgent")
            raise HTTPException(status_code=400, detail=f"Invalid file upload: {exc}") from exc

        # Normalize columns
        df = self.normalize_columns(df)

        # Create session and save
        session_id = create_session_id()
        persist_dataframe_for_session(session_id, df, filename=filename)

        # Profile & Data Quality
        profile = profile_dataframe(df)
        quality = compute_data_quality(df)

        return session_id, df, profile, quality
