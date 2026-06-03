"""Data Analysis & Prediction Agent (Agent 2).

Receives a pandas DataFrame, a user prompt, and structured output from
the Data Understanding Agent (Agent 1).  Performs deterministic analysis
using pandas / numpy / sklearn and returns a structured result dict.

This module is intentionally self-contained — it does NOT import from any
``app.*`` packages so it can be tested and used independently.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_TABLE_ROWS: int = 20
_MIN_ROWS_FOR_ML: int = 20
_DISPLAY_DECIMALS: int = 2

# Keyword groups used to classify what the user is asking for.
_INTENT_KEYWORDS: dict[str, list[str]] = {
    "top":       ["top", "best", "highest", "lowest", "worst", "most", "least",
                  "biggest", "smallest", "largest", "maximum", "minimum"],
    "trend":     ["trend", "monthly", "weekly", "daily", "yearly", "quarterly",
                  "over time", "time series", "growth", "decline", "seasonal"],
    "predict":   ["predict", "forecast", "future", "projection", "estimate",
                  "next month", "next quarter", "next year"],
    "segment":   ["segment", "cluster", "group by behavior", "kmeans",
                  "customer segment", "classify customers"],
    "correlate": ["correlat", "relationship", "association", "depends on",
                  "related to", "impact of", "effect of"],
    "quality":   ["clean", "quality", "issue", "missing", "duplicate",
                  "outlier", "anomaly", "data problem"],
    "summary":   ["summary", "overview", "describe", "statistics",
                  "distribution", "general info", "snapshot"],
    "compare":   ["compare", "versus", "vs", "difference between",
                  "against", "contrast"],
    "filter":    ["filter", "find", "where", "show me", "list",
                  "which", "search for"],
    "recommend": ["recommend", "suggest", "advice", "insight",
                  "opportunity", "improve", "optimiz"],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _round(value: Any) -> Any:
    """Round numeric scalars to display precision; pass through others."""
    if isinstance(value, float):
        return round(value, _DISPLAY_DECIMALS)
    if isinstance(value, (np.floating, np.integer)):
        return round(float(value), _DISPLAY_DECIMALS)
    return value


def _safe_json_value(value: Any) -> Any:
    """Convert numpy / pandas types to JSON-safe Python types."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return round(float(value), _DISPLAY_DECIMALS)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (np.ndarray,)):
        return [_safe_json_value(v) for v in value.tolist()]
    return value


def _df_to_records(df: pd.DataFrame, max_rows: int = _MAX_TABLE_ROWS) -> list[dict]:
    """Convert a DataFrame to a list of JSON-safe dicts, capped at *max_rows*."""
    records = df.head(max_rows).to_dict(orient="records")
    return [
        {str(k): _safe_json_value(v) for k, v in row.items()}
        for row in records
    ]


def _make_table(title: str, df: pd.DataFrame) -> dict:
    """Build a table payload from a DataFrame."""
    rows = _df_to_records(df)
    return {
        "title": title,
        "columns": [str(c) for c in df.columns],
        "rows": rows,
    }


def _make_chart(
    title: str,
    chart_type: str,
    x_key: str,
    y_key: str,
    df: pd.DataFrame,
) -> dict:
    """Build a chart payload from a DataFrame."""
    return {
        "title": title,
        "type": chart_type,
        "x_key": x_key,
        "y_key": y_key,
        "data": _df_to_records(df, max_rows=50),
    }


def _empty_result() -> dict[str, Any]:
    """Return the canonical empty result structure."""
    return {
        "answer": "",
        "calculations": {},
        "tables": [],
        "charts": [],
        "model_result": {},
        "recommendations": [],
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------


def _detect_intent(prompt: str) -> str:
    """Return the best-matching intent key from ``_INTENT_KEYWORDS``.

    Falls back to ``"summary"`` if nothing matches.
    """
    prompt_lower = prompt.lower()
    scores: dict[str, int] = {}
    for intent, keywords in _INTENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in prompt_lower)
        if score:
            scores[intent] = score
    if not scores:
        return "summary"
    return max(scores, key=scores.get)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Column resolution helpers
# ---------------------------------------------------------------------------


def _resolve_column(
    df: pd.DataFrame,
    candidates: list[str],
    understanding: dict[str, Any],
) -> str | None:
    """Try to find the first column from *candidates* that exists in *df*."""
    columns_lower = {str(c).lower(): str(c) for c in df.columns}
    for name in candidates:
        if name and str(name).lower() in columns_lower:
            return columns_lower[str(name).lower()]
    return None


def _get_date_col(df: pd.DataFrame, understanding: dict[str, Any]) -> str | None:
    """Return the best date column from the understanding output or detection."""
    detected = understanding.get("detected_columns", {})
    date_candidates = detected.get("date_columns", [])
    col = _resolve_column(df, date_candidates, understanding)
    if col:
        return col
    # Fallback: find first datetime column
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            return str(c)
    return None


def _get_numeric_cols(df: pd.DataFrame, understanding: dict[str, Any]) -> list[str]:
    """Return numeric column names, preferring understanding output."""
    detected = understanding.get("detected_columns", {})
    candidates: list[str] = []
    for key in ("revenue_columns", "sales_columns", "quantity_columns"):
        candidates.extend(detected.get(key, []))
    resolved = [
        c for c in candidates
        if c in df.columns and pd.api.types.is_numeric_dtype(df[c])
    ]
    if resolved:
        return resolved
    return [str(c) for c in df.select_dtypes(include=["number"]).columns]


def _get_category_col(df: pd.DataFrame, understanding: dict[str, Any]) -> str | None:
    """Return the best categorical / product / group column."""
    detected = understanding.get("detected_columns", {})
    for key in ("product_columns", "category_columns", "customer_columns"):
        col = _resolve_column(df, detected.get(key, []), understanding)
        if col:
            return col
    # Fallback: first object column with reasonable cardinality
    for c in df.columns:
        if pd.api.types.is_object_dtype(df[c]) or pd.api.types.is_string_dtype(df[c]):
            nunique = df[c].nunique(dropna=True)
            if 2 <= nunique <= 200:
                return str(c)
    return None


