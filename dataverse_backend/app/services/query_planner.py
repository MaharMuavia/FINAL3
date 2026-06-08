"""Semantic query planning for business analytics questions."""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from .llm_provider import LLMProvider


Intent = Literal[
    "total_sales",
    "top_product",
    "revenue_by_month",
    "dataset_overview",
    "category_performance",
    "region_performance",
    "profit_summary",
    "profit_analysis",
    "expense_analysis",
    "prediction",
    "full_report",
    "customer_analysis",
    "revenue_trend",
    "top_products",
    "correlation",
    "anomaly",
    "generic_question",
]


class QueryPlan(BaseModel):
    intent: Intent = "dataset_overview"
    metric: Literal["revenue", "profit", "expense", "quantity", "count", "average_order_value"] = "revenue"
    dimensions: list[str] = Field(default_factory=list)
    filters: list[dict[str, Any]] = Field(default_factory=list)
    needs_prediction: bool = False
    needs_xai: bool = False
    report_mode: Literal["focused_answer_report", "full_analysis_report"] = "focused_answer_report"

    @field_validator("dimensions")
    @classmethod
    def clean_dimensions(cls, value: list[str]) -> list[str]:
        allowed = {"month", "date", "product", "category", "customer", "region", "store", "city", "country"}
        return [item for item in value if item in allowed]


class QueryPlanner:
    def __init__(self, llm_provider: LLMProvider | None = None):
        self.llm_provider = llm_provider or LLMProvider()

    def plan(self, query: str | None, semantic_map: dict[str, Any], dataset_profile: dict[str, Any] | None = None) -> dict[str, Any]:
        heuristic = self._heuristic_plan(query or "", semantic_map)
        if not query or not self.llm_provider.is_configured() or _should_use_heuristic_only(heuristic):
            return heuristic.model_dump()
        try:
            asyncio.get_running_loop()
            return heuristic.model_dump()
        except RuntimeError:
            return asyncio.run(self.plan_async(query, semantic_map, dataset_profile))

    async def plan_async(self, query: str | None, semantic_map: dict[str, Any], dataset_profile: dict[str, Any] | None = None) -> dict[str, Any]:
        heuristic = self._heuristic_plan(query or "", semantic_map)
        if not query or not self.llm_provider.is_configured() or _should_use_heuristic_only(heuristic):
            return heuristic.model_dump()
        llm_plan = await self._llm_plan(query, semantic_map, dataset_profile or {})
        if llm_plan is None:
            return heuristic.model_dump()
        return llm_plan.model_dump()

    def _heuristic_plan(self, query: str, semantic_map: dict[str, Any]) -> QueryPlan:
        q = query.lower().strip()
        dataset_type = str(semantic_map.get("dataset_type") or "")
        dimensions: list[str] = []
        if any(word in q for word in ["month", "monthly"]):
            dimensions.append("month")
        if any(word in q for word in ["date", "daily", "day", "trend", "over time"]):
            dimensions.append("date" if "month" not in dimensions else "month")
        if any(word in q for word in ["product", "item", "sku"]):
            dimensions.append("product")
        if any(word in q for word in ["category", "department", "segment"]):
            dimensions.append("category")
        if any(word in q for word in ["customer", "client", "buyer"]):
            dimensions.append("customer")
        if any(word in q for word in ["region", "city", "country", "store", "branch"]):
            dimensions.append("region")

        explicit_report = _looks_like_report_request(q)
        if explicit_report:
            return QueryPlan(intent="full_report", metric="revenue", dimensions=dimensions, report_mode="full_analysis_report")
        if _looks_like_broad_analysis_request(q):
            return QueryPlan(intent="dataset_overview", metric="revenue", dimensions=dimensions, report_mode="full_analysis_report")

        if any(word in q for word in ["predict", "forecast", "future"]):
            metric = "profit" if "profit" in q or "margin" in q else "quantity" if "quantity" in q else "revenue"
            return QueryPlan(intent="prediction", metric=metric, dimensions=dimensions, needs_prediction=True, needs_xai=True)
        if _looks_like_total_sales_question(q):
            return QueryPlan(intent="total_sales", metric="revenue", dimensions=dimensions, report_mode="focused_answer_report")
        if any(word in q for word in ["month", "monthly", "trend", "over time"]) and any(word in q for word in ["revenue", "sales"]):
            monthly_intent = "revenue_by_month" if dataset_type in {"retail_sales", "mart_sales"} else "revenue_trend"
            return QueryPlan(intent=monthly_intent, metric="revenue", dimensions=["month" if "month" in dimensions else "date"], report_mode="focused_answer_report")
        if any(word in q for word in ["why", "driver", "drivers", "explain"]) and any(word in q for word in ["sales", "revenue", "profit"]):
            return QueryPlan(intent="generic_question", metric="revenue", dimensions=dimensions, needs_xai=True)
        if any(word in q for word in ["correlation", "relationship", "related"]):
            return QueryPlan(intent="correlation", metric="revenue", dimensions=dimensions)
        if any(word in q for word in ["anomaly", "outlier", "unusual"]):
            return QueryPlan(intent="anomaly", metric="revenue", dimensions=dimensions)
        if any(word in q for word in ["expense", "cost", "spending"]):
            return QueryPlan(intent="expense_analysis", metric="expense", dimensions=dimensions or ["category"])
        if any(word in q for word in ["profit", "margin"]):
            return QueryPlan(intent="profit_summary", metric="profit", dimensions=dimensions, report_mode="focused_answer_report")
        if any(word in q for word in ["customer", "client", "buyer"]):
            return QueryPlan(intent="customer_analysis", metric="revenue", dimensions=dimensions or ["customer"])
        if any(word in q for word in ["category", "department", "segment"]) and any(word in q for word in ["best", "top", "perform", "performance", "highest", "most"]):
            return QueryPlan(intent="category_performance", metric="revenue", dimensions=dimensions or ["category"])
        if any(word in q for word in ["region", "city", "country", "store", "branch"]) and any(word in q for word in ["best", "top", "perform", "performance", "highest", "most"]):
            return QueryPlan(intent="region_performance", metric="revenue", dimensions=dimensions or ["region"])
        if any(word in q for word in ["product", "item", "sku", "selling", "sells", "sold"]) and any(word in q for word in ["best", "top", "highest", "most", "sell", "sells", "sold"]):
            metric = "revenue" if semantic_map.get("metrics", {}).get("revenue") else "quantity"
            if "quantity" in q or ("sold" in q and dataset_type in {"mart_sales", "retail_sales"}):
                metric = "quantity"
            return QueryPlan(intent="top_product", metric=metric, dimensions=dimensions or ["product"], report_mode="focused_answer_report")
        if any(word in q for word in ["revenue", "sales", "income", "selling"]) and ({"month", "date"} & set(dimensions) or "trend" in q or "over time" in q):
            return QueryPlan(intent="revenue_trend", metric="revenue", dimensions=["month" if "month" in dimensions else "date"])
        if any(word in q for word in ["overview", "summarize", "summary", "tell me about"]):
            return QueryPlan(intent="dataset_overview", metric="revenue", dimensions=[], report_mode="focused_answer_report")
        return QueryPlan(intent="dataset_overview", metric="revenue", dimensions=dimensions, report_mode="focused_answer_report")

    async def _llm_plan(self, query: str, semantic_map: dict[str, Any], dataset_profile: dict[str, Any]) -> QueryPlan | None:
        prompt = (
            "Classify the user analytics query. Return strict JSON only with keys: "
            "intent, metric, dimensions, filters, needs_prediction, needs_xai. "
            "Do not calculate numbers.\n"
            f"User query: {query}\n"
            f"Semantic map: {json.dumps(semantic_map, default=str)[:8000]}\n"
            f"Dataset profile: {json.dumps({'row_count': dataset_profile.get('row_count'), 'columns': dataset_profile.get('columns')}, default=str)}"
        )
        text = await self.llm_provider.generate(prompt, system_prompt="Return strict JSON only. Do not calculate numbers.", json_mode=True)
        if not text:
            return None
        try:
            return QueryPlan.model_validate(_extract_json(text))
        except (ValidationError, ValueError, json.JSONDecodeError, TypeError):
            return None


