"""Business metric calculations driven by semantic maps."""
from __future__ import annotations

from typing import Any

import pandas as pd

from .semantic_mapper import CREDIT_VALUES, EXPENSE_VALUES, REFUND_VALUES, SALE_VALUES


def calculate_business_metrics(df: pd.DataFrame, semantic_map: dict[str, Any]) -> dict[str, Any]:
    metrics = semantic_map.get("metrics") or {}
    roles = semantic_map.get("column_roles") or {}
    warnings: list[str] = list(semantic_map.get("warnings") or [])
    limitations: list[str] = []

    revenue_series = _metric_series(df, metrics.get("revenue"), roles, warnings, metric_name="revenue")
    quantity_series = _metric_series(df, metrics.get("quantity"), roles, warnings, metric_name="quantity")
    cost_series = _metric_series(df, metrics.get("cost"), roles, warnings, metric_name="cost")
    expense_series = _metric_series(df, metrics.get("expense"), roles, warnings, metric_name="expense")
    profit_series = _metric_series(df, metrics.get("profit"), roles, warnings, metric_name="profit")

    total_revenue = float(revenue_series.sum()) if revenue_series is not None else None
    total_quantity = float(quantity_series.sum()) if quantity_series is not None else None
    total_cost = float(cost_series.sum()) if cost_series is not None else None
    total_expense = float(expense_series.sum()) if expense_series is not None else None

    if profit_series is not None:
        total_profit = float(profit_series.sum())
    elif total_revenue is not None and (total_cost is not None or total_expense is not None):
        total_profit = total_revenue - float(total_cost or total_expense or 0)
    else:
        total_profit = None

    gross_margin = (total_profit / total_revenue * 100) if total_profit is not None and total_revenue not in {None, 0} else None
    transaction_count = int(len(df))
    sales_transaction_count = _filtered_count(df, metrics.get("revenue"))
    average_order_value = total_revenue / sales_transaction_count if total_revenue is not None and sales_transaction_count else None

    date_col = _metric_col(metrics.get("date"))
    product_col = _metric_col(metrics.get("product"))
    category_col = _metric_col(metrics.get("category"))
    customer_col = _metric_col(metrics.get("customer"))

    if not date_col:
        limitations.append("Date column missing; skipped time trends.")
    if not product_col:
        limitations.append("Product column missing; skipped product ranking.")
    if not category_col:
        limitations.append("Category column missing; skipped category ranking.")

    revenue_by_date = _group_by_date(df, date_col, revenue_series, "D") if date_col and revenue_series is not None else []
    revenue_by_month = _group_by_date(df, date_col, revenue_series, "M") if date_col and revenue_series is not None else []
    trend_warning = None
    if revenue_by_month and len(revenue_by_month) == 1:
        trend_warning = "Only one period is available, so a trend cannot be reliably detected."
        limitations.append(trend_warning)

    top_products = _group_by_dimension(df, product_col, revenue_series, "revenue") if product_col and revenue_series is not None else []
    top_categories = _group_by_dimension(df, category_col, revenue_series, "revenue") if category_col and revenue_series is not None else []
    top_customers = _group_by_dimension(df, customer_col, revenue_series, "revenue") if customer_col and revenue_series is not None else []

    revenue_by_category = top_categories
    revenue_by_product = top_products
    expense_summary = _expense_summary(df, metrics, roles)
    profit_summary = {
        "total_revenue": _money(total_revenue),
        "total_cost_or_expense": _money(total_cost if total_cost is not None else total_expense),
        "total_profit": _money(total_profit),
        "gross_margin_pct": None if gross_margin is None else round(float(gross_margin), 2),
    }

    if total_revenue is None:
        limitations.append("No revenue metric could be calculated from the semantic map.")

    return {
        "dataset_type": semantic_map.get("dataset_type", "generic_tabular"),
        "total_revenue": _money(total_revenue),
        "total_quantity": _money(total_quantity),
        "total_cost": _money(total_cost),
        "total_expenses": _money(total_expense),
        "total_profit": _money(total_profit),
        "gross_margin": None if gross_margin is None else round(float(gross_margin), 4),
        "average_order_value": _money(average_order_value),
        "transaction_count": transaction_count,
        "sales_transaction_count": int(sales_transaction_count),
        "top_products": top_products,
        "top_categories": top_categories,
        "top_customers": top_customers,
        "revenue_by_date": revenue_by_date,
        "revenue_by_month": revenue_by_month,
        "revenue_by_category": revenue_by_category,
        "revenue_by_product": revenue_by_product,
        "expense_summary": expense_summary,
        "profit_summary": profit_summary,
        "data_limitations": list(dict.fromkeys(warnings + limitations)),
        "trend_warning": trend_warning,
    }