def _get_target_col(df: pd.DataFrame, understanding: dict[str, Any]) -> str | None:
    """Return the best prediction target column."""
    detected = understanding.get("detected_columns", {})
    candidates = detected.get("target_candidates", [])
    if isinstance(candidates, list):
        # Each candidate may be a dict {"column": ..., "task_type": ...}
        for item in candidates:
            name = item.get("column") if isinstance(item, dict) else item
            if name and str(name) in df.columns:
                return str(name)
    # Fallback to first revenue / sales column
    for key in ("revenue_columns", "sales_columns"):
        col = _resolve_column(df, detected.get(key, []), understanding)
        if col:
            return col
    return None


def _extract_mentioned_column(prompt: str, df: pd.DataFrame) -> str | None:
    """Try to find a column name explicitly mentioned in the user prompt."""
    prompt_lower = prompt.lower()
    # Sort by length descending so longer names match first
    for col in sorted(df.columns, key=lambda c: len(str(c)), reverse=True):
        if str(col).lower() in prompt_lower:
            return str(col)
    return None


def _extract_number_from_prompt(prompt: str, default: int = 10) -> int:
    """Extract a number like 'top 5' or 'bottom 15' from the prompt."""
    match = re.search(r"\b(?:top|bottom|first|last|best|worst)\s+(\d+)\b", prompt, re.IGNORECASE)
    if match:
        return min(int(match.group(1)), _MAX_TABLE_ROWS)
    return default


# ---------------------------------------------------------------------------
# Analysis handlers — one per intent
# ---------------------------------------------------------------------------


