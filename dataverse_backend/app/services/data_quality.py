"""Deterministic data quality, EDA, trends, correlations, and chart specs."""
from __future__ import annotations

import math
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
        charts.append({
            "type": "histogram",
            "title": f"Distribution of {col}",
            "x_key": "bin",
            "y_key": "count",
            "data": _histogram_rows(series),
        })
    for col in (types["categorical_columns"] + types["text_columns"])[:3]:
        counts = df[col].astype(str).replace("nan", np.nan).dropna().value_counts().head(12).reset_index()
        counts.columns = [col, "count"]
        charts.append({"type": "bar", "title": f"Top {col}", "x": col, "y": "count", "data": counts.to_dict(orient="records")})
    for trend in trends.get("series", [])[:3]:
        charts.append({"type": "line", "title": f"{trend['value_column']} over time", "x_key": "date", "y_key": "value", "data": trend.get("chart_data", [])})
    if correlations.get("matrix"):
        charts.append({"type": "heatmap", "title": "Numeric correlations", "data": correlations["matrix"]})
    if outliers.get("by_column"):
        charts.append({"type": "boxplot", "title": "Outlier bounds", "data": outliers["by_column"]})
    if _valid_feature_importance(xai.get("global_feature_importance")):
        charts.append({
            "type": "feature_importance",
            "title": "Model feature importance",
            "x_key": "feature",
            "y_key": "importance",
            "data": xai["global_feature_importance"],
        })
    if prediction.get("task_type") == "regression" and prediction.get("predictions_sample"):
        charts.append({
            "type": "actual_vs_predicted",
            "title": "Actual vs predicted",
            "x_key": "row_index",
            "y_key": "predicted",
            "data": prediction["predictions_sample"],
        })
    if prediction.get("task_type") == "classification" and _valid_confusion_matrix(prediction.get("confusion_matrix")):
        charts.append({
            "type": "confusion_matrix",
            "title": "Confusion matrix",
            "x_key": "predicted",
            "y_key": "count",
            "series_key": "actual",
            "data": prediction["confusion_matrix"],
        })
    return json_safe(charts)


def normalize_chart_specs(charts: list[dict[str, Any]], *, limit: int = 20) -> tuple[list[dict[str, Any]], list[str]]:
    """Normalize and validate chart specs before any renderer sees them."""
    normalized: list[dict[str, Any]] = []
    warnings: list[str] = []
    priority = {"bar": 0, "line": 1, "donut": 2, "pie": 2, "histogram": 3, "feature_importance": 4, "confusion_matrix": 5}
    ordered = sorted(
        [chart for chart in charts if isinstance(chart, dict)],
        key=lambda chart: (
            priority.get(str(chart.get("type", "")).lower(), 6),
            0 if any(token in str(chart.get("title", "")).lower() for token in ["product", "revenue", "category", "growth", "profit", "food", "cuisine", "ingredient"]) else 1,
        ),
    )
    for chart in ordered:
        if len(normalized) >= limit:
            break
        candidate = _normalize_chart_spec(chart)
        is_valid, reason = validate_chart_spec(candidate)
        if not is_valid:
            warnings.append(f"Skipped invalid chart '{candidate.get('title', 'Chart')}': {reason}.")
            continue
        normalized.append(candidate)
    return normalized, list(dict.fromkeys(warnings))


def validate_chart_spec(chart: dict[str, Any]) -> tuple[bool, str]:
    data = chart.get("data")
    if not isinstance(data, list) or not data:
        return False, "chart data is empty"
    x_key = chart.get("x_key") or chart.get("x")
    y_key = chart.get("y_key") or chart.get("y")
    if not x_key or not y_key:
        return False, "x_key or y_key is missing"
    numeric_values: list[float] = []
    for row in data:
        if not isinstance(row, dict):
            return False, "chart row is malformed"
        if x_key not in row or y_key not in row:
            return False, "x_key or y_key is missing from one or more rows"
        if _invalid_label(row.get(x_key)):
            return False, "label is blank or n/a"
        number = _finite_number(row.get(y_key))
        if number is None:
            return False, "chart values must be numeric"
        numeric_values.append(number)
    if not numeric_values or all(value == 0 for value in numeric_values):
        return False, "all chart values are zero"
    chart_type = str(chart.get("type", "")).lower()
    if chart_type == "feature_importance" and not _valid_feature_importance(data):
        return False, "feature importance was unavailable"
    if chart_type == "confusion_matrix" and not _valid_confusion_matrix(data):
        return False, "confusion matrix data is malformed"
    return True, ""


