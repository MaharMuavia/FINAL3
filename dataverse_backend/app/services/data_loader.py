"""File loading helpers for CSV and Excel uploads."""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd


def load_dataframe(filename: str, contents: bytes) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    buffer = io.BytesIO(contents)
    if suffix == ".csv":
        return pd.read_csv(buffer)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(buffer)
    raise ValueError("Unsupported file format. Supported: CSV, XLSX, XLS")
