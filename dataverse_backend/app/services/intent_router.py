"""Dataset-aware intent routing for natural-language analytics questions."""
from __future__ import annotations

import re
from typing import Any


def extract_limit(query: str, default: int = 10) -> int:
    match = re.search(r"\b(\d{1,2})\b", query)
    if not match:
        return default
    return max(1, min(25, int(match.group(1))))


def route_intent(question: str, dataset_type: str, semantic_columns: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return an intent name and params without assuming a sales dataset."""
    query = question.lower().strip()
    semantic = semantic_columns or {}
    limit = extract_limit(query)

    if any(phrase in query for phrase in ["tell me about", "about this data", "summarize", "overview", "describe", "profile"]):
        return {"intent": "dataset_overview", "limit": limit}
    if any(phrase in query for phrase in ["missing", "null", "empty values", "data quality", "quality", "clean"]):
        return {"intent": "missing_values", "limit": limit}

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
        if any(word in query for word in ["monthly", "weekly", "daily", "revenue trend", "sales trend", "over time"]):
            period = "D" if "daily" in query else "W" if "weekly" in query else "M"
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
