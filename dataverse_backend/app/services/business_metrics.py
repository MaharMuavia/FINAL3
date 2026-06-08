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
    region_col = _metric_col(metrics.get("region"))

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
    top_regions = _group_by_dimension(df, region_col, revenue_series, "revenue") if region_col and revenue_series is not None else []
    top_products_by_quantity = _group_by_dimension(df, product_col, quantity_series, "quantity") if product_col and quantity_series is not None else []
    top_categories_by_transactions = _count_by_dimension(df, category_col, "category") if category_col else []

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
        "top_regions": top_regions,
        "top_products_by_quantity": top_products_by_quantity,
        "top_categories_by_transactions": top_categories_by_transactions,
        "revenue_by_date": revenue_by_date,
        "revenue_by_month": revenue_by_month,
        "revenue_by_category": revenue_by_category,
        "revenue_by_product": revenue_by_product,
        "expense_summary": expense_summary,
        "profit_summary": profit_summary,
        "data_limitations": list(dict.fromkeys(warnings + limitations)),
        "trend_warning": trend_warning,
    }


def compute_product_trends(
    df: pd.DataFrame,
    semantic_map: dict[str, Any],
    business_metrics: dict[str, Any],
) -> dict[str, Any]:
    """Compute grounded product/category trend payloads for sales-style prompts."""
    metrics = semantic_map.get("metrics") or {}
    roles = semantic_map.get("column_roles") or {}
    warnings: list[str] = []

    revenue_series = _metric_series(df, metrics.get("revenue"), roles, warnings, metric_name="revenue")
    quantity_series = _metric_series(df, metrics.get("quantity"), roles, warnings, metric_name="quantity")
    profit_series = _metric_series(df, metrics.get("profit"), roles, warnings, metric_name="profit")

    product_col = _metric_col(metrics.get("product")) or _fallback_column(
        df,
        roles,
        role_names=("product",),
        name_tokens=("product", "item", "sku", "name", "subcategory", "sub_category"),
    )
    category_col = _metric_col(metrics.get("category")) or _fallback_column(
        df,
        roles,
        role_names=("product_category",),
        name_tokens=("category", "subcategory", "department", "segment"),
    )
    date_col = _metric_col(metrics.get("date")) or _fallback_column(
        df,
        roles,
        role_names=("order_date", "invoice_date", "transaction_date"),
        name_tokens=("date", "month", "order_datetime", "datetime"),
    )
    region_col = _metric_col(metrics.get("region")) or _fallback_column(
        df,
        roles,
        role_names=("region", "city", "store", "country"),
        name_tokens=("region", "city", "store", "branch", "country"),
    )

    charts: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    insights: list[str] = []
    recommendations: list[str] = []
    next_questions: list[str] = []

    top_revenue = _rank_dimension(df, product_col, revenue_series, "product", "revenue", 10)
    top_quantity = _rank_dimension(df, product_col, quantity_series, "product", "quantity", 10)
    top_profit = _rank_dimension(df, product_col, profit_series, "product", "profit", 10)
    category_performance = _rank_dimension(df, category_col, revenue_series, "category", "revenue", 10)
    region_performance = _rank_dimension(df, region_col, revenue_series, "region", "revenue", 10)

    if top_revenue:
        charts.append({"type": "bar", "title": "Top 10 Products by Revenue", "x_key": "product", "y_key": "revenue", "data": top_revenue})
        tables.append({"title": "Top Products by Revenue", "columns": ["product", "revenue"], "rows": top_revenue})
        leader = top_revenue[0]
        insights.append(f"{leader['product']} is the top revenue product with {leader['revenue']}.")
        recommendations.append(f"Protect availability and merchandising for {leader['product']}, the current revenue leader.")

    if top_quantity:
        charts.append({"type": "bar", "title": "Top 10 Products by Quantity", "x_key": "product", "y_key": "quantity", "data": top_quantity})
        tables.append({"title": "Top Products by Quantity", "columns": ["product", "quantity"], "rows": top_quantity})

    trend_rows, growth_rows = _product_monthly_trends(df, date_col, product_col, revenue_series, top_revenue)
    if trend_rows:
        charts.append({
            "type": "line",
            "title": "Monthly Revenue Trend for Top Products",
            "x_key": "period",
            "y_key": "revenue",
            "series_key": "product",
            "data": trend_rows,
        })
    positive_growth = [row for row in growth_rows if float(row.get("absolute_growth") or 0) > 0 and row.get("meaningful_periods")]
    negative_growth = [row for row in growth_rows if float(row.get("absolute_growth") or 0) < 0 and row.get("meaningful_periods")]
    if positive_growth:
        charts.append({"type": "bar", "title": "Fastest Growing Products", "x_key": "product", "y_key": "absolute_growth", "data": positive_growth[:10]})
        tables.append({"title": "Product Growth", "columns": ["product", "first_period_revenue", "last_period_revenue", "absolute_growth", "pct_growth"], "rows": positive_growth[:10]})
    elif negative_growth:
        charts.append({"type": "bar", "title": "Declining Products", "x_key": "product", "y_key": "absolute_growth", "data": negative_growth[:10]})
        tables.append({"title": "Declining Products", "columns": ["product", "first_period_revenue", "last_period_revenue", "absolute_growth", "pct_growth"], "rows": negative_growth[:10]})
    elif top_revenue and date_col:
        warnings.append("Product growth needs at least two meaningful periods with non-zero change; growth chart was skipped.")

    share_source = category_performance or top_revenue
    if share_source:
        x_key = "category" if category_performance else "product"
        charts.append({"type": "donut", "title": "Revenue Share", "x_key": x_key, "y_key": "revenue", "data": share_source[:8]})
    if category_performance:
        charts.append({"type": "bar", "title": "Category Performance", "x_key": "category", "y_key": "revenue", "data": category_performance})
        tables.append({"title": "Category Performance", "columns": ["category", "revenue"], "rows": category_performance})
    if region_performance:
        charts.append({"type": "bar", "title": "Region/Store Performance", "x_key": "region", "y_key": "revenue", "data": region_performance})
        tables.append({"title": "Region/Store Performance", "columns": ["region", "revenue"], "rows": region_performance})
    if top_profit:
        charts.append({"type": "bar", "title": "Profit by Product", "x_key": "product", "y_key": "profit", "data": top_profit})
        tables.append({"title": "Profit by Product", "columns": ["product", "profit"], "rows": top_profit})

    if not top_revenue and business_metrics.get("total_revenue") is None:
        warnings.append("Product trend analysis needs a revenue column or quantity/unit price pair.")
    if product_col and not date_col:
        warnings.append("Date column missing; product trend over time was skipped.")

    if top_revenue:
        next_questions.extend([
            "Which top products are losing momentum?",
            "Which categories should receive more inventory or campaign budget?",
            "Compare product profitability against revenue share.",
        ])

    return {
        "product_column": product_col,
        "date_column": date_col,
        "revenue_available": revenue_series is not None,
        "top_products_by_revenue": top_revenue,
        "top_products_by_quantity": top_quantity,
        "product_revenue_trend": trend_rows,
        "fastest_growing_products": growth_rows,
        "category_performance": category_performance,
        "region_performance": region_performance,
        "profit_by_product": top_profit,
        "charts": charts,
        "tables": tables,
        "insights": insights,
        "recommendations": recommendations,
        "next_questions": next_questions,
        "warnings": list(dict.fromkeys(warnings)),
    }


