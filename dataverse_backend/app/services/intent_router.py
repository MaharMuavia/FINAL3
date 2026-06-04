"""Dataset-aware intent routing for natural-language analytics questions."""
from __future__ import annotations

import re
from typing import Any


def extract_limit(query: str, default: int = 10) -> int:
    match = re.search(r"\b(\d{1,2})\b", query)
    if not match:
        return default
    return max(1, min(25, int(match.group(1))))


def _period_from_query(query: str) -> str | None:
    if any(word in query for word in ["daily", "day"]):
        return "D"
    if any(word in query for word in ["weekly", "week"]):
        return "W"
    if any(word in query for word in ["monthly", "month"]):
        return "M"
    if any(word in query for word in ["yearly", "annual", "year"]):
        return "Y"
    return None


def _is_metric_time_series_query(query: str) -> bool:
    metric_requested = any(word in query for word in ["revenue", "sales", "amount", "profit", "income"])
    time_requested = _period_from_query(query) is not None or any(
        phrase in query
        for phrase in ["over time", "time series", "timeline", "revenue trend", "sales trend"]
    )
    return metric_requested and time_requested


def route_intent(question: str, dataset_type: str, semantic_columns: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return an intent name and params without assuming a sales dataset."""
    query = question.lower().strip()
    semantic = semantic_columns or {}
    limit = extract_limit(query)

    if any(phrase in query for phrase in ["tell me about", "about this data", "summarize", "overview", "describe", "profile"]):
        return {"intent": "dataset_overview", "limit": limit}
    if any(phrase in query for phrase in ["missing", "null", "empty values", "data quality", "quality", "clean"]):
        return {"intent": "missing_values", "limit": limit}

    if dataset_type in {"ai_khata_transaction_report", "business_transaction_dataset"}:
        period = _period_from_query(query) or ("M" if any(phrase in query for phrase in ["over time", "trend", "by month"]) else None)
        if any(word in query for word in ["expense", "expenses", "cost", "spending"]):
            return {"intent": "expense_summary", "period": period, "limit": limit}
        if any(word in query for word in ["udhaar", "credit", "outstanding"]) or "customer debt" in query:
            return {"intent": "udhaar_summary", "period": period, "limit": limit}
        if any(phrase in query for phrase in ["net profit", "profit"]):
            return {"intent": "profit_summary", "period": period, "limit": limit}
        if "category" in query and any(word in query for word in ["best", "top", "perform", "performance", "largest"]):
            return {"intent": "transaction_type_performance", "limit": limit}
        if any(word in query for word in ["sales", "revenue", "income", "selling"]):
            if period:
                return {"intent": "revenue_trend", "period": period, "limit": limit}
            return {"intent": "sales_items", "limit": limit}
        if any(word in query for word in ["item", "items", "product", "products"]):
            return {"intent": "sales_items", "limit": limit}
        return {"intent": "dataset_overview", "limit": limit}

    if dataset_type == "business_leads":
        if any(word in query for word in ["product", "products", "sales trend", "top products", "trending product"]):
            return {"intent": "unsupported_sales_intent", "limit": limit}
        if any(word in query for word in ["recommend", "strategy", "outreach", "target", "business advice", "what should i"]):
            return {"intent": "outreach_recommendations", "limit": limit}
        if any(phrase in query for phrase in ["no website", "without website", "missing website", "have no website"]):
            return {"intent": "no_website_analysis", "limit": limit}
        if any(word in query for word in ["country", "countries"]):
            return {"intent": "country_distribution", "limit": limit}
        if any(word in query for word in ["industry", "industries", "naics", "sector"]):
            return {"intent": "industry_distribution", "limit": limit}
        if any(word in query for word in ["employee", "staff", "headcount"]):
            return {"intent": "employee_range_distribution", "limit": limit}
        if "revenue" in query:
            return {"intent": "revenue_range_distribution", "limit": limit}
        if any(word in query for word in ["lead", "prospect", "highest-value", "high value", "best", "top"]):
            return {"intent": "high_value_leads", "limit": limit}
        return {"intent": "dataset_overview", "limit": limit}

    if dataset_type == "sales":
        if any(word in query for word in ["trending", "trend product", "growing product", "growth product"]):
            return {"intent": "trending_products", "limit": limit}
        if any(word in query for word in ["declining", "falling", "dropping", "decreasing"]):
            return {"intent": "declining_products", "limit": limit}
        if any(word in query for word in ["recommend", "stock more", "stock", "business advice", "what should i"]):
            return {"intent": "sales_recommendations", "limit": limit}
        if any(word in query for word in ["forecast", "predict next", "future sales"]):
            return {"intent": "forecast", "limit": limit}
        if _is_metric_time_series_query(query):
            period = _period_from_query(query) or "M"
            return {"intent": "revenue_trend", "period": period, "limit": limit}
        if any(word in query for word in ["category", "department", "segment"]):
            return {"intent": "category_performance", "limit": limit}
        if any(word in query for word in ["region", "city", "country", "location"]):
            return {"intent": "region_performance", "limit": limit}
        if any(word in query for word in ["customer", "buyer", "client"]):
            return {"intent": "customer_performance", "limit": limit}
        if any(word in query for word in ["top", "highest", "best", "most", "sales", "revenue", "products"]):
            return {"intent": "top_products", "limit": limit, "ascending": any(word in query for word in ["lowest", "worst", "least", "bottom"])}
        return {"intent": "dataset_overview", "limit": limit}

    if any(word in query for word in ["correlation", "relationship", "related"]):
        return {"intent": "correlation", "limit": limit}
    if any(word in query for word in ["outlier", "anomaly", "unusual"]):
        return {"intent": "outliers", "limit": limit}
    if any(word in query for word in ["top", "highest", "best", "most"]) and semantic.get("sales_amount"):
        return {"intent": "generic_top_rows", "limit": limit}
    return {"intent": "dataset_overview", "limit": limit}
