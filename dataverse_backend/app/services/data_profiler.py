"""Dataset profiling and semantic column detection for dataset-aware analytics."""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

import pandas as pd


SEMANTIC_HINTS: dict[str, list[str]] = {
    "date": ["date", "order_date", "created_at", "timestamp", "time", "day", "month"],
    "product": ["product", "product_name", "item", "sku", "item_name"],
    "revenue": ["sales", "revenue", "amount", "total", "total_sales", "sales_amount"],
    "quantity": ["quantity", "qty", "units", "units_sold", "volume"],
    "price": ["price", "unit_price", "cost", "rate"],
    "category": ["category", "department", "segment", "type", "class"],
    "region": ["region", "country", "city", "state", "location", "territory", "area"],
    "customer": ["customer", "customer_id", "buyer", "client", "user"],
    "order_id": ["order_id", "order", "invoice", "transaction", "receipt"],
    "profit": ["profit", "margin", "net_profit", "gross_profit"],
}

PRIMARY_ROLES = [
    "business_name",
    "website",
    "employee_range",
    "revenue_range",
    "country",
    "region",
    "industry",
    "business_id",
    "product",
    "sales_amount",
    "quantity",
    "order_date",
    "customer",
    "category",
    "transaction_date",
    "generic_text",
    "generic_id",
    "unknown",
]

ROLE_HINTS: dict[str, set[str]] = {
    "business_name": {"business_name", "company_name", "organization", "company", "organisation"},
    "website": {"business_website", "website", "url", "domain", "web_site", "site"},
    "employee_range": {
        "business_number_of_employees_range",
        "employees",
        "employee_range",
        "staff_size",
        "number_of_employees",
        "employee_count_range",
    },
    "revenue_range": {
        "business_yearly_revenue_range",
        "revenue_range",
        "annual_revenue",
        "yearly_revenue",
        "business_revenue_range",
    },
    "country": {"business_country_name", "country", "country_name"},
    "region": {"business_region", "region", "state", "city", "province", "territory", "area", "location"},
    "industry": {"business_naics_description", "industry", "sector", "naics", "naics_description"},
    "business_id": {"business_id", "company_id", "lead_id"},
    "product": {"product", "product_name", "item", "sku", "item_name"},
    "sales_amount": {"sales", "revenue", "amount", "total", "total_sales", "sales_amount", "net_sales"},
    "quantity": {"quantity", "qty", "units", "units_sold", "volume"},
    "order_date": {"order_date", "sale_date", "sales_date", "purchase_date"},
    "customer": {"customer", "customer_name", "customer_id", "client", "buyer"},
    "category": {"category", "department", "segment", "type", "class"},
    "transaction_date": {"transaction_date", "txn_date", "expense_date", "income_date", "posted_date"},
}