def answer_business_query(query_plan: dict[str, Any], business_metrics: dict[str, Any]) -> dict[str, Any]:
    intent = query_plan.get("intent", "dataset_overview")
    metric = query_plan.get("metric", "revenue")
    dimensions = query_plan.get("dimensions") or []
    warnings = list(business_metrics.get("data_limitations") or [])

    if intent == "total_sales":
        top_category_revenue = (business_metrics.get("top_categories") or [{}])[0]
        top_region_revenue = (business_metrics.get("top_regions") or [{}])[0]
        answer = (
            f"Total sales are {business_metrics.get('total_revenue')} across {business_metrics.get('transaction_count')} transactions. "
            f"Total quantity sold is {business_metrics.get('total_quantity')} and total profit is {business_metrics.get('total_profit')}, "
            f"giving a gross margin of {business_metrics.get('gross_margin')}%."
        )
        kpis = build_kpi_cards(business_metrics)
        summary_rows = [
            {"metric": "Top category by revenue", "value": top_category_revenue.get("category"), "amount": top_category_revenue.get("revenue")},
            {"metric": "Top region by revenue", "value": top_region_revenue.get("region"), "amount": top_region_revenue.get("revenue")},
        ]
        summary_rows = [row for row in summary_rows if row.get("value")]
        return {
            "intent": intent,
            "answer": answer,
            "kpis": kpis,
            "tables": [{"title": "Total Sales Overview", "columns": ["metric", "value", "amount"], "rows": summary_rows}] if summary_rows else [],
            "charts": [],
            "warnings": warnings,
            "recommendations": [
                "Ask for revenue by month, category performance, or top products to drill into the drivers.",
            ],
            "follow_up_ideas": ["Show revenue by month.", "Show category performance.", "Show top products."],
        }

    if intent in {"revenue_by_month", "revenue_trend"} or ("month" in dimensions and metric == "revenue"):
        rows = business_metrics.get("revenue_by_month") or []
        answer = "No revenue by month could be calculated."
        if len(rows) == 1:
            answer = f"Revenue is {rows[0]['revenue']:,} in {rows[0]['period']}. Only one period is available, so a trend cannot be reliably detected."
        elif len(rows) >= 2:
            answer = f"Revenue is available across {len(rows)} monthly periods."
        return _query_result("revenue_by_month", answer, ["period", "revenue"], rows, "Revenue by month", "line", "period", "revenue", warnings)

    if intent in {"top_product", "top_products"}:
        rows = business_metrics.get("top_products") or []
        quantity_rows = business_metrics.get("top_products_by_quantity") or []
        if rows and quantity_rows:
            answer = (
                f"Top product by revenue is {rows[0]['product']} with {rows[0]['revenue']}. "
                f"Top product by quantity is {quantity_rows[0]['product']} with {quantity_rows[0]['quantity']} units."
            )
        else:
            answer = "Product ranking is unavailable."
        tables = []
        if rows:
            tables.append({"title": "Top products by revenue", "columns": ["product", "revenue"], "rows": rows})
        if quantity_rows:
            tables.append({"title": "Top products by quantity", "columns": ["product", "quantity"], "rows": quantity_rows})
        charts = []
        if rows:
            charts.append({"type": "bar", "title": "Top products by revenue", "data": rows, "x_key": "product", "y_key": "revenue"})
        if quantity_rows:
            charts.append({"type": "bar", "title": "Top products by quantity", "data": quantity_rows, "x_key": "product", "y_key": "quantity"})
        return {
            "intent": "top_product",
            "answer": answer,
            "kpis": build_kpi_cards(business_metrics),
            "tables": tables,
            "charts": charts,
            "warnings": warnings,
            "recommendations": ["Compare top products by revenue, quantity, and profit before making assortment changes."],
            "follow_up_ideas": ["Show product profitability.", "Show product trend by month."],
        }

    if intent == "category_performance":
        rows = business_metrics.get("top_categories") or []
        transaction_rows = business_metrics.get("top_categories_by_transactions") or []
        answer = "Category performance is unavailable."
        if rows:
            answer = f"{rows[0]['category']} is top category by revenue with {rows[0]['revenue']}."
            if transaction_rows:
                answer += f" {transaction_rows[0]['category']} is top category by transaction count with {transaction_rows[0]['transaction_count']} rows."
        return {
            "intent": intent,
            "answer": answer,
            "kpis": build_kpi_cards(business_metrics),
            "tables": [
                {"title": "Category revenue", "columns": ["category", "revenue"], "rows": rows},
                {"title": "Category transaction count", "columns": ["category", "transaction_count"], "rows": transaction_rows},
            ],
            "charts": [{"type": "bar", "title": "Category revenue", "data": rows, "x_key": "category", "y_key": "revenue"}] if rows else [],
            "warnings": warnings,
            "recommendations": ["Use revenue and transaction count together so high-frequency low-ticket categories do not get confused with top revenue categories."],
            "follow_up_ideas": ["Show category profit.", "Show category share by revenue."],
        }

    if intent == "region_performance":
        rows = business_metrics.get("top_regions") or []
        answer = f"{rows[0]['region']} is top region by revenue with {rows[0]['revenue']}." if rows else "Region performance is unavailable."
        return _query_result(intent, answer, ["region", "revenue"], rows, "Region revenue", "bar", "region", "revenue", warnings)

    if intent == "customer_analysis":
        rows = business_metrics.get("top_customers") or []
        answer = f"{rows[0]['customer']} is the top customer with revenue {rows[0]['revenue']:,}." if rows else "Customer analysis is unavailable."
        return _query_result("customer_analysis", answer, ["customer", "revenue"], rows, "Top customers", "bar", "customer", "revenue", warnings)

    if intent == "expense_analysis":
        rows = business_metrics.get("expense_summary") or []
        answer = f"Total expenses are {business_metrics.get('total_expenses')}." if business_metrics.get("total_expenses") is not None else "Expense analysis is unavailable."
        return _query_result("expense_analysis", answer, ["expense_type", "expense"], rows, "Expense summary", "bar", "expense_type", "expense", warnings)

    if intent in {"profit_summary", "profit_analysis"}:
        summary = business_metrics.get("profit_summary") or {}
        rows = [{"metric": key, "value": value} for key, value in summary.items()]
        answer = f"Total profit is {summary.get('total_profit')} with gross margin {summary.get('gross_margin_pct')}%."
        return {
            "intent": "profit_summary",
            "answer": answer,
            "kpis": build_kpi_cards(business_metrics),
            "tables": [{"title": "Profit summary", "columns": ["metric", "value"], "rows": rows}],
            "charts": [],
            "warnings": warnings,
            "recommendations": ["Compare gross margin with category and region profitability before changing pricing or discount strategy."],
            "follow_up_ideas": ["Show profit by category.", "Show profit by region."],
        }

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
    return {
        "intent": "dataset_overview",
        "answer": answer,
        "kpis": build_kpi_cards(business_metrics),
        "tables": [{"title": "Business overview", "columns": ["metric", "value"], "rows": rows}],
        "charts": [],
        "warnings": warnings,
        "recommendations": ["Ask for total sales, revenue by month, top products, category performance, or a full report to go deeper."],
        "follow_up_ideas": ["Show revenue by month.", "Which products perform best?", "Show profit summary."],
    }