def answer_business_query(query_plan: dict[str, Any], business_metrics: dict[str, Any]) -> dict[str, Any]:
    intent = query_plan.get("intent", "dataset_overview")
    metric = query_plan.get("metric", "revenue")
    dimensions = query_plan.get("dimensions") or []
    warnings = list(business_metrics.get("data_limitations") or [])

    if intent == "revenue_trend" or ("month" in dimensions and metric == "revenue"):
        rows = business_metrics.get("revenue_by_month") or []
        answer = "No revenue by month could be calculated."
        if len(rows) == 1:
            answer = f"Revenue is {rows[0]['revenue']:,} in {rows[0]['period']}. Only one period is available, so a trend cannot be reliably detected."
        elif len(rows) >= 2:
            answer = f"Revenue is available across {len(rows)} monthly periods."
        return _query_result("revenue_trend", answer, ["period", "revenue"], rows, "Revenue by month", "line", "period", "revenue", warnings)

    if intent == "top_products":
        rows = business_metrics.get("top_products") or []
        answer = f"{rows[0]['product']} leads with revenue {rows[0]['revenue']:,}." if rows else "Product ranking is unavailable."
        return _query_result("top_products", answer, ["product", "revenue"], rows, "Top products", "bar", "product", "revenue", warnings)

    if intent == "category_performance":
        rows = business_metrics.get("top_categories") or []
        answer = f"{rows[0]['category']} leads with revenue {rows[0]['revenue']:,}." if rows else "Category performance is unavailable."
        return _query_result("category_performance", answer, ["category", "revenue"], rows, "Category performance", "bar", "category", "revenue", warnings)

    if intent == "customer_analysis":
        rows = business_metrics.get("top_customers") or []
        answer = f"{rows[0]['customer']} is the top customer with revenue {rows[0]['revenue']:,}." if rows else "Customer analysis is unavailable."
        return _query_result("customer_analysis", answer, ["customer", "revenue"], rows, "Top customers", "bar", "customer", "revenue", warnings)

    if intent == "expense_analysis":
        rows = business_metrics.get("expense_summary") or []
        answer = f"Total expenses are {business_metrics.get('total_expenses')}." if business_metrics.get("total_expenses") is not None else "Expense analysis is unavailable."
        return _query_result("expense_analysis", answer, ["expense_type", "expense"], rows, "Expense summary", "bar", "expense_type", "expense", warnings)

    if intent == "profit_analysis":
        summary = business_metrics.get("profit_summary") or {}
        rows = [{"metric": key, "value": value} for key, value in summary.items()]
        answer = f"Total profit is {summary.get('total_profit')} with gross margin {summary.get('gross_margin_pct')}%."
        return _query_result("profit_analysis", answer, ["metric", "value"], rows, "Profit summary", "bar", "metric", "value", warnings)

    rows = [
        {"metric": "total_revenue", "value": business_metrics.get("total_revenue")},
        {"metric": "total_quantity", "value": business_metrics.get("total_quantity")},
        {"metric": "total_profit", "value": business_metrics.get("total_profit")},
        {"metric": "transaction_count", "value": business_metrics.get("transaction_count")},
    ]
    answer = (
        f"Detected {business_metrics.get('dataset_type')} data. "
        f"Total revenue is {business_metrics.get('total_revenue')}; transactions: {business_metrics.get('transaction_count')}."
    )
    return _query_result("dataset_overview", answer, ["metric", "value"], rows, "Business overview", "bar", "metric", "value", warnings)


def _query_result(intent: str, answer: str, columns: list[str], rows: list[dict[str, Any]], title: str, chart_type: str, x_key: str, y_key: str, warnings: list[str]) -> dict[str, Any]:
    return {
        "intent": intent,
        "answer": answer,
        "tables": [{"title": title, "columns": columns, "rows": rows}],
        "charts": [{"type": chart_type, "title": title, "data": rows, "x_key": x_key, "y_key": y_key}] if rows else [],
        "warnings": warnings,
        "follow_up_ideas": ["Show revenue by month.", "Which products perform best?", "Show profit analysis."],
    }


