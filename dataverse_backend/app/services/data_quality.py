"""Deterministic data quality, EDA, trends, correlations, and chart specs."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        if np.isnan(value) or np.isinf(value):
            return None
        return round(float(value), 6)
    if isinstance(value, np.ndarray):
        return [json_safe(item) for item in value.tolist()]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def _looks_like_date(series: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    if pd.api.types.is_numeric_dtype(series):
        return False
    sample = series.dropna().astype(str).head(50)
    if sample.empty:
        return False
    if not sample.str.contains(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", regex=True).any():
        return False
    parsed = pd.to_datetime(sample, errors="coerce")
    return bool(parsed.notna().sum() >= max(3, int(len(sample) * 0.6)))


def detect_column_types(df: pd.DataFrame) -> dict[str, list[str]]:
    numeric_columns = [str(col) for col in df.select_dtypes(include=["number"]).columns]
    date_columns = [str(col) for col in df.columns if _looks_like_date(df[col])]
    categorical_columns: list[str] = []
    text_columns: list[str] = []
    for col in df.columns:
        name = str(col)
        if name in numeric_columns or name in date_columns:
            continue
        unique = int(df[col].nunique(dropna=True))
        if unique <= max(20, int(len(df) * 0.2)):
            categorical_columns.append(name)
        else:
            text_columns.append(name)
    return {
        "numeric_columns": numeric_columns,
        "categorical_columns": categorical_columns,
        "date_columns": date_columns,
        "text_columns": text_columns,
    }


def compute_data_quality(df: pd.DataFrame) -> dict[str, Any]:
    types = detect_column_types(df)
    missing_by_column = {
        str(col): {"count": int(df[col].isna().sum()), "pct": round(float(df[col].isna().mean() * 100), 4)}
        for col in df.columns
    }
    constant_columns = [str(col) for col in df.columns if df[col].nunique(dropna=True) <= 1]
    high_cardinality_columns = [
        str(col)
        for col in df.columns
        if col not in types["numeric_columns"] and df[col].nunique(dropna=True) / max(1, len(df)) >= 0.7
    ]
    missing_cells = int(df.isna().sum().sum())
    duplicate_rows = int(df.duplicated().sum())
    total_cells = int(df.size)
    missing_pct = round(missing_cells / max(1, total_cells) * 100, 4)
    duplicate_pct = round(duplicate_rows / max(1, len(df)) * 100, 4)
    score = 100.0 - missing_pct - min(25.0, duplicate_pct) - len(constant_columns) * 2 - len(high_cardinality_columns)
    warnings: list[str] = []
    if missing_cells:
        warnings.append("missing_values_present")
    if duplicate_rows:
        warnings.append("duplicate_rows_present")
    if constant_columns:
        warnings.append("constant_columns_present")
    if high_cardinality_columns:
        warnings.append("high_cardinality_columns_present")
    if len(df) < 10:
        warnings.append("too_few_rows_for_modeling")
    return {
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "missing_cells": missing_cells,
        "missing_pct": missing_pct,
        "missing_values_by_column": missing_by_column,
        "duplicate_rows": duplicate_rows,
        "duplicate_pct": duplicate_pct,
        "numeric_columns": types["numeric_columns"],
        "categorical_columns": types["categorical_columns"],
        "date_columns": types["date_columns"],
        "text_columns": types["text_columns"],
        "constant_columns": constant_columns,
        "high_cardinality_columns": high_cardinality_columns,
        "data_quality_score": round(max(0.0, min(100.0, score)), 2),
        "warnings": warnings,
    }


def compute_eda(df: pd.DataFrame, outliers: dict[str, Any] | None = None) -> dict[str, Any]:
    types = detect_column_types(df)
    numeric_describe = (
        df[types["numeric_columns"]].describe().round(6).to_dict()
        if types["numeric_columns"]
        else {}
    )
    categorical_top_values = {}
    for col in types["categorical_columns"] + types["text_columns"]:
        counts = df[col].astype(str).replace("nan", np.nan).dropna().value_counts().head(10)
        categorical_top_values[col] = [{"value": str(idx), "count": int(count)} for idx, count in counts.items()]
    skewness = {}
    for col in types["numeric_columns"]:
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        skewness[col] = None if len(series) < 3 else round(float(series.skew()), 6)
    cardinality = {
        str(col): {
            "unique_count": int(df[col].nunique(dropna=True)),
            "unique_pct": round(float(df[col].nunique(dropna=True) / max(1, len(df)) * 100), 4),
        }
        for col in df.columns
    }
    return {
        "numeric_describe": numeric_describe,
        "categorical_top_values": categorical_top_values,
        "missing_values_by_column": compute_data_quality(df)["missing_values_by_column"],
        "duplicates": {"duplicate_rows": int(df.duplicated().sum())},
        "outlier_summary": outliers or compute_outliers(df),
        "skewness": skewness,
        "cardinality": cardinality,
        "sample_preview": df.head(10).to_dict(orient="records"),
    }


def compute_outliers(df: pd.DataFrame) -> dict[str, Any]:
    by_column = {}
    total = 0
    for col in df.select_dtypes(include=["number"]).columns:
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(series) < 4:
            continue
        q1 = float(series.quantile(0.25))
        q3 = float(series.quantile(0.75))
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        mask = (df[col] < lower) | (df[col] > upper)
        count = int(mask.sum())
        total += count
        by_column[str(col)] = {
            "count": count,
            "lower_bound": round(lower, 6),
            "upper_bound": round(upper, 6),
            "sample_indices": [int(idx) for idx in df.index[mask].tolist()[:10]],
        }
    return {"total_outlier_cells": total, "by_column": by_column}


def compute_correlations(df: pd.DataFrame) -> dict[str, Any]:
    numeric = df.select_dtypes(include=["number"])
    if numeric.shape[1] < 2:
        return {"matrix": {}, "strong_pairs": [], "possible_driver_columns": []}
    matrix = numeric.corr().replace([np.inf, -np.inf], np.nan).fillna(0).round(6)
    strong_pairs = []
    cols = list(matrix.columns)
    for idx, left in enumerate(cols):
        for right in cols[idx + 1 :]:
            corr = float(matrix.loc[left, right])
            if abs(corr) >= 0.65:
                strong_pairs.append({"column_a": str(left), "column_b": str(right), "correlation": round(corr, 6)})
    strong_pairs.sort(key=lambda item: abs(item["correlation"]), reverse=True)
    drivers = list(dict.fromkeys(pair["column_a"] for pair in strong_pairs) | dict.fromkeys(pair["column_b"] for pair in strong_pairs))
    return {"matrix": matrix.to_dict(), "strong_pairs": strong_pairs, "possible_driver_columns": drivers}


def compute_trends(df: pd.DataFrame) -> dict[str, Any]:
    types = detect_column_types(df)
    if not types["date_columns"] or not types["numeric_columns"]:
        return {"date_columns": types["date_columns"], "series": []}
    date_col = types["date_columns"][0]
    work = df.copy()
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
    work = work.dropna(subset=[date_col]).sort_values(date_col)
    if work.empty:
        return {"date_columns": types["date_columns"], "series": []}
    freq = "D" if work[date_col].dt.date.nunique() <= 45 else "W" if work[date_col].dt.date.nunique() <= 180 else "M"
    series_out = []
    for col in types["numeric_columns"][:6]:
        grouped = work.set_index(date_col)[col].resample(freq).mean().dropna()
        values = grouped.to_numpy(dtype=float)
        if len(values) < 2:
            continue
        slope = float(np.polyfit(np.arange(len(values)), values, 1)[0])
        first = float(values[0])
        last = float(values[-1])
        change = last - first
        pct_change = None if first == 0 else change / abs(first) * 100
        volatility = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
        anomaly_points = []
        if volatility:
            z_scores = (values - float(np.mean(values))) / volatility
            anomaly_points = [
                {"date": str(grouped.index[idx].date()), "value": round(float(values[idx]), 6), "z_score": round(float(z), 6)}
                for idx, z in enumerate(z_scores)
                if abs(float(z)) >= 2.5
            ][:10]
        series_out.append(
            {
                "date_column": date_col,
                "value_column": str(col),
                "aggregation_level": freq,
                "first_value": round(first, 6),
                "last_value": round(last, 6),
                "absolute_change": round(change, 6),
                "percent_change": None if pct_change is None else round(float(pct_change), 6),
                "slope": round(slope, 6),
                "direction": "up" if slope > 0 else "down" if slope < 0 else "flat",
                "volatility": round(volatility, 6),
                "anomaly_points": anomaly_points,
                "chart_data": [{"date": str(idx.date()), "value": round(float(value), 6)} for idx, value in grouped.tail(100).items()],
            }
        )
    return {"date_columns": types["date_columns"], "series": series_out}


def build_chart_specs(
    df: pd.DataFrame,
    trends: dict[str, Any],
    correlations: dict[str, Any],
    outliers: dict[str, Any],
    prediction: dict[str, Any],
    xai: dict[str, Any],
) -> list[dict[str, Any]]:
    types = detect_column_types(df)
    charts: list[dict[str, Any]] = []
    for col in types["numeric_columns"][:3]:
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if series.empty:
            continue
        counts, edges = np.histogram(series, bins=min(12, max(3, int(np.sqrt(len(series))))))
        charts.append({
            "type": "histogram",
            "title": f"Distribution of {col}",
            "x": "bin",
            "y": "count",
            "data": [{"bin_start": round(float(edges[i]), 6), "bin_end": round(float(edges[i + 1]), 6), "count": int(count)} for i, count in enumerate(counts)],
        })
    for col in (types["categorical_columns"] + types["text_columns"])[:3]:
        counts = df[col].astype(str).replace("nan", np.nan).dropna().value_counts().head(12).reset_index()
        counts.columns = [col, "count"]
        charts.append({"type": "bar", "title": f"Top {col}", "x": col, "y": "count", "data": counts.to_dict(orient="records")})
    for trend in trends.get("series", [])[:3]:
        charts.append({"type": "line", "title": f"{trend['value_column']} over time", "x": trend["date_column"], "y": trend["value_column"], "data": trend.get("chart_data", [])})
    if correlations.get("matrix"):
        charts.append({"type": "heatmap", "title": "Numeric correlations", "data": correlations["matrix"]})
    if outliers.get("by_column"):
        charts.append({"type": "boxplot", "title": "Outlier bounds", "data": outliers["by_column"]})
    if xai.get("global_feature_importance"):
        charts.append({"type": "feature_importance", "title": "Model feature importance", "data": xai["global_feature_importance"]})
    if prediction.get("task_type") == "regression" and prediction.get("predictions_sample"):
        charts.append({"type": "actual_vs_predicted", "title": "Actual vs predicted", "data": prediction["predictions_sample"]})
    if prediction.get("task_type") == "classification" and prediction.get("confusion_matrix"):
        charts.append({"type": "confusion_matrix", "title": "Confusion matrix", "data": prediction["confusion_matrix"]})
    return json_safe(charts)
