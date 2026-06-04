"""Domain-aware analytics for AI Khata style transaction reports."""
from __future__ import annotations

from typing import Any

import pandas as pd


AI_KHATA_TYPES = {"ai_khata_transaction_report", "business_transaction_dataset"}
SALES_LABEL = "SALES"
EXPENSE_LABEL = "EXPENSE"
UDHAAR_LABEL = "UDHAAR"


def _normalize_name(name: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in str(name)).strip("_")


def _money(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("Rs", "").replace("rs", "").strip()
    if text == "":
        return None
    numeric = pd.to_numeric(text, errors="coerce")
    if pd.isna(numeric):
        return None
    return float(numeric)


def _round_money(value: float | None) -> float:
    value = 0.0 if value is None else float(value)
    return int(value) if float(value).is_integer() else round(value, 2)


def ai_khata_columns(df: pd.DataFrame) -> dict[str, str | None]:
    normalized = {_normalize_name(column): str(column) for column in df.columns}
    amount_col = None
    for key, column in normalized.items():
        if key in {"amount", "amount_rs", "transaction_amount", "rs_amount"} or ("amount" in key and "range" not in key):
            amount_col = column
            break
    return {
        "date": normalized.get("date") or normalized.get("transaction_date"),
        "time": normalized.get("time"),
        "category": normalized.get("category") or normalized.get("type") or normalized.get("transaction_type"),
        "item_customer": normalized.get("item_customer") or normalized.get("item") or normalized.get("customer"),
        "amount": amount_col,
    }


def is_ai_khata_dataset(df: pd.DataFrame) -> bool:
    columns = ai_khata_columns(df)
    required = columns["date"] and columns["category"] and columns["item_customer"] and columns["amount"]
    if not required:
        return False
    categories = {
        str(value).strip().upper()
        for value in df[columns["category"]].dropna().astype(str).unique()
    }
    return bool(categories & {SALES_LABEL, EXPENSE_LABEL, UDHAAR_LABEL})


def ai_khata_dataset_type(df: pd.DataFrame) -> str | None:
    if not is_ai_khata_dataset(df):
        return None
    metadata = df.attrs.get("report_metadata") or {}
    title = str(metadata.get("report_title", "")).lower()
    if df.attrs.get("report_summary") or "ai khata" in title:
        return "ai_khata_transaction_report"
    return "business_transaction_dataset"


def conditional_item_roles(df: pd.DataFrame) -> dict[str, str]:
    columns = ai_khata_columns(df)
    category_col = columns["category"]
    item_col = columns["item_customer"]
    if not category_col or not item_col:
        return {}
    roles: dict[str, str] = {}
    for category in df[category_col].dropna().astype(str).str.strip().str.upper().unique():
        if category == SALES_LABEL:
            roles[category] = "product_or_item"
        elif category == UDHAAR_LABEL:
            roles[category] = "customer"
        elif category == EXPENSE_LABEL:
            roles[category] = "expense_description"
        else:
            roles[category] = "transaction_description"
    return roles


def business_summary(df: pd.DataFrame) -> dict[str, Any]:
    columns = ai_khata_columns(df)
    category_col = columns["category"]
    amount_col = columns["amount"]
    metadata = df.attrs.get("report_metadata") or {}
    report_summary = df.attrs.get("report_summary") or {}
    if not category_col or not amount_col:
        return {}

    work = df.copy()
    work["_category_norm"] = work[category_col].astype(str).str.strip().str.upper()
    work["_amount"] = pd.to_numeric(work[amount_col], errors="coerce").fillna(0)

    sales_total = float(work.loc[work["_category_norm"] == SALES_LABEL, "_amount"].sum())
    expense_total = float(work.loc[work["_category_norm"] == EXPENSE_LABEL, "_amount"].sum())
    udhaar_total = float(work.loc[work["_category_norm"] == UDHAAR_LABEL, "_amount"].sum())

    parsed_sales = _money(report_summary.get("Total Sales"))
    parsed_expenses = _money(report_summary.get("Total Expenses"))
    parsed_udhaar = _money(report_summary.get("Udhaar Outstanding"))
    parsed_profit = _money(report_summary.get("Net Profit"))

    total_sales = parsed_sales if parsed_sales is not None else sales_total
    total_expenses = parsed_expenses if parsed_expenses is not None else expense_total
    udhaar_outstanding = parsed_udhaar if parsed_udhaar is not None else udhaar_total
    net_profit = parsed_profit if parsed_profit is not None else total_sales - total_expenses
    profit_status = str(report_summary.get("Profit Status") or ("Profit" if net_profit >= 0 else "Loss"))

    return {
        "shop_name": metadata.get("Shop Name"),
        "report_filter": metadata.get("Report Filter"),
        "generated_at": metadata.get("Generated At"),
        "total_sales": _round_money(total_sales),
        "total_expenses": _round_money(total_expenses),
        "udhaar_outstanding": _round_money(udhaar_outstanding),
        "net_profit": _round_money(net_profit),
        "profit_status": profit_status,
        "transaction_count": int(len(work)),
        "sales_transaction_count": int((work["_category_norm"] == SALES_LABEL).sum()),
        "expense_transaction_count": int((work["_category_norm"] == EXPENSE_LABEL).sum()),
        "udhaar_transaction_count": int((work["_category_norm"] == UDHAAR_LABEL).sum()),
    }


def rows_for_category(df: pd.DataFrame, category: str) -> pd.DataFrame:
    columns = ai_khata_columns(df)
    category_col = columns["category"]
    amount_col = columns["amount"]
    if not category_col or not amount_col:
        return df.iloc[0:0].copy()
    work = df.copy()
    work["_category_norm"] = work[category_col].astype(str).str.strip().str.upper()
    work["_amount"] = pd.to_numeric(work[amount_col], errors="coerce").fillna(0)
    return work[work["_category_norm"] == category.upper()].copy()


def monthly_sales_revenue(df: pd.DataFrame, period: str = "M") -> list[dict[str, Any]]:
    columns = ai_khata_columns(df)
    date_col = columns["date"]
    if not date_col:
        return []
    sales = rows_for_category(df, SALES_LABEL)
    if sales.empty:
        return []
    sales["_date"] = pd.to_datetime(sales[date_col], errors="coerce")
    sales = sales.dropna(subset=["_date"])
    if sales.empty:
        return []
    sales["_period"] = sales["_date"].dt.to_period(period)
    grouped = sales.groupby("_period")["_amount"].sum().sort_index()
    return [{"period": str(period_key), "sales_revenue": _round_money(float(value))} for period_key, value in grouped.items()]


def grouped_items(df: pd.DataFrame, category: str, value_name: str) -> list[dict[str, Any]]:
    columns = ai_khata_columns(df)
    item_col = columns["item_customer"]
    if not item_col:
        return []
    rows = rows_for_category(df, category)
    if rows.empty:
        return []
    grouped = rows.groupby(item_col)["_amount"].sum().sort_values(ascending=False)
    return [{str(item_col): str(name), value_name: _round_money(float(value))} for name, value in grouped.items()]


def transaction_type_totals(df: pd.DataFrame) -> list[dict[str, Any]]:
    columns = ai_khata_columns(df)
    category_col = columns["category"]
    if not category_col:
        return []
    work = df.copy()
    work["_amount"] = pd.to_numeric(work[columns["amount"]], errors="coerce").fillna(0)
    grouped = work.groupby(work[category_col].astype(str).str.strip().str.upper())["_amount"].sum().sort_values(ascending=False)
    return [{"transaction_type": str(name), "amount": _round_money(float(value))} for name, value in grouped.items()]