def _query_result(intent: str, answer: str, columns: list[str], rows: list[dict[str, Any]], title: str, chart_type: str, x_key: str, y_key: str, warnings: list[str]) -> dict[str, Any]:
    return {
        "intent": intent,
        "answer": answer,
        "kpis": [],
        "tables": [{"title": title, "columns": columns, "rows": rows}],
        "charts": [{"type": chart_type, "title": title, "data": rows, "x_key": x_key, "y_key": y_key}] if rows else [],
        "warnings": warnings,
        "follow_up_ideas": ["Show revenue by month.", "Which products perform best?", "Show profit analysis."],
    }


def build_kpi_cards(business_metrics: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"label": "Total Sales", "value": business_metrics.get("total_revenue")},
        {"label": "Total Quantity", "value": business_metrics.get("total_quantity")},
        {"label": "Total Profit", "value": business_metrics.get("total_profit")},
        {"label": "Gross Margin", "value": None if business_metrics.get("gross_margin") is None else f"{business_metrics.get('gross_margin')}%"},
        {"label": "Transactions", "value": business_metrics.get("transaction_count")},
    ]


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
    normalized = column.lower().replace(" ", "_")
    if any(token in normalized for token in ("product", "item", "sku")):
        key = "product"
    elif "category" in normalized:
        key = "category"
    elif any(token in normalized for token in ("customer", "client", "buyer")):
        key = "customer"
    elif any(token in normalized for token in ("region", "city", "country")):
        key = "region"
    elif any(token in normalized for token in ("store", "branch", "shop")):
        key = "store"
    else:
        key = column
    return [{key: str(name), value_name: _money(value)} for name, value in grouped.items() if float(value) != 0]