def _extract_json(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    return json.loads(cleaned)


def _looks_like_total_sales_question(query: str) -> bool:
    query = query.strip()
    direct_phrases = [
        "total sales",
        "total revenue",
        "overall sales",
        "overall revenue",
        "how much revenue",
        "how much sales",
    ]
    if any(phrase in query for phrase in direct_phrases):
        return True
    if query in {"sales", "revenue"}:
        return True
    return ("total" in query or "overall" in query or "how much" in query) and any(word in query for word in ["sales", "revenue"])


def _looks_like_report_request(query: str) -> bool:
    direct_phrases = [
        "full report",
        "generate report",
        "make full report",
        "make report",
        "make a report",
        "analysis report",
        "detailed report",
        "report of",
    ]
    if any(phrase in query for phrase in direct_phrases):
        return True
    return bool(re.search(r"\b(make|generate|create|build)\b.*\breport\b", query))


def _looks_like_broad_analysis_request(query: str) -> bool:
    phrases = [
        "analyze uploaded dataset",
        "analyze this dataset",
        "analyze the dataset",
        "analyze dataset",
        "tell me about the given data",
        "tell me about this data",
        "tell me about the data",
        "analyze data",
    ]
    if any(phrase in query for phrase in phrases):
        return True
    return "analyze" in query and "dataset" in query


def _should_use_heuristic_only(plan: QueryPlan) -> bool:
    return plan.intent in {
        "total_sales",
        "top_product",
        "revenue_by_month",
        "dataset_overview",
        "category_performance",
        "region_performance",
        "profit_summary",
        "prediction",
        "full_report",
        "revenue_trend",
        "top_products",
        "expense_analysis",
        "customer_analysis",
    }
