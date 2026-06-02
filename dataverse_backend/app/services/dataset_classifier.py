"""Dataset type classification from semantic roles and sample values."""
from __future__ import annotations

from typing import Any

import pandas as pd


DATASET_TYPES = {"sales", "business_leads", "customer", "finance", "generic"}


def _roles_from_profile(df: pd.DataFrame, profile: dict[str, Any] | None = None) -> dict[str, str]:
    if profile and isinstance(profile.get("column_roles"), dict):
        return {str(k): str(v) for k, v in profile["column_roles"].items()}
    from .data_profiler import detect_column_roles

    return detect_column_roles(df)


def classify_dataset(
    df: pd.DataFrame,
    filename: str | None = None,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify a dataframe without assuming a sales domain."""
    roles = _roles_from_profile(df, profile)
    role_set = set(roles.values())
    filename_norm = (filename or "").lower()

    scores = {
        "sales": 0.0,
        "business_leads": 0.0,
        "customer": 0.0,
        "finance": 0.0,
        "generic": 0.05,
    }
    signals: list[str] = []

    def add(dataset_type: str, amount: float, signal: str) -> None:
        scores[dataset_type] += amount
        signals.append(signal)

    if "business_name" in role_set:
        add("business_leads", 0.28, "business_name")
    if "website" in role_set:
        add("business_leads", 0.18, "website")
    if "employee_range" in role_set:
        add("business_leads", 0.16, "employee_range")
    if "revenue_range" in role_set:
        add("business_leads", 0.16, "revenue_range")
    if "industry" in role_set:
        add("business_leads", 0.14, "industry")
    if "business_id" in role_set:
        add("business_leads", 0.08, "business_id")
    if any(token in filename_norm for token in ["lead", "business", "company", "prospect", "no_website"]):
        add("business_leads", 0.12, "filename_business_leads")

    if "product" in role_set:
        add("sales", 0.22, "product")
    if "sales_amount" in role_set:
        add("sales", 0.22, "sales_amount")
    if "quantity" in role_set:
        add("sales", 0.12, "quantity")
    if "order_date" in role_set:
        add("sales", 0.12, "order_date")
    if "category" in role_set and "product" in role_set:
        add("sales", 0.08, "category")

    customer_cols = [col for col, role in roles.items() if role == "customer"]
    if customer_cols:
        add("customer", 0.24, "customer")
    lower_columns = {str(column).lower() for column in df.columns}
    if any(key in lower_columns for key in {"email", "phone", "signup_date", "spend"}):
        add("customer", 0.16, "customer_contact_or_spend")
    if customer_cols and not {"product", "sales_amount"} & role_set:
        add("customer", 0.12, "customer_without_sales")

    finance_names = " ".join(str(column).lower() for column in df.columns)
    if "transaction_date" in role_set:
        add("finance", 0.18, "transaction_date")
    if any(token in finance_names for token in ["expense", "income", "account", "debit", "credit"]):
        add("finance", 0.28, "finance_terms")
    if "sales_amount" in role_set and "transaction_date" in role_set and "product" not in role_set:
        add("finance", 0.08, "amount_with_transaction_date")

    if len(df.columns) <= 1:
        scores["generic"] += 0.5

    best = max(scores, key=scores.get)
    confidence = min(0.99, round(scores[best], 2))
    if best != "generic" and confidence < 0.3:
        best = "generic"
        confidence = max(0.1, confidence)

    return {
        "dataset_type": best if best in DATASET_TYPES else "generic",
        "confidence": confidence,
        "scores": {key: round(value, 2) for key, value in scores.items()},
        "signals": signals,
        "column_roles": roles,
    }