def _normalize(name: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_")


def _name_score(column: str, hints: list[str]) -> float:
    normalized = _normalize(column)
    tokens = set(normalized.split("_"))
    best = 0.0
    for hint in hints:
        hint_norm = _normalize(hint)
        hint_tokens = set(hint_norm.split("_"))
        if normalized == hint_norm:
            return 1.0
        if hint_norm in normalized:
            best = max(best, 0.88)
        if tokens & hint_tokens:
            best = max(best, 0.72)
        best = max(best, SequenceMatcher(None, normalized, hint_norm).ratio() * 0.68)
    return best


def _looks_like_date(series: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    if pd.api.types.is_numeric_dtype(series):
        return False
    sample = series.dropna().astype(str).head(20)
    if sample.empty:
        return False
    dateish = sample.str.contains(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", regex=True)
    if int(dateish.sum()) < max(1, int(len(sample) * 0.5)):
        return False
    parsed = pd.to_datetime(series, errors="coerce")
    return bool(parsed.notna().sum() >= max(2, int(len(series.dropna()) * 0.55)))


def _is_numeric_like(series: pd.Series) -> bool:
    if pd.api.types.is_numeric_dtype(series):
        return True
    sample = series.dropna()
    if sample.empty:
        return False
    numeric = pd.to_numeric(sample, errors="coerce")
    return bool(numeric.notna().sum() >= max(2, int(len(sample) * 0.7)))


def _looks_like_range(series: pd.Series) -> bool:
    sample = series.dropna().astype(str).head(30)
    if sample.empty:
        return False
    rangeish = sample.str.contains(r"\d+\s*[-–]\s*\d+|\$|m\b|million|k\b|employees?", case=False, regex=True)
    return bool(rangeish.sum() >= max(1, int(len(sample) * 0.4)))


def _missing_mask(series: pd.Series) -> pd.Series:
    mask = series.isna()
    if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
        mask = mask | (series.astype(str).str.strip() == "")
    return mask


def _skewness_label(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "unknown"
    if abs(value) < 0.5:
        return "approximately symmetric"
    if value > 0:
        return "right-skewed"
    return "left-skewed"


def _cardinality_label(unique_count: int, row_count: int) -> str:
    if row_count <= 0:
        return "unknown"
    ratio = unique_count / row_count
    if unique_count <= 1:
        return "constant"
    if ratio <= 0.05:
        return "low"
    if ratio <= 0.25:
        return "medium"
    if ratio <= 0.75:
        return "high"
    return "very_high"


def detect_column_roles(df: pd.DataFrame) -> dict[str, str]:
    """Return a role for every column without making sales-specific assumptions."""
    roles: dict[str, str] = {}
    for column in df.columns:
        name = str(column)
        normalized = _normalize(name)
        compact = normalized.replace("_", "")
        series = df[column]

        role = "unknown"
        if normalized in ROLE_HINTS["business_name"]:
            role = "business_name"
        elif normalized in ROLE_HINTS["website"] or any(token in normalized for token in ["website", "url", "domain"]):
            role = "website"
        elif normalized in ROLE_HINTS["employee_range"] or ("employee" in normalized and _looks_like_range(series)):
            role = "employee_range"
        elif normalized in ROLE_HINTS["revenue_range"] or ("revenue" in normalized and _looks_like_range(series) and not _is_numeric_like(series)):
            role = "revenue_range"
        elif normalized in ROLE_HINTS["country"] or compact in {"businesscountryname", "countryname"}:
            role = "country"
        elif normalized in ROLE_HINTS["industry"] or "naics" in normalized:
            role = "industry"
        elif normalized in ROLE_HINTS["business_id"]:
            role = "business_id"
        elif normalized in ROLE_HINTS["product"]:
            role = "product"
        elif normalized in ROLE_HINTS["customer"] or "customer" in normalized:
            role = "customer"
        elif normalized in ROLE_HINTS["order_date"] or ("order" in normalized and "date" in normalized):
            role = "order_date"
        elif normalized in ROLE_HINTS["transaction_date"] or ("transaction" in normalized and "date" in normalized):
            role = "transaction_date"
        elif normalized in ROLE_HINTS["quantity"] and _is_numeric_like(series):
            role = "quantity"
        elif (normalized in ROLE_HINTS["sales_amount"] or "amount" in normalized or "sales" in normalized) and _is_numeric_like(series):
            role = "sales_amount"
        elif normalized in ROLE_HINTS["category"]:
            role = "category"
        elif normalized in ROLE_HINTS["region"]:
            role = "region"
        elif _looks_like_date(series):
            role = "transaction_date" if "transaction" in normalized else "order_date"
        elif normalized.endswith("_id") or normalized == "id" or compact.endswith("id"):
            role = "generic_id"
        elif pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
            role = "generic_text"

        roles[name] = role
    return roles


def _semantic_from_roles(column_roles: dict[str, str]) -> dict[str, str | None]:
    semantic: dict[str, str | None] = {role: None for role in PRIMARY_ROLES if role not in {"generic_text", "unknown"}}
    for column, role in column_roles.items():
        if role in semantic and semantic[role] is None:
            semantic[role] = column

    semantic["date"] = semantic.get("order_date") or semantic.get("transaction_date")
    semantic["revenue"] = semantic.get("sales_amount")
    semantic["region"] = semantic.get("region") or semantic.get("country")
    return semantic


def _safe_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (int, float, str, bool)):
        return value
    return str(value)


def dataframe_preview(df: pd.DataFrame, rows: int = 10) -> list[dict[str, Any]]:
    return [
        {str(column): _safe_value(value) for column, value in row.items()}
        for row in df.head(rows).to_dict(orient="records")
    ]


def detect_semantic_columns(df: pd.DataFrame) -> dict[str, str | None]:
    """Detect common business roles using explicit role rules plus legacy aliases."""
    column_roles = detect_column_roles(df)
    detected = _semantic_from_roles(column_roles)

    for role in ("price", "profit", "order_id"):
        best_column: str | None = None
        best_score = 0.0
        for column in df.columns:
            series = df[column]
            score = _name_score(str(column), SEMANTIC_HINTS[role])
            if role in {"price", "profit"} and not _is_numeric_like(series):
                score *= 0.35
            if score > best_score:
                best_score = score
                best_column = str(column)
        detected[role] = best_column if best_score >= 0.58 else None

    return detected


def coerce_analysis_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with likely date/numeric business columns converted safely."""
    result = df.copy()
    semantics = detect_semantic_columns(result)

    for role in ("revenue", "quantity", "price", "profit"):
        column = semantics.get(role)
        if column and column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce")

    date_column = semantics.get("date")
    if date_column and date_column in result.columns:
        result[date_column] = pd.to_datetime(result[date_column], errors="coerce")

    return result


def profile_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    df = coerce_analysis_dataframe(df)
    column_roles = detect_column_roles(df)
    semantic_columns = detect_semantic_columns(df)
    missing = pd.Series({column: int(_missing_mask(df[column]).sum()) for column in df.columns})
    missing_pct = (missing / max(1, len(df)) * 100).round(2)
    numeric_columns = df.select_dtypes(include=["number"]).columns.tolist()
    date_columns = [
        column for column in df.columns
        if pd.api.types.is_datetime64_any_dtype(df[column]) or _looks_like_date(df[column])
    ]
    text_columns = [
        column for column in df.columns
        if column not in numeric_columns and column not in date_columns
    ]

    numeric_summary: dict[str, dict[str, float | None]] = {}
    skewness: dict[str, dict[str, Any]] = {}
    categorical_summary: dict[str, dict[str, Any]] = {}
    cardinality: dict[str, dict[str, Any]] = {}
    suspicious_columns: list[dict[str, Any]] = []
    warnings: list[str] = []

    try:
        from .target_inference import is_identifier_like
    except Exception:  # pragma: no cover - defensive import guard
        is_identifier_like = None

    for column in numeric_columns:
        series = pd.to_numeric(df[column], errors="coerce").dropna()
        if series.empty:
            numeric_summary[column] = {"min": None, "max": None, "mean": None, "median": None}
            continue
        skew_value = float(series.skew()) if len(series) > 2 else None
        numeric_summary[column] = {
            "min": round(float(series.min()), 4),
            "max": round(float(series.max()), 4),
            "mean": round(float(series.mean()), 4),
            "median": round(float(series.median()), 4),
            "std": round(float(series.std(ddof=1)), 4) if len(series) > 1 else 0.0,
        }
        skewness[column] = {
            "value": None if skew_value is None or pd.isna(skew_value) else round(float(skew_value), 4),
            "label": _skewness_label(skew_value),
        }

    for column in text_columns:
        series = df[column].astype(str)
        non_null = series[~_missing_mask(df[column])]
        unique_count = int(non_null.nunique(dropna=True))
        top_values = non_null.value_counts(dropna=True).head(10)
        categorical_summary[column] = {
            "unique_count": unique_count,
            "unique_ratio": round(unique_count / max(1, len(df)), 4),
            "top_values": [{"value": str(idx), "count": int(count)} for idx, count in top_values.items()],
        }
        cardinality[column] = {
            "unique_count": unique_count,
            "label": _cardinality_label(unique_count, len(df)),
            "ratio": round(unique_count / max(1, len(df)), 4),
        }
        missing_count = int(missing[column])
        if unique_count <= 1 or (is_identifier_like and is_identifier_like(df[column], str(column))):
            suspicious_columns.append({"column": str(column), "reason": "identifier_like_or_constant", "unique_count": unique_count})
        elif cardinality[column]["label"] in {"high", "very_high"}:
            suspicious_columns.append({"column": str(column), "reason": "high_cardinality", "unique_count": unique_count})
        if missing_count and missing_count / max(1, len(df)) >= 0.3:
            suspicious_columns.append({"column": str(column), "reason": "high_missingness", "missing_count": missing_count})

    for column in df.columns:
        unique_count = int(df[column].nunique(dropna=True))
        cardinality.setdefault(
            str(column),
            {
                "unique_count": unique_count,
                "label": _cardinality_label(unique_count, len(df)),
                "ratio": round(unique_count / max(1, len(df)), 4),
            },
        )
        if pd.api.types.is_numeric_dtype(df[column]):
            cardinality[str(column)]["numeric"] = True

    column_profiles = []
    for column in df.columns:
        unique_count = int(df[column].nunique(dropna=True))
        unique_ratio = round(unique_count / max(1, len(df)), 4)
        missing_count = int(missing[column])
        missing_ratio = float(missing_pct[column])
        column_profiles.append(
            {
                "name": str(column),
                "dtype": str(df[column].dtype),
                "missing": missing_count,
                "missing_pct": missing_ratio,
                "unique": unique_count,
                "unique_ratio": unique_ratio,
                "is_constant": unique_count <= 1,
                "is_identifier_like": bool(is_identifier_like(df[column], str(column))) if is_identifier_like else False,
                "cardinality": cardinality[str(column)]["label"],
                "role": next(
                    (role for role, role_column in semantic_columns.items() if role_column == column),
                    column_roles.get(str(column)),
                ),
            }
        )

    duplicate_rows = int(df.duplicated().sum())
    total_missing = int(missing.sum())
    total_cells = int(df.size)
    completeness = 1 - (total_missing / total_cells if total_cells else 0)
    duplicate_penalty = duplicate_rows / max(1, len(df))
    high_missing_penalty = sum(1 for count in missing if count / max(1, len(df)) >= 0.3)
    high_cardinality_penalty = sum(1 for meta in cardinality.values() if meta["label"] in {"high", "very_high"})
    quality_score = max(0.0, min(100.0, (completeness - duplicate_penalty - high_missing_penalty * 0.02 - high_cardinality_penalty * 0.01) * 100))

    if len(df) < 20:
        warnings.append("too_few_rows")
    if total_missing:
        warnings.append("missing_values_present")
    if duplicate_rows:
        warnings.append("duplicate_rows_present")
    if not date_columns:
        warnings.append("no_date_column")
    if not numeric_columns:
        warnings.append("no_numeric_column")
    if high_cardinality_penalty:
        warnings.append("high_cardinality_columns")

    profile = {
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "shape": [int(len(df)), int(len(df.columns))],
        "columns": [str(column) for column in df.columns],
        "schema": {
            str(column): {
                "dtype": str(dtype),
                "missing": int(missing[column]),
                "missing_pct": float(missing_pct[column]),
                "unique": int(df[column].nunique(dropna=True)),
            }
            for column, dtype in df.dtypes.items()
        },
        "dtypes": {str(column): str(dtype) for column, dtype in df.dtypes.items()},
        "semantic_columns": semantic_columns,
        "column_roles": column_roles,
        "numeric_columns": [str(column) for column in numeric_columns],
        "date_columns": [str(column) for column in date_columns],
        "text_columns": [str(column) for column in text_columns],
        "numeric_stats": numeric_summary,
        "categorical_stats": categorical_summary,
        "missing_values": {
            str(column): {"count": int(missing[column]), "pct": float(missing_pct[column])}
            for column in df.columns
        },
        "skewness": skewness,
        "cardinality": cardinality,
        "suspicious_columns": suspicious_columns,
        "numeric_summary": numeric_summary,
        "quality": {
            "score": round(float(quality_score), 1),
            "duplicate_rows": duplicate_rows,
            "total_missing": total_missing,
            "total_cells": total_cells,
        },
        "data_quality_score": round(float(quality_score), 1),
        "warnings": warnings,
        "recommendations": [
            "Review high-missing or high-cardinality columns before modeling.",
            "Inspect identifier-like columns to avoid leakage.",
            "Use the inferred semantic columns to drive trend and prediction analysis.",
        ],
        "column_profiles": column_profiles,
        "preview": dataframe_preview(df),
    }

    if df.attrs.get("report_metadata"):
        profile["report_metadata"] = dict(df.attrs["report_metadata"])
    if df.attrs.get("report_summary"):
        profile["report_summary"] = dict(df.attrs["report_summary"])

    try:
        from .dataset_classifier import classify_dataset

        classification = classify_dataset(df, profile=profile)
        profile["dataset_type"] = classification["dataset_type"]
        profile["dataset_classification"] = classification
    except Exception:
        profile["dataset_type"] = "generic"

    return profile