def _metric_series(df: pd.DataFrame, spec: dict[str, Any] | None, roles: dict[str, str], warnings: list[str], metric_name: str) -> pd.Series | None:
    if not spec:
        if metric_name == "revenue":
            return _derived_revenue_series(df, roles, warnings)
        return None
    source_col = spec.get("source_column")
    if spec.get("aggregation") == "derived" and spec.get("expression") == "quantity * unit_price":
        quantity_col = _first_role(roles, "quantity")
        price_col = _first_role(roles, "unit_price")
        if quantity_col and price_col:
            return pd.to_numeric(df[quantity_col], errors="coerce").fillna(0) * pd.to_numeric(df[price_col], errors="coerce").fillna(0)
    if not source_col or source_col not in df.columns:
        return None
    values = pd.to_numeric(df[source_col], errors="coerce").fillna(0)
    filter_spec = spec.get("filter")
    if not filter_spec:
        return values
    filter_col = filter_spec.get("column")
    if not filter_col or filter_col not in df.columns:
        return values
    normalized = df[filter_col].astype(str).str.strip().str.upper()
    include = {str(value).upper() for value in filter_spec.get("include", [])}
    subtract = {str(value).upper() for value in filter_spec.get("subtract", [])}
    result = pd.Series(0.0, index=df.index)
    if include:
        result.loc[normalized.isin(include)] = values.loc[normalized.isin(include)]
    if subtract:
        result.loc[normalized.isin(subtract)] = -values.loc[normalized.isin(subtract)]
    return result


def _derived_revenue_series(df: pd.DataFrame, roles: dict[str, str], warnings: list[str]) -> pd.Series | None:
    quantity_col = _first_role(roles, "quantity")
    price_col = _first_role(roles, "unit_price")
    if quantity_col and price_col:
        return pd.to_numeric(df[quantity_col], errors="coerce").fillna(0) * pd.to_numeric(df[price_col], errors="coerce").fillna(0)
    warnings.append("Revenue metric unavailable; no sales column or quantity/unit price pair found.")
    return None


def _filtered_count(df: pd.DataFrame, spec: dict[str, Any] | None) -> int:
    if not spec or not spec.get("filter"):
        return int(len(df))
    filter_spec = spec["filter"]
    col = filter_spec.get("column")
    if not col or col not in df.columns:
        return int(len(df))
    include = {str(value).upper() for value in filter_spec.get("include", [])}
    normalized = df[col].astype(str).str.strip().str.upper()
    return int(normalized.isin(include).sum())


def _group_by_date(df: pd.DataFrame, date_col: str, values: pd.Series, period: str) -> list[dict[str, Any]]:
    work = pd.DataFrame({"_date": pd.to_datetime(df[date_col], errors="coerce"), "_value": values}).dropna(subset=["_date"])
    if work.empty:
        return []
    if period == "M":
        grouped = work.groupby(work["_date"].dt.to_period("M"))["_value"].sum().sort_index()
        return [{"period": str(idx), "revenue": _money(value)} for idx, value in grouped.items()]
    grouped = work.groupby(work["_date"].dt.date)["_value"].sum().sort_index()
    return [{"date": str(idx), "revenue": _money(value)} for idx, value in grouped.items()]


def _group_by_dimension(df: pd.DataFrame, column: str, values: pd.Series, value_name: str) -> list[dict[str, Any]]:
    work = pd.DataFrame({"_dimension": df[column].fillna("Unknown").astype(str), "_value": values})
    grouped = work.groupby("_dimension")["_value"].sum().sort_values(ascending=False).head(20)
    key = "product" if value_name == "revenue" and "product" in column.lower() else "category" if "category" in column.lower() else "customer" if "customer" in column.lower() else column
    return [{key: str(name), value_name: _money(value)} for name, value in grouped.items() if float(value) != 0]


def _expense_summary(df: pd.DataFrame, metrics: dict[str, Any], roles: dict[str, str]) -> list[dict[str, Any]]:
    expense_series = _metric_series(df, metrics.get("expense"), roles, [], metric_name="expense")
    if expense_series is None:
        return []
    transaction_col = _first_role(roles, "transaction_type")
    category_col = _first_role(roles, "product_category")
    group_col = transaction_col or category_col
    if not group_col:
        return [{"expense_type": "expenses", "expense": _money(expense_series.sum())}]
    work = pd.DataFrame({"_group": df[group_col].fillna("Unknown").astype(str), "_expense": expense_series})
    grouped = work.groupby("_group")["_expense"].sum().sort_values(ascending=False)
    return [{"expense_type": str(name), "expense": _money(value)} for name, value in grouped.items() if float(value) != 0]


def _metric_col(spec: dict[str, Any] | None) -> str | None:
    return spec.get("source_column") if spec else None


def _first_role(roles: dict[str, str], role: str) -> str | None:
    return next((column for column, value in roles.items() if value == role), None)


def _money(value: Any) -> float | int | None:
    if value is None or pd.isna(value):
        return None
    value = float(value)
    return int(value) if value.is_integer() else round(value, 2)