def _count_by_dimension(df: pd.DataFrame, column: str, label_name: str) -> list[dict[str, Any]]:
    if not column or column not in df.columns:
        return []
    grouped = df[column].fillna("Unknown").astype(str).value_counts().head(20)
    return [{label_name: str(name), "transaction_count": int(count)} for name, count in grouped.items() if int(count) > 0]


def _rank_dimension(
    df: pd.DataFrame,
    column: str | None,
    values: pd.Series | None,
    label_name: str,
    value_name: str,
    limit: int,
) -> list[dict[str, Any]]:
    if not column or column not in df.columns or values is None:
        return []
    work = pd.DataFrame({"_label": df[column].fillna("Unknown").astype(str), "_value": values})
    grouped = work.groupby("_label")["_value"].sum().sort_values(ascending=False).head(limit)
    return [{label_name: str(name), value_name: _money(value)} for name, value in grouped.items() if float(value) != 0]


def _product_monthly_trends(
    df: pd.DataFrame,
    date_col: str | None,
    product_col: str | None,
    revenue_series: pd.Series | None,
    top_revenue: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not date_col or not product_col or date_col not in df.columns or product_col not in df.columns or revenue_series is None:
        return [], []
    top_products = [str(row["product"]) for row in top_revenue[:5]]
    if not top_products:
        return [], []
    work = pd.DataFrame(
        {
            "_date": pd.to_datetime(df[date_col], errors="coerce"),
            "product": df[product_col].fillna("Unknown").astype(str),
            "revenue": revenue_series,
        }
    ).dropna(subset=["_date"])
    work = work[work["product"].isin(top_products)]
    if work.empty:
        return [], []
    work["period"] = work["_date"].dt.to_period("M").astype(str)
    grouped = work.groupby(["period", "product"], as_index=False)["revenue"].sum().sort_values(["period", "product"])
    trend_rows = [
        {"period": str(row["period"]), "product": str(row["product"]), "revenue": _money(row["revenue"])}
        for row in grouped.to_dict(orient="records")
        if float(row["revenue"]) != 0
    ]

    growth_rows: list[dict[str, Any]] = []
    periods = sorted(grouped["period"].unique().tolist())
    if len(periods) >= 2:
        pivot = grouped.pivot_table(index="product", columns="period", values="revenue", aggfunc="sum", fill_value=0)
        first_period = periods[0]
        last_period = periods[-1]
        for product, row in pivot.iterrows():
            first = float(row.get(first_period, 0))
            last = float(row.get(last_period, 0))
            absolute = last - first
            pct = None if first == 0 else absolute / abs(first) * 100
            growth_rows.append(
                {
                    "product": str(product),
                    "first_period_revenue": _money(first),
                    "last_period_revenue": _money(last),
                    "absolute_growth": _money(absolute),
                    "pct_growth": None if pct is None else round(float(pct), 2),
                    "meaningful_periods": bool(first != 0 or last != 0),
                }
            )
        growth_rows.sort(key=lambda item: float(item["absolute_growth"] or 0), reverse=True)
    return trend_rows, growth_rows


def _fallback_column(
    df: pd.DataFrame,
    roles: dict[str, str],
    *,
    role_names: tuple[str, ...],
    name_tokens: tuple[str, ...],
) -> str | None:
    for role_name in role_names:
        found = _first_role(roles, role_name)
        if found:
            return found
    for column in df.columns:
        normalized = str(column).lower().replace(" ", "_")
        if any(token in normalized for token in name_tokens):
            return str(column)
    return None


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