def _normalize_chart_spec(chart: dict[str, Any]) -> dict[str, Any]:
    chart_type = str(chart.get("type", "bar")).lower()
    data = chart.get("data") or []
    x_key = chart.get("x_key") or chart.get("x")
    y_key = chart.get("y_key") or chart.get("y")
    if chart_type == "feature_importance":
        x_key = x_key or "feature"
        y_key = y_key or "importance"
    elif chart_type == "confusion_matrix":
        x_key = x_key or "predicted"
        y_key = y_key or "count"
    elif chart_type == "histogram":
        x_key = x_key or "bin"
        y_key = y_key or "count"
    return {
        "type": chart_type,
        "title": chart.get("title", "Chart"),
        "data": data,
        "x_key": x_key,
        "y_key": y_key,
        "series_key": chart.get("series_key"),
    }


def _histogram_rows(series: pd.Series) -> list[dict[str, Any]]:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return []
    minimum = float(clean.min())
    maximum = float(clean.max())
    if minimum == maximum:
        label = _format_bin_label(minimum, maximum)
        return [{"bin": label, "count": int(len(clean))}]
    integerish = bool((clean.dropna() % 1 == 0).all())
    if integerish and minimum >= 0 and maximum - minimum <= 1200:
        bin_width = max(1, int(math.ceil((maximum - minimum) / 10)))
        is_calories = "calorie" in str(series.name).lower()
        if is_calories:
            bin_width = 60
        start = int(math.floor(minimum))
        rows = []
        lower = start
        first_bin = True
        while lower <= maximum:
            upper = lower + bin_width if is_calories and first_bin else lower + bin_width - 1
            count = int(((clean >= lower) & (clean <= upper)).sum())
            rows.append({"bin": f"{lower}-{upper}", "count": count})
            lower = upper + 1
            first_bin = False
        return [row for row in rows if row["count"] > 0]
    counts, edges = np.histogram(clean, bins=min(12, max(3, int(np.sqrt(len(clean))))))
    return [
        {"bin": _format_bin_label(float(edges[i]), float(edges[i + 1])), "count": int(count)}
        for i, count in enumerate(counts)
        if int(count) > 0
    ]


def _format_bin_label(start: float, end: float) -> str:
    def _fmt_num(value: float) -> str:
        return str(int(value)) if float(value).is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")

    return f"{_fmt_num(start)}-{_fmt_num(end)}"


def _valid_feature_importance(data: Any) -> bool:
    if not isinstance(data, list) or not data:
        return False
    values = []
    for row in data:
        if not isinstance(row, dict) or _invalid_label(row.get("feature")):
            return False
        number = _finite_number(row.get("importance"))
        if number is None:
            return False
        values.append(number)
    return bool(values) and not all(value == 0 for value in values)


def _valid_confusion_matrix(data: Any) -> bool:
    if not isinstance(data, list) or not data:
        return False
    total = 0.0
    for row in data:
        if not isinstance(row, dict):
            return False
        if _invalid_label(row.get("actual")) or _invalid_label(row.get("predicted")):
            return False
        count = _finite_number(row.get("count"))
        if count is None or count < 0:
            return False
        total += count
    return total > 0


def _invalid_label(value: Any) -> bool:
    if value is None:
        return True
    label = str(value).strip().lower()
    return label in {"", "n/a", "na", "nan", "none", "null"}


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
