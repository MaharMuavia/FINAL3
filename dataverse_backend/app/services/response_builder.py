"""Grounded response helpers for generic dataset answers."""
from __future__ import annotations

from typing import Any

import pandas as pd

from .data_profiler import profile_dataframe
from .recommendation_engine import follow_up_suggestions


def _table(columns: list[str], rows: list[dict[str, Any]], title: str) -> dict[str, Any]:
    return {"title": title, "columns": columns, "rows": rows}


def build_dataset_overview(
    df: pd.DataFrame,
    dataset_type: str,
    filename: str | None = None,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = profile or profile_dataframe(df)
    rows = profile["row_count"]
    cols = profile["column_count"]
    suggestions = follow_up_suggestions(dataset_type, profile.get("semantic_columns", {}))

    result = {
        "intent": "dataset_overview",
        "dataset_type": dataset_type,
        "answer": "",
        "method": "Profiled dataframe shape, column roles, missing values and sample values.",
        "tables": [],
        "charts": [],
        "warnings": [],
        "recommendations": [],
        "profile": profile,
        "suggestions": suggestions,
    }

    if cols == 1:
        column = profile["columns"][0] if profile["columns"] else "the uploaded column"
        result["answer"] = (
            f"This file has only one column and {rows:,} rows, so analysis is limited. "
            f"The column is `{column}`. I can summarize the text entries, count unique values, "
            "detect repeated items, and explain what kind of structured columns are needed for deeper business analytics."
        )
    else:
        missing = profile["quality"]["total_missing"]
        role_pairs = [
            f"{column} as {role}"
            for column, role in profile.get("column_roles", {}).items()
            if role not in {"unknown", "generic_text", "generic_id"}
        ][:8]
        role_sentence = f" Detected roles include {', '.join(role_pairs)}." if role_pairs else ""
        source = f" from `{filename}`" if filename else ""
        result["answer"] = (
            f"This appears to be a {dataset_type.replace('_', ' ')} dataset{source}. "
            f"It has {rows:,} rows and {cols} columns, with {missing:,} missing cells.{role_sentence} "
            "I will only answer questions that can be calculated from these columns."
        )

    result["tables"].append(
        _table(
            ["name", "dtype", "role", "missing", "missing_pct", "unique"],
            profile["column_profiles"],
            "Column profile",
        )
    )
    return result
