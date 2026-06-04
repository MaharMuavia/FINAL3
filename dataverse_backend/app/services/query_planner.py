"""Semantic query planning for business analytics questions."""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from .llm_provider import LLMProvider


Intent = Literal[
    "dataset_overview",
    "revenue_trend",
    "top_products",
    "category_performance",
    "customer_analysis",
    "profit_analysis",
    "expense_analysis",
    "prediction",
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
        if not query or not self.llm_provider.is_configured():
            return heuristic.model_dump()
        try:
            asyncio.get_running_loop()
            return heuristic.model_dump()
        except RuntimeError:
            return asyncio.run(self.plan_async(query, semantic_map, dataset_profile))

    async def plan_async(self, query: str | None, semantic_map: dict[str, Any], dataset_profile: dict[str, Any] | None = None) -> dict[str, Any]:
        heuristic = self._heuristic_plan(query or "", semantic_map)
        if not query or not self.llm_provider.is_configured():
            return heuristic.model_dump()
        llm_plan = await self._llm_plan(query, semantic_map, dataset_profile or {})
        if llm_plan is None:
            return heuristic.model_dump()
        return llm_plan.model_dump()

    def _heuristic_plan(self, query: str, semantic_map: dict[str, Any]) -> QueryPlan:
        q = query.lower().strip()
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

        if any(word in q for word in ["predict", "forecast", "future"]):
            return QueryPlan(intent="prediction", metric="revenue", dimensions=dimensions, needs_prediction=True, needs_xai="why" in q or "driver" in q)
        if any(word in q for word in ["why", "driver", "drivers", "explain"]) and any(word in q for word in ["sales", "revenue", "profit"]):
            return QueryPlan(intent="generic_question", metric="revenue", dimensions=dimensions, needs_xai=True)
        if any(word in q for word in ["correlation", "relationship", "related"]):
            return QueryPlan(intent="correlation", metric="revenue", dimensions=dimensions)
        if any(word in q for word in ["anomaly", "outlier", "unusual"]):
            return QueryPlan(intent="anomaly", metric="revenue", dimensions=dimensions)
        if any(word in q for word in ["expense", "cost", "spending"]):
            return QueryPlan(intent="expense_analysis", metric="expense", dimensions=dimensions or ["category"])
        if any(word in q for word in ["profit", "margin"]):
            return QueryPlan(intent="profit_analysis", metric="profit", dimensions=dimensions)
        if any(word in q for word in ["customer", "client", "buyer"]):
            return QueryPlan(intent="customer_analysis", metric="revenue", dimensions=dimensions or ["customer"])
        if any(word in q for word in ["category", "department", "segment"]) and any(word in q for word in ["best", "top", "perform", "performance", "highest", "most"]):
            return QueryPlan(intent="category_performance", metric="revenue", dimensions=dimensions or ["category"])
        if any(word in q for word in ["product", "item", "sku", "selling", "sells"]) and any(word in q for word in ["best", "top", "highest", "most", "sell", "sells"]):
            return QueryPlan(intent="top_products", metric="revenue" if semantic_map.get("metrics", {}).get("revenue") else "quantity", dimensions=dimensions or ["product"])
        if any(word in q for word in ["revenue", "sales", "income", "selling"]) and ({"month", "date"} & set(dimensions) or "trend" in q or "over time" in q):
            return QueryPlan(intent="revenue_trend", metric="revenue", dimensions=["month" if "month" in dimensions else "date"])
        if any(word in q for word in ["overview", "summarize", "summary", "tell me about"]):
            return QueryPlan(intent="dataset_overview", metric="revenue", dimensions=[])
        return QueryPlan(intent="dataset_overview", metric="revenue", dimensions=dimensions)

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
