"""Target-column inference for prediction-ready datasets."""
from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Any

import pandas as pd


ID_HINTS = ("id", "uuid", "guid", "email", "phone", "name", "address", "url", "website")
REGRESSION_HINTS = ("sales", "revenue", "amount", "profit", "price", "total", "value", "income", "cost")
CLASSIFICATION_HINTS = ("churn", "status", "class", "category", "label", "target", "outcome", "approved", "converted")
QUERY_TARGET_ALIASES = {
    "sales": REGRESSION_HINTS,
    "revenue": ("revenue", "sales", "amount", "total", "profit"),
    "amount": ("amount", "total", "sales", "revenue"),
    "profit": ("profit", "margin", "net"),
    "churn": ("churn", "churned", "cancel", "retention"),
}


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def _name_score(column: str, hints: tuple[str, ...]) -> float:
    normalized = _normalize(column)
    tokens = set(normalized.split("_"))
    score = 0.0
    for hint in hints:
        hint_norm = _normalize(hint)
        if normalized == hint_norm:
            return 1.0
        if hint_norm in normalized:
            score = max(score, 0.9)
        if hint_norm in tokens:
            score = max(score, 0.82)
        score = max(score, SequenceMatcher(None, normalized, hint_norm).ratio() * 0.7)
    return score


def is_identifier_like(series: pd.Series, column: str) -> bool:
    normalized = _normalize(column)
    non_null = series.dropna()
    unique_ratio = float(non_null.nunique(dropna=True)) / max(1, len(non_null))
    if any(hint in normalized for hint in ID_HINTS):
        if unique_ratio > 0.65 or not pd.api.types.is_numeric_dtype(series):
            return True
    if unique_ratio > 0.95 and len(non_null) >= 20 and not pd.api.types.is_numeric_dtype(series):
        return True
    return False


def _task_for_column(series: pd.Series) -> str | None:
    non_null = series.dropna()
    if len(non_null) < 10:
        return None
    unique_count = int(non_null.nunique(dropna=True))
    unique_ratio = unique_count / max(1, len(non_null))
    if pd.api.types.is_bool_dtype(series):
        return "classification"
    if pd.api.types.is_numeric_dtype(series):
        if 2 <= unique_count <= max(20, int(len(non_null) * 0.2)):
            return "classification"
        return "regression"
    if 2 <= unique_count <= max(20, int(len(non_null) * 0.4)):
        return "classification"
    if unique_ratio <= 0.3 and unique_count >= 2:
        return "classification"
    return None


def _target_confidence(column: str, series: pd.Series, task_type: str) -> float:
    non_null = series.dropna()
    usable_ratio = float(len(non_null)) / max(1, len(series))
    unique_count = int(non_null.nunique(dropna=True))
    unique_ratio = unique_count / max(1, len(non_null))
    if task_type == "regression":
        base = 0.55
        base += min(0.2, _name_score(column, REGRESSION_HINTS) * 0.2)
        if pd.api.types.is_numeric_dtype(series):
            base += 0.12
        if unique_ratio > 0.7:
            base += 0.08
        if unique_count < 5:
            base -= 0.25
    else:
        base = 0.52
        base += min(0.2, _name_score(column, CLASSIFICATION_HINTS) * 0.2)
        if unique_count <= max(10, int(len(non_null) * 0.25)):
            base += 0.12
        if unique_ratio <= 0.3:
            base += 0.08
        if unique_count <= 2:
            base -= 0.05
    if is_identifier_like(series, column):
        base -= 0.45
    if pd.api.types.is_numeric_dtype(series) and task_type == "classification" and unique_count > 20:
        base -= 0.15
    return round(float(max(0.0, min(0.99, base + min(0.12, usable_ratio * 0.12)))), 3)


def suggest_targets(df: pd.DataFrame, limit: int = 6) -> list[dict[str, Any]]:
    """Suggest safe prediction targets while avoiding IDs and unique identifiers."""
    suggestions: list[dict[str, Any]] = []
    for column in df.columns:
        series = df[column]
        if is_identifier_like(series, str(column)):
            continue
        task_type = _task_for_column(series)
        if not task_type:
            continue
        regression_score = _name_score(str(column), REGRESSION_HINTS)
        classification_score = _name_score(str(column), CLASSIFICATION_HINTS)
        name_bonus = regression_score if task_type == "regression" else classification_score
        normalized = _normalize(column)
        if task_type == "classification" and normalized in {"category", "region", "type", "segment"}:
            name_bonus *= 0.45
        usable_rows = int(series.notna().sum())
        score = _target_confidence(str(column), series, task_type)
        suggestions.append(
            {
                "column": str(column),
                "task_type": task_type,
                "score": round(float(score), 3),
                "confidence": round(float(score), 3),
                "reason": (
                    "Numeric target suitable for regression"
                    if task_type == "regression"
                    else "Low-cardinality target suitable for classification"
                ),
                "non_null_rows": usable_rows,
                "unique_values": int(series.nunique(dropna=True)),
                "safe": bool(score >= 0.5),
            }
        )
    suggestions.sort(key=lambda item: (item["score"], item["non_null_rows"]), reverse=True)
    return suggestions[:limit]


def infer_target_column(
    df: pd.DataFrame,
    query: str | None = None,
    selected_target: str | None = None,
    minimum_confidence: float = 0.0,
) -> dict[str, Any] | None:
    """Infer a target from an explicit selection, query wording, or ranked suggestions."""
    suggestions = suggest_targets(df, limit=max(6, len(df.columns)))
    by_column = {item["column"].lower(): item for item in suggestions}
    if selected_target:
        for column in df.columns:
            if str(column).lower() == selected_target.lower() and str(column).lower() in by_column:
                return by_column[str(column).lower()]
        return None

    query_lower = (query or "").lower()
    if query_lower:
        for keyword, aliases in QUERY_TARGET_ALIASES.items():
            if keyword in query_lower:
                best = max(
                    suggestions,
                    key=lambda item: _name_score(item["column"], tuple(aliases)),
                    default=None,
                )
                if best and _name_score(best["column"], tuple(aliases)) >= 0.55 and best["score"] >= minimum_confidence:
                    return best
        for suggestion in suggestions:
            if _normalize(suggestion["column"]).replace("_", " ") in query_lower and suggestion["score"] >= minimum_confidence:
                return suggestion

    if not suggestions:
        return None
    best = suggestions[0]
    if best["score"] < minimum_confidence:
        return None
    return best
