"""Shared response helpers for deterministic agent tools."""
from __future__ import annotations

from typing import Any

import pandas as pd

from .data_profiler import profile_dataframe


def build_dataset_overview(
    df: pd.DataFrame,
    dataset_type: str,
    *,
    filename: str | None = None,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = profile or profile_dataframe(df)
    rows = [
        {"metric": "Rows", "value": int(len(df))},
        {"metric": "Columns", "value": int(len(df.columns))},
        {"metric": "Dataset type", "value": dataset_type},
    ]
    filename_part = f" from {filename}" if filename else ""
    if len(df.columns) == 1:
        answer = f"This {dataset_type} dataset{filename_part} has only one column and {len(df)} rows."
    elif dataset_type == "business_leads":
        website_col = profile.get("semantic_columns", {}).get("website")
        missing_websites = int(df[website_col].isna().sum() + (df[website_col].astype(str).str.strip() == "").sum()) if website_col in df.columns else 0
        answer = f"This business leads dataset{filename_part} has {len(df)} business records across {len(df.columns)} columns, including website coverage and lead attributes."
        if website_col:
            answer += f" {missing_websites} records are missing website values."
    else:
        answer = f"This {dataset_type} dataset{filename_part} has {len(df)} rows and {len(df.columns)} columns."
    return {
        "intent": "dataset_overview",
        "dataset_type": dataset_type,
        "answer": answer,
        "method": "Profiled dataset shape, column roles, and basic schema metadata.",
        "tables": [{"title": "Dataset overview", "columns": ["metric", "value"], "rows": rows}],
        "charts": [],
        "warnings": [],
        "recommendations": [],
        "profile": profile,
    }