def _handle_top(
    df: pd.DataFrame,
    prompt: str,
    understanding: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Handle top/best/highest/lowest queries via groupby + sort."""
    n = _extract_number_from_prompt(prompt)
    ascending = any(kw in prompt.lower() for kw in ["lowest", "worst", "least", "smallest", "minimum", "bottom"])

    category_col = _extract_mentioned_column(prompt, df) or _get_category_col(df, understanding)
    numeric_cols = _get_numeric_cols(df, understanding)

    if not category_col:
        result["answer"] = (
            "I could not identify a categorical column to group by. "
            "Please specify which column you'd like to rank."
        )
        result["warnings"].append("No suitable category column found for ranking.")
        return

    if not numeric_cols:
        result["answer"] = "No numeric columns available to rank by."
        result["warnings"].append("Dataset has no numeric columns for aggregation.")
        return

    value_col = numeric_cols[0]
    # Check if user mentions a specific numeric column
    for nc in numeric_cols:
        if str(nc).lower() in prompt.lower():
            value_col = nc
            break

    try:
        grouped = (
            df.groupby(category_col, dropna=True)[value_col]
            .sum()
            .reset_index()
            .sort_values(value_col, ascending=ascending)
            .head(n)
        )
        grouped[value_col] = grouped[value_col].round(_DISPLAY_DECIMALS)

        direction = "bottom" if ascending else "top"
        result["answer"] = (
            f"Here are the {direction} {len(grouped)} items by total {value_col}, "
            f"grouped by {category_col}."
        )
        result["calculations"] = {
            "group_column": category_col,
            "value_column": value_col,
            "aggregation": "sum",
            "direction": direction,
            "count": len(grouped),
        }
        result["tables"].append(_make_table(f"{direction.title()} {n} by {value_col}", grouped))
        result["charts"].append(
            _make_chart(
                f"{direction.title()} {n} {category_col} by {value_col}",
                "bar",
                category_col,
                value_col,
                grouped,
            )
        )
        result["recommendations"].append(
            f"Focus on the {direction} performers in '{category_col}' to understand "
            f"what drives {'low' if ascending else 'high'} {value_col}."
        )
    except Exception as exc:
        logger.exception("Error in top/rank analysis")
        result["answer"] = "An error occurred while computing the ranking."
        result["warnings"].append(f"Ranking analysis failed: {type(exc).__name__}")


def _handle_trend(
    df: pd.DataFrame,
    prompt: str,
    understanding: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Handle trend / time-series queries."""
    date_col = _get_date_col(df, understanding)
    numeric_cols = _get_numeric_cols(df, understanding)

    if not date_col:
        result["answer"] = (
            "No date column was found in the dataset, so I cannot perform a "
            "time-based trend analysis. Please ensure your data includes a date column."
        )
        result["warnings"].append("No date column available for trend analysis.")
        return

    if not numeric_cols:
        result["answer"] = "No numeric columns available to analyse over time."
        result["warnings"].append("Dataset has no numeric columns for trend analysis.")
        return

    value_col = numeric_cols[0]
    for nc in numeric_cols:
        if str(nc).lower() in prompt.lower():
            value_col = nc
            break

    try:
        df_copy = df[[date_col, value_col]].copy()
        df_copy[date_col] = pd.to_datetime(df_copy[date_col], errors="coerce")
        df_copy = df_copy.dropna(subset=[date_col, value_col])

        if df_copy.empty:
            result["answer"] = "After cleaning, no valid date + numeric rows remain."
            result["warnings"].append("All rows had invalid dates or missing numeric values.")
            return

        # Determine period from prompt
        prompt_lower = prompt.lower()
        if "daily" in prompt_lower or "day" in prompt_lower:
            freq, label = "D", "Day"
        elif "weekly" in prompt_lower or "week" in prompt_lower:
            freq, label = "W", "Week"
        elif "quarterly" in prompt_lower or "quarter" in prompt_lower:
            freq, label = "QS", "Quarter"
        elif "yearly" in prompt_lower or "year" in prompt_lower or "annual" in prompt_lower:
            freq, label = "YS", "Year"
        else:
            freq, label = "MS", "Month"

        df_copy = df_copy.set_index(date_col)
        trend = df_copy[value_col].resample(freq).sum().reset_index()
        trend.columns = [label, value_col]
        trend[label] = trend[label].astype(str)
        trend[value_col] = trend[value_col].round(_DISPLAY_DECIMALS)

        # Calculate overall growth
        if len(trend) >= 2:
            first_val = trend[value_col].iloc[0]
            last_val = trend[value_col].iloc[-1]
            if first_val and first_val != 0:
                growth_pct = round(((last_val - first_val) / abs(first_val)) * 100, _DISPLAY_DECIMALS)
                growth_direction = "grew" if growth_pct > 0 else "declined"
            else:
                growth_pct = None
                growth_direction = "changed"
        else:
            growth_pct = None
            growth_direction = "unchanged"

        growth_msg = ""
        if growth_pct is not None:
            growth_msg = f" Overall, {value_col} {growth_direction} by {abs(growth_pct)}%."

        result["answer"] = (
            f"Here is the {label.lower()}ly trend for {value_col} "
            f"from {trend[label].iloc[0]} to {trend[label].iloc[-1]}.{growth_msg}"
        )
        result["calculations"] = {
            "period": label,
            "value_column": value_col,
            "data_points": len(trend),
            "growth_pct": growth_pct,
        }
        result["tables"].append(_make_table(f"{value_col} by {label}", trend))
        result["charts"].append(
            _make_chart(f"{value_col} Trend ({label}ly)", "line", label, value_col, trend)
        )
        if growth_pct is not None and growth_pct < 0:
            result["recommendations"].append(
                f"{value_col} shows a declining trend ({growth_pct}%). "
                "Investigate recent periods to identify potential causes."
            )
        elif growth_pct is not None and growth_pct > 20:
            result["recommendations"].append(
                f"Strong growth in {value_col} ({growth_pct}%). "
                "Ensure operations can scale to sustain this trajectory."
            )
    except Exception as exc:
        logger.exception("Error in trend analysis")
        result["answer"] = "An error occurred while computing the trend."
        result["warnings"].append(f"Trend analysis failed: {type(exc).__name__}")


def _handle_predict(
    df: pd.DataFrame,
    prompt: str,
    understanding: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Handle predict / forecast queries using sklearn."""
    if len(df) < _MIN_ROWS_FOR_ML:
        result["answer"] = (
            f"The dataset has only {len(df)} rows. At least {_MIN_ROWS_FOR_ML} rows "
            "are needed for a meaningful prediction model."
        )
        result["warnings"].append("Too few rows for prediction.")
        return

    target_col = _get_target_col(df, understanding)
    if not target_col:
        result["answer"] = (
            "I could not identify a suitable target column for prediction. "
            "Please specify what you'd like to predict."
        )
        result["warnings"].append("No target column identified.")
        return

    # Determine task type
    target_series = df[target_col].dropna()
    unique_values = target_series.nunique()
    is_classification = (
        pd.api.types.is_object_dtype(target_series)
        or pd.api.types.is_bool_dtype(target_series)
        or (pd.api.types.is_numeric_dtype(target_series) and unique_values <= 20)
    )

    # Select feature columns: numeric only, exclude target
    feature_cols = [
        c for c in df.select_dtypes(include=["number"]).columns
        if str(c) != target_col
    ]

    if len(feature_cols) < 1:
        result["answer"] = (
            "Not enough numeric feature columns to build a prediction model. "
            "The model needs at least one numeric feature besides the target."
        )
        result["warnings"].append("Insufficient numeric features for modeling.")
        return

    try:
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import (
            mean_squared_error,
            r2_score,
            accuracy_score,
            f1_score,
        )

        model_df = df[feature_cols + [target_col]].dropna()
        if len(model_df) < _MIN_ROWS_FOR_ML:
            result["answer"] = (
                f"After removing missing values, only {len(model_df)} rows remain. "
                f"Need at least {_MIN_ROWS_FOR_ML} for modeling."
            )
            result["warnings"].append("Too few complete rows after dropping NAs.")
            return

        X = model_df[feature_cols].values  # noqa: N806
        if is_classification:
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.preprocessing import LabelEncoder

            le = LabelEncoder()
            y = le.fit_transform(model_df[target_col])
            X_train, X_test, y_train, y_test = train_test_split(  # noqa: N806
                X, y, test_size=0.2, random_state=42,
            )
            model = RandomForestClassifier(
                n_estimators=100, max_depth=10, random_state=42, n_jobs=-1,
            )
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            acc = round(float(accuracy_score(y_test, y_pred)), _DISPLAY_DECIMALS)
            f1 = round(
                float(f1_score(y_test, y_pred, average="weighted", zero_division=0)),
                _DISPLAY_DECIMALS,
            )

            # Feature importance
            importance = sorted(
                zip(feature_cols, model.feature_importances_),
                key=lambda x: x[1],
                reverse=True,
            )
            importance_df = pd.DataFrame(importance, columns=["Feature", "Importance"])
            importance_df["Importance"] = importance_df["Importance"].round(4)

            result["answer"] = (
                f"I built a Random Forest classification model to predict '{target_col}'. "
                f"Accuracy: {acc * 100}%, Weighted F1: {f1}. "
                f"The model used {len(feature_cols)} features on {len(model_df)} rows."
            )
            result["model_result"] = {
                "task_type": "classification",
                "target_column": target_col,
                "algorithm": "RandomForestClassifier",
                "features_used": feature_cols,
                "train_rows": len(X_train),
                "test_rows": len(X_test),
                "accuracy": acc,
                "f1_score": f1,
                "classes": le.classes_.tolist(),
                "feature_importance": importance[:10],
            }
            result["tables"].append(_make_table("Feature Importance", importance_df.head(10)))
            result["charts"].append(
                _make_chart(
                    "Feature Importance",
                    "bar",
                    "Feature",
                    "Importance",
                    importance_df.head(10),
                )
            )
        else:
            from sklearn.ensemble import RandomForestRegressor
            from sklearn.linear_model import LinearRegression

            y = model_df[target_col].values.astype(float)
            X_train, X_test, y_train, y_test = train_test_split(  # noqa: N806
                X, y, test_size=0.2, random_state=42,
            )

            # Use LinearRegression for small feature sets, RF for larger
            if len(feature_cols) <= 3:
                model = LinearRegression()
                algo_name = "LinearRegression"
            else:
                model = RandomForestRegressor(
                    n_estimators=100, max_depth=10, random_state=42, n_jobs=-1,
                )
                algo_name = "RandomForestRegressor"

            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            r2 = round(float(r2_score(y_test, y_pred)), _DISPLAY_DECIMALS)
            rmse = round(float(np.sqrt(mean_squared_error(y_test, y_pred))), _DISPLAY_DECIMALS)

            # Feature importance
            if hasattr(model, "feature_importances_"):
                importances = model.feature_importances_
            elif hasattr(model, "coef_"):
                importances = np.abs(model.coef_)
            else:
                importances = np.zeros(len(feature_cols))

            importance = sorted(
                zip(feature_cols, importances),
                key=lambda x: x[1],
                reverse=True,
            )
            importance_df = pd.DataFrame(importance, columns=["Feature", "Importance"])
            importance_df["Importance"] = importance_df["Importance"].round(4)

            result["answer"] = (
                f"I built a {algo_name} model to predict '{target_col}'. "
                f"R² Score: {r2}, RMSE: {rmse}. "
                f"The model used {len(feature_cols)} features on {len(model_df)} rows."
            )
            result["model_result"] = {
                "task_type": "regression",
                "target_column": target_col,
                "algorithm": algo_name,
                "features_used": feature_cols,
                "train_rows": len(X_train),
                "test_rows": len(X_test),
                "r2_score": r2,
                "rmse": rmse,
                "feature_importance": importance[:10],
            }
            result["tables"].append(_make_table("Feature Importance", importance_df.head(10)))
            result["charts"].append(
                _make_chart(
                    "Feature Importance",
                    "bar",
                    "Feature",
                    "Importance",
                    importance_df.head(10),
                )
            )

            if r2 < 0.3:
                result["warnings"].append(
                    f"The model's R² score ({r2}) is low, meaning predictions may not be "
                    "reliable. Consider adding more data or features."
                )
                result["recommendations"].append(
                    "The model has weak predictive power. Consider enriching the dataset "
                    "with additional features or collecting more data."
                )
            else:
                result["recommendations"].append(
                    f"The model explains {r2 * 100}% of variance in {target_col}. "
                    f"Top driver: {importance[0][0]}."
                )
    except ImportError:
        result["answer"] = "scikit-learn is not installed; prediction is unavailable."
        result["warnings"].append("sklearn not available.")
    except Exception as exc:
        logger.exception("Error in prediction analysis")
        result["answer"] = "An error occurred while building the prediction model."
        result["warnings"].append(f"Prediction failed: {type(exc).__name__}")


def _handle_segment(
    df: pd.DataFrame,
    prompt: str,
    understanding: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Handle segmentation / clustering queries using KMeans."""
    numeric_cols = _get_numeric_cols(df, understanding)
    if len(numeric_cols) < 2:
        # Fallback: use all available numeric columns
        numeric_cols = [str(c) for c in df.select_dtypes(include=["number"]).columns]

    if len(numeric_cols) < 2:
        result["answer"] = (
            "At least 2 numeric columns are needed for clustering, "
            f"but only {len(numeric_cols)} were found."
        )
        result["warnings"].append("Not enough numeric columns for segmentation.")
        return

    if len(df) < _MIN_ROWS_FOR_ML:
        result["answer"] = (
            f"The dataset has only {len(df)} rows — too few for meaningful clustering."
        )
        result["warnings"].append("Too few rows for segmentation.")
        return

    try:
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler

        cluster_df = df[numeric_cols].dropna()
        if len(cluster_df) < _MIN_ROWS_FOR_ML:
            result["answer"] = "Too few complete rows after removing missing values for clustering."
            result["warnings"].append("Insufficient clean rows for clustering.")
            return

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(cluster_df.values)  # noqa: N806

        # Determine optimal k (2-6) using inertia elbow heuristic
        n_clusters = _extract_number_from_prompt(prompt, default=0)
        if n_clusters < 2 or n_clusters > 10:
            max_k = min(6, len(cluster_df) // 5)
            max_k = max(max_k, 2)
            inertias: list[float] = []
            for k in range(2, max_k + 1):
                km = KMeans(n_clusters=k, random_state=42, n_init=10)
                km.fit(X_scaled)
                inertias.append(km.inertia_)
            # Simple elbow: biggest drop
            if len(inertias) >= 2:
                drops = [inertias[i] - inertias[i + 1] for i in range(len(inertias) - 1)]
                n_clusters = drops.index(max(drops)) + 2
            else:
                n_clusters = 3

        km_final = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = km_final.fit_predict(X_scaled)

        segment_df = cluster_df.copy()
        segment_df["Segment"] = labels

        # Build summary per segment
        summary = segment_df.groupby("Segment")[numeric_cols].mean().round(_DISPLAY_DECIMALS)
        summary.insert(0, "Count", segment_df.groupby("Segment").size())
        summary = summary.reset_index()

        result["answer"] = (
            f"I identified {n_clusters} distinct segments using K-Means clustering "
            f"on {len(numeric_cols)} numeric features across {len(cluster_df)} rows."
        )
        result["calculations"] = {
            "algorithm": "KMeans",
            "n_clusters": n_clusters,
            "features_used": numeric_cols,
            "total_rows_clustered": len(cluster_df),
        }
        result["tables"].append(_make_table("Segment Profiles (Averages)", summary))
        # Chart: segment sizes
        size_df = summary[["Segment", "Count"]].copy()
        size_df["Segment"] = size_df["Segment"].astype(str)
        result["charts"].append(
            _make_chart("Segment Sizes", "pie", "Segment", "Count", size_df)
        )
        result["recommendations"].append(
            "Review each segment's average values to develop targeted strategies. "
            "High-value segments may warrant premium treatment."
        )
    except ImportError:
        result["answer"] = "scikit-learn is not installed; segmentation is unavailable."
        result["warnings"].append("sklearn not available.")
    except Exception as exc:
        logger.exception("Error in segmentation analysis")
        result["answer"] = "An error occurred while performing segmentation."
        result["warnings"].append(f"Segmentation failed: {type(exc).__name__}")


def _handle_correlate(
    df: pd.DataFrame,
    prompt: str,
    understanding: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Handle correlation / relationship queries."""
    numeric_cols = [str(c) for c in df.select_dtypes(include=["number"]).columns]
    if len(numeric_cols) < 2:
        result["answer"] = (
            "At least 2 numeric columns are required for correlation analysis, "
            f"but only {len(numeric_cols)} were found."
        )
        result["warnings"].append("Insufficient numeric columns for correlation.")
        return

    try:
        corr_matrix = df[numeric_cols].corr().round(_DISPLAY_DECIMALS)

        # Find top correlated pairs (excluding self-correlation)
        pairs: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for i, col_a in enumerate(numeric_cols):
            for j, col_b in enumerate(numeric_cols):
                if i >= j:
                    continue
                key = (col_a, col_b)
                if key not in seen:
                    seen.add(key)
                    corr_val = corr_matrix.loc[col_a, col_b]
                    if not pd.isna(corr_val):
                        pairs.append({
                            "Column A": col_a,
                            "Column B": col_b,
                            "Correlation": round(float(corr_val), _DISPLAY_DECIMALS),
                        })

        pairs.sort(key=lambda p: abs(p["Correlation"]), reverse=True)
        top_pairs = pairs[:_MAX_TABLE_ROWS]
        top_df = pd.DataFrame(top_pairs) if top_pairs else pd.DataFrame(
            columns=["Column A", "Column B", "Correlation"]
        )

        if top_pairs:
            strongest = top_pairs[0]
            strength = "strong" if abs(strongest["Correlation"]) > 0.7 else (
                "moderate" if abs(strongest["Correlation"]) > 0.4 else "weak"
            )
            result["answer"] = (
                f"The strongest correlation is between '{strongest['Column A']}' and "
                f"'{strongest['Column B']}' ({strongest['Correlation']}), which is {strength}. "
                f"I found {len(pairs)} numeric column pairs."
            )
        else:
            result["answer"] = "No valid correlations were found among the numeric columns."

        result["calculations"] = {
            "numeric_columns_analyzed": numeric_cols,
            "total_pairs": len(pairs),
        }
        if not top_df.empty:
            result["tables"].append(_make_table("Top Correlations", top_df))
        # Full correlation matrix as a table
        corr_display = corr_matrix.reset_index().rename(columns={"index": "Column"})
        result["tables"].append(_make_table("Correlation Matrix", corr_display))

        # Recommendations based on strong correlations
        for pair in top_pairs[:3]:
            val = pair["Correlation"]
            if abs(val) > 0.7:
                direction = "positively" if val > 0 else "negatively"
                result["recommendations"].append(
                    f"'{pair['Column A']}' and '{pair['Column B']}' are strongly "
                    f"{direction} correlated ({val}). Changes in one likely affect the other."
                )
    except Exception as exc:
        logger.exception("Error in correlation analysis")
        result["answer"] = "An error occurred while computing correlations."
        result["warnings"].append(f"Correlation analysis failed: {type(exc).__name__}")


def _handle_quality(
    df: pd.DataFrame,
    prompt: str,
    understanding: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Handle data quality / cleaning queries."""
    try:
        total_cells = df.size
        total_rows = len(df)

        # Missing values
        missing = df.isnull().sum()
        missing_pct = (missing / max(1, total_rows) * 100).round(_DISPLAY_DECIMALS)
        missing_report = pd.DataFrame({
            "Column": missing.index.astype(str),
            "Missing Count": missing.values,
            "Missing %": missing_pct.values,
        }).sort_values("Missing Count", ascending=False)
        missing_report = missing_report[missing_report["Missing Count"] > 0]

        # Duplicates
        duplicate_count = int(df.duplicated().sum())

        # Outliers (IQR method on numeric columns)
        numeric_cols = df.select_dtypes(include=["number"]).columns
        outlier_info: list[dict[str, Any]] = []
        for col in numeric_cols:
            series = df[col].dropna()
            if len(series) < 4:
                continue
            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            iqr = q3 - q1
            if iqr == 0:
                continue
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            n_outliers = int(((series < lower) | (series > upper)).sum())
            if n_outliers > 0:
                outlier_info.append({
                    "Column": str(col),
                    "Outliers": n_outliers,
                    "Outlier %": round(n_outliers / len(series) * 100, _DISPLAY_DECIMALS),
                    "Lower Bound": round(float(lower), _DISPLAY_DECIMALS),
                    "Upper Bound": round(float(upper), _DISPLAY_DECIMALS),
                })

        # Completeness score
        total_missing = int(missing.sum())
        completeness = round((1 - total_missing / max(1, total_cells)) * 100, _DISPLAY_DECIMALS)

        parts: list[str] = [f"Dataset has {total_rows} rows and {len(df.columns)} columns."]
        parts.append(f"Overall completeness: {completeness}%.")
        if total_missing:
            parts.append(f"Total missing values: {total_missing}.")
        else:
            parts.append("No missing values detected — great!")
        if duplicate_count:
            parts.append(f"Duplicate rows: {duplicate_count}.")
        else:
            parts.append("No duplicate rows found.")
        if outlier_info:
            parts.append(f"Outliers detected in {len(outlier_info)} column(s).")

        result["answer"] = " ".join(parts)
        result["calculations"] = {
            "total_rows": total_rows,
            "total_columns": len(df.columns),
            "total_missing": total_missing,
            "completeness_pct": completeness,
            "duplicate_rows": duplicate_count,
            "columns_with_outliers": len(outlier_info),
        }

        if not missing_report.empty:
            result["tables"].append(_make_table("Missing Values", missing_report))
        if outlier_info:
            result["tables"].append(
                _make_table("Outlier Summary", pd.DataFrame(outlier_info))
            )

        # Recommendations
        if total_missing > 0:
            high_missing = missing_report[missing_report["Missing %"] > 30]
            if not high_missing.empty:
                cols_list = ", ".join(high_missing["Column"].head(5).tolist())
                result["recommendations"].append(
                    f"Columns with >30% missing data: {cols_list}. "
                    "Consider dropping or imputing these."
                )
        if duplicate_count > 0:
            result["recommendations"].append(
                f"Found {duplicate_count} duplicate rows. "
                "Review whether they represent valid data or need deduplication."
            )
        if outlier_info:
            result["recommendations"].append(
                "Some columns have outliers. Verify they are genuine data points "
                "and not data-entry errors."
            )
    except Exception as exc:
        logger.exception("Error in data quality analysis")
        result["answer"] = "An error occurred while assessing data quality."
        result["warnings"].append(f"Quality analysis failed: {type(exc).__name__}")


def _handle_summary(
    df: pd.DataFrame,
    prompt: str,
    understanding: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Handle summary / overview / describe queries."""
    try:
        total_rows = len(df)
        total_cols = len(df.columns)
        numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
        cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()

        # Numeric describe
        if numeric_cols:
            desc = df[numeric_cols].describe().round(_DISPLAY_DECIMALS).T.reset_index()
            desc.columns = ["Column"] + list(desc.columns[1:])
            result["tables"].append(_make_table("Numeric Summary", desc))

        # Categorical overview
        if cat_cols:
            cat_info: list[dict[str, Any]] = []
            for col in cat_cols:
                unique = df[col].nunique(dropna=True)
                top_val = df[col].mode().iloc[0] if not df[col].mode().empty else "N/A"
                top_freq = int(df[col].value_counts().iloc[0]) if not df[col].value_counts().empty else 0
                cat_info.append({
                    "Column": str(col),
                    "Unique Values": unique,
                    "Most Common": str(top_val),
                    "Frequency": top_freq,
                })
            result["tables"].append(
                _make_table("Categorical Summary", pd.DataFrame(cat_info))
            )

        # Summary for the understanding output
        dataset_summary = understanding.get("dataset_summary", "")

        parts = [f"The dataset contains {total_rows} rows and {total_cols} columns."]
        if numeric_cols:
            parts.append(f"{len(numeric_cols)} numeric column(s): {', '.join(numeric_cols[:5])}.")
        if cat_cols:
            parts.append(f"{len(cat_cols)} categorical column(s): {', '.join(cat_cols[:5])}.")
        if dataset_summary:
            parts.append(f"Agent 1 assessment: {dataset_summary}")

        result["answer"] = " ".join(parts)
        result["calculations"] = {
            "total_rows": total_rows,
            "total_columns": total_cols,
            "numeric_columns": numeric_cols,
            "categorical_columns": cat_cols,
        }

        # Chart: value distribution for first numeric column
        if numeric_cols:
            col = numeric_cols[0]
            try:
                hist_data = df[col].dropna()
                bins = min(20, max(5, len(hist_data) // 10))
                counts, edges = np.histogram(hist_data, bins=bins)
                bin_labels = [
                    f"{round(float(edges[i]), 1)}-{round(float(edges[i+1]), 1)}"
                    for i in range(len(counts))
                ]
                hist_df = pd.DataFrame({"Range": bin_labels, "Count": counts.astype(int)})
                result["charts"].append(
                    _make_chart(f"Distribution of {col}", "bar", "Range", "Count", hist_df)
                )
            except Exception:
                pass  # Non-critical: skip histogram on error

        result["recommendations"].append(
            "Use this overview to identify which columns to analyse further. "
            "Ask about trends, predictions, or comparisons for deeper insights."
        )
    except Exception as exc:
        logger.exception("Error in summary analysis")
        result["answer"] = "An error occurred while generating the summary."
        result["warnings"].append(f"Summary analysis failed: {type(exc).__name__}")


def _handle_compare(
    df: pd.DataFrame,
    prompt: str,
    understanding: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Handle compare / versus queries."""
    category_col = _extract_mentioned_column(prompt, df) or _get_category_col(df, understanding)
    numeric_cols = _get_numeric_cols(df, understanding)

    if not category_col:
        result["answer"] = (
            "No categorical column found to compare groups. "
            "Please specify which column to compare by."
        )
        result["warnings"].append("No category column for comparison.")
        return

    if not numeric_cols:
        result["answer"] = "No numeric columns available for comparison."
        result["warnings"].append("No numeric columns for comparison.")
        return

    try:
        comparison = df.groupby(category_col, dropna=True)[numeric_cols].agg(
            ["mean", "sum", "count"]
        )
        # Flatten multi-level columns
        comparison.columns = [
            f"{col}_{agg}" for col, agg in comparison.columns
        ]
        comparison = comparison.round(_DISPLAY_DECIMALS).reset_index()

        # Limit to top categories by row count
        count_col = comparison.columns[-1]  # Last column is the last count
        comparison = comparison.sort_values(count_col, ascending=False).head(_MAX_TABLE_ROWS)

        result["answer"] = (
            f"Comparison across {category_col} categories for "
            f"{', '.join(numeric_cols[:3])}. Showing mean, sum, and count."
        )
        result["calculations"] = {
            "group_column": category_col,
            "value_columns": numeric_cols,
            "categories_compared": len(comparison),
        }
        result["tables"].append(_make_table(f"Comparison by {category_col}", comparison))

        # Bar chart for first numeric column (mean)
        if numeric_cols:
            mean_col = f"{numeric_cols[0]}_mean"
            if mean_col in comparison.columns:
                chart_df = comparison[[category_col, mean_col]].copy()
                result["charts"].append(
                    _make_chart(
                        f"Average {numeric_cols[0]} by {category_col}",
                        "bar",
                        category_col,
                        mean_col,
                        chart_df,
                    )
                )

        result["recommendations"].append(
            f"Look for categories with significantly different averages in "
            f"'{category_col}' to identify performance gaps or opportunities."
        )
    except Exception as exc:
        logger.exception("Error in comparison analysis")
        result["answer"] = "An error occurred while comparing groups."
        result["warnings"].append(f"Comparison analysis failed: {type(exc).__name__}")


def _handle_filter(
    df: pd.DataFrame,
    prompt: str,
    understanding: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Handle filter / find / where queries.

    Attempts basic keyword-based filtering on the dataframe.
    """
    prompt_lower = prompt.lower()

    # Try to identify column and value from the prompt
    matched_col: str | None = None
    matched_value: str | None = None

    for col in sorted(df.columns, key=lambda c: len(str(c)), reverse=True):
        col_lower = str(col).lower()
        if col_lower in prompt_lower:
            matched_col = str(col)
            break

    if not matched_col:
        # Fallback: try the first category column
        matched_col = _get_category_col(df, understanding)

    if not matched_col:
        result["answer"] = (
            "I could not determine which column to filter. "
            "Please specify the column and value in your question."
        )
        result["warnings"].append("Could not identify filter column from prompt.")
        return

    # Try to extract a filter value — look for quoted strings or values after keywords
    value_match = re.search(r'["\']([^"\']+)["\']', prompt)
    if value_match:
        matched_value = value_match.group(1)
    else:
        # Try to find known values from the column in the prompt
        if pd.api.types.is_object_dtype(df[matched_col]) or pd.api.types.is_string_dtype(df[matched_col]):
            unique_vals = df[matched_col].dropna().unique()
            for val in unique_vals:
                if str(val).lower() in prompt_lower:
                    matched_value = str(val)
                    break

    try:
        if matched_value:
            if pd.api.types.is_numeric_dtype(df[matched_col]):
                try:
                    num_val = float(matched_value)
                    filtered = df[df[matched_col] == num_val]
                except ValueError:
                    filtered = df[df[matched_col].astype(str).str.contains(
                        matched_value, case=False, na=False
                    )]
            else:
                filtered = df[df[matched_col].astype(str).str.contains(
                    matched_value, case=False, na=False
                )]
            filter_desc = f"Filtered '{matched_col}' for '{matched_value}'"
        else:
            # No value found — show value_counts for the column
            vc = df[matched_col].value_counts(dropna=True).head(_MAX_TABLE_ROWS).reset_index()
            vc.columns = [matched_col, "Count"]
            result["answer"] = (
                f"I couldn't determine a specific filter value. Here are the "
                f"most common values in '{matched_col}'."
            )
            result["tables"].append(_make_table(f"Values in {matched_col}", vc))
            result["recommendations"].append(
                f"Specify a value from '{matched_col}' to filter by — for example: "
                f"\"show me rows where {matched_col} is '{vc[matched_col].iloc[0]}'\""
            )
            return

        result["answer"] = (
            f"{filter_desc}: found {len(filtered)} matching rows "
            f"out of {len(df)} total."
        )
        result["calculations"] = {
            "filter_column": matched_col,
            "filter_value": matched_value,
            "matching_rows": len(filtered),
            "total_rows": len(df),
        }
        if not filtered.empty:
            result["tables"].append(_make_table(f"Filtered Results ({filter_desc})", filtered))
        else:
            result["warnings"].append(f"No rows matched the filter: {filter_desc}.")
    except Exception as exc:
        logger.exception("Error in filter analysis")
        result["answer"] = "An error occurred while filtering the data."
        result["warnings"].append(f"Filter operation failed: {type(exc).__name__}")


def _handle_recommend(
    df: pd.DataFrame,
    prompt: str,
    understanding: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Handle recommendation / insight queries by analysing patterns."""
    numeric_cols = _get_numeric_cols(df, understanding)
    category_col = _get_category_col(df, understanding)
    date_col = _get_date_col(df, understanding)

    insights: list[str] = []

    try:
        # Insight 1: Top and bottom performers
        if category_col and numeric_cols:
            value_col = numeric_cols[0]
            grouped = df.groupby(category_col, dropna=True)[value_col].sum()
            if len(grouped) >= 2:
                top_item = grouped.idxmax()
                bottom_item = grouped.idxmin()
                top_val = round(float(grouped.max()), _DISPLAY_DECIMALS)
                bottom_val = round(float(grouped.min()), _DISPLAY_DECIMALS)
                insights.append(
                    f"Top performer: '{top_item}' with {value_col} = {top_val}. "
                    f"Lowest: '{bottom_item}' ({bottom_val}). "
                    f"Investigate what makes '{top_item}' successful."
                )

        # Insight 2: Growth trend
        if date_col and numeric_cols:
            value_col = numeric_cols[0]
            temp = df[[date_col, value_col]].copy()
            temp[date_col] = pd.to_datetime(temp[date_col], errors="coerce")
            temp = temp.dropna()
            if len(temp) >= 10:
                monthly = temp.set_index(date_col)[value_col].resample("MS").sum()
                if len(monthly) >= 3:
                    recent_avg = monthly.tail(3).mean()
                    older_avg = monthly.head(3).mean()
                    if older_avg and older_avg != 0:
                        change = round(((recent_avg - older_avg) / abs(older_avg)) * 100, 1)
                        direction = "up" if change > 0 else "down"
                        insights.append(
                            f"Recent 3-month average vs earliest 3-month average: "
                            f"{direction} {abs(change)}%. "
                            f"{'Sustain this momentum.' if change > 0 else 'Investigate the decline.'}"
                        )

        # Insight 3: Data quality quick note
        missing_pct = round(df.isnull().sum().sum() / max(1, df.size) * 100, 1)
        if missing_pct > 5:
            insights.append(
                f"Data quality note: {missing_pct}% of values are missing. "
                "Improving data completeness may reveal stronger patterns."
            )

        # Insight 4: Concentration analysis
        if category_col and numeric_cols:
            value_col = numeric_cols[0]
            grouped = df.groupby(category_col, dropna=True)[value_col].sum().sort_values(ascending=False)
            total = grouped.sum()
            if total > 0 and len(grouped) >= 5:
                top_share = round(float(grouped.head(3).sum() / total * 100), 1)
                if top_share > 60:
                    insights.append(
                        f"High concentration: Top 3 {category_col}s account for "
                        f"{top_share}% of total {value_col}. Diversification may reduce risk."
                    )

        if insights:
            result["answer"] = (
                f"Based on analysis of your data, here are {len(insights)} key insights "
                "and recommendations."
            )
            result["recommendations"] = insights
        else:
            result["answer"] = (
                "The dataset doesn't have enough structure for automated recommendations. "
                "Try asking about specific trends, comparisons, or predictions."
            )
            result["warnings"].append("Limited columns for automated insight generation.")

        result["calculations"] = {
            "insights_generated": len(insights),
            "numeric_columns_used": numeric_cols[:5],
            "category_column_used": category_col,
        }

    except Exception as exc:
        logger.exception("Error in recommendation analysis")
        result["answer"] = "An error occurred while generating recommendations."
        result["warnings"].append(f"Recommendation analysis failed: {type(exc).__name__}")


# ---------------------------------------------------------------------------
# Intent dispatcher
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, Any] = {
    "top":       _handle_top,
    "trend":     _handle_trend,
    "predict":   _handle_predict,
    "segment":   _handle_segment,
    "correlate": _handle_correlate,
    "quality":   _handle_quality,
    "summary":   _handle_summary,
    "compare":   _handle_compare,
    "filter":    _handle_filter,
    "recommend": _handle_recommend,
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze(
    df: pd.DataFrame,
    prompt: str,
    understanding_output: dict[str, Any],
) -> dict[str, Any]:
    """Run analysis on *df* driven by the user *prompt* and Agent 1 output.

    Parameters
    ----------
    df:
        The raw (or lightly cleaned) pandas DataFrame uploaded by the user.
    prompt:
        A natural-language question or instruction from the user.
    understanding_output:
        Structured output from the Data Understanding Agent (Agent 1) containing
        ``dataset_summary``, ``detected_columns``, ``data_quality``,
        ``possible_tasks``, ``missing_requirements``, and ``analysis_plan``.

    Returns
    -------
    dict
        A structured result with keys: ``answer``, ``calculations``,
        ``tables``, ``charts``, ``model_result``, ``recommendations``,
        ``warnings``.
    """
    result = _empty_result()

    # ---- Input validation ----
    if df is None or not isinstance(df, pd.DataFrame):
        result["answer"] = "No valid DataFrame was provided for analysis."
        result["warnings"].append("Input DataFrame is None or invalid.")
        return result

    if df.empty:
        result["answer"] = "The provided dataset is empty — there are no rows to analyse."
        result["warnings"].append("Empty DataFrame.")
        return result

    if not prompt or not isinstance(prompt, str) or not prompt.strip():
        result["answer"] = "No analysis prompt was provided. Please ask a question about your data."
        result["warnings"].append("Empty or missing prompt.")
        return result

    understanding = understanding_output if isinstance(understanding_output, dict) else {}

    # ---- Pre-process: coerce obvious date / numeric columns ----
    try:
        detected = understanding.get("detected_columns", {})
        df_work = df.copy()

        # Coerce date columns
        for col_name in detected.get("date_columns", []):
            if col_name in df_work.columns and not pd.api.types.is_datetime64_any_dtype(df_work[col_name]):
                df_work[col_name] = pd.to_datetime(df_work[col_name], errors="coerce")

        # Coerce numeric columns
        for key in ("revenue_columns", "sales_columns", "quantity_columns"):
            for col_name in detected.get(key, []):
                if col_name in df_work.columns and not pd.api.types.is_numeric_dtype(df_work[col_name]):
                    df_work[col_name] = pd.to_numeric(df_work[col_name], errors="coerce")
    except Exception:
        logger.warning("Column coercion encountered an issue; proceeding with original types")
        df_work = df.copy()

    # ---- Detect intent and dispatch ----
    intent = _detect_intent(prompt)
    logger.info(
        "Analysis intent detected",
        extra={"intent": intent, "prompt_length": len(prompt), "rows": len(df_work)},
    )

    handler = _HANDLERS.get(intent, _handle_summary)
    handler(df_work, prompt, understanding, result)

    # ---- Append general warnings from understanding ----
    missing_reqs = understanding.get("missing_requirements", [])
    if missing_reqs:
        result["warnings"].extend(
            [f"Agent 1 note: {req}" for req in missing_reqs[:5]]
        )

    return result


class DataAnalysisPredictionAgent:
    """Agent 2: Data Analysis & Prediction Agent."""

    def analyze(
        self,
        df: pd.DataFrame,
        prompt: str,
        understanding_output: dict[str, Any],
    ) -> dict[str, Any]:
        """Analyze df based on prompt and Agent 1's understanding."""
        return analyze(df, prompt, understanding_output)

