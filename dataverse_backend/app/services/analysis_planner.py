"""Dataset-aware analysis planning before dataframe tools run."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .intent_router import route_intent


@dataclass(frozen=True)
class AnalysisPlan:
    dataset_type: str
    intent: str
    tool_name: str
    answerable: bool = True
    reason: str = ""
    required_roles: list[str] = field(default_factory=list)
    missing_roles: list[str] = field(default_factory=list)
    limit: int = 10
    params: dict[str, Any] = field(default_factory=dict)
    clarification: str | None = None


def _has_role(semantic_columns: dict[str, Any], role: str) -> bool:
    value = semantic_columns.get(role)
    return bool(value)


def _missing(semantic_columns: dict[str, Any], required_roles: list[str]) -> list[str]:
    return [role for role in required_roles if not _has_role(semantic_columns, role)]


def _is_forecast_or_sales_trend(query: str) -> bool:
    return any(
        phrase in query
        for phrase in [
            "forecast",
            "predict",
            "next month",
            "next quarter",
            "sales trend",
            "revenue trend",
            "monthly revenue",
            "over time revenue",
        ]
    )


def plan_analysis(
    question: str,
    dataset_type: str,
    semantic_columns: dict[str, Any] | None = None,
) -> AnalysisPlan:
    """Create a validated dataframe-analysis plan for a user question.

    The planner is deliberately conservative: it routes to known pandas tools,
    rejects mismatched dataset intents, and asks for clarification when required
    columns are not present.
    """
    semantic = semantic_columns or {}
    query = question.lower().strip()
    routed = route_intent(question, dataset_type, semantic)
    intent = routed["intent"]
    limit = int(routed.get("limit", 10))

    if dataset_type == "business_leads":
        if _is_forecast_or_sales_trend(query):
            return AnalysisPlan(
                dataset_type=dataset_type,
                intent="clarification_needed",
                tool_name="clarify",
                answerable=False,
                reason="Forecasting requires dated numeric sales or revenue observations, but this is a business leads dataset.",
                required_roles=["transaction_date", "sales_amount"],
                missing_roles=["transaction_date", "sales_amount"],
                limit=limit,
                clarification=(
                    "This dataset contains business lead records, not date-stamped numeric revenue transactions. "
                    "To forecast next month revenue, upload sales or finance data with a date-stamped numeric revenue column. "
                    "With this dataset I can prioritize leads, analyze countries, industries, employee ranges, revenue ranges, or no-website opportunities."
                ),
            )

        required_by_intent = {
            "country_distribution": ["country"],
            "industry_distribution": ["industry"],
            "employee_range_distribution": ["employee_range"],
            "revenue_range_distribution": ["revenue_range"],
            "no_website_analysis": ["website"],
            "outreach_recommendations": ["website", "country", "industry"],
            "high_value_leads": ["business_name"],
        }
        required = required_by_intent.get(intent, [])
        missing = _missing(semantic, required)
        return AnalysisPlan(
            dataset_type=dataset_type,
            intent=intent,
            tool_name=f"business_leads.{intent}",
            answerable=not missing,
            reason="Matched a business-leads analysis tool from dataset type and question intent.",
            required_roles=required,
            missing_roles=missing,
            limit=limit,
        )

    if dataset_type == "sales":
        required_by_intent = {
            "top_products": ["product", "sales_amount"],
            "trending_products": ["product", "sales_amount", "date"],
            "declining_products": ["product", "sales_amount", "date"],
            "revenue_trend": ["sales_amount", "date"],
            "category_performance": ["category", "sales_amount"],
            "region_performance": ["region", "sales_amount"],
            "customer_performance": ["customer", "sales_amount"],
            "forecast": ["sales_amount", "date"],
        }
        required = required_by_intent.get(intent, [])
        missing = _missing(semantic, required)
        if missing:
            return AnalysisPlan(
                dataset_type=dataset_type,
                intent="clarification_needed",
                tool_name="clarify",
                answerable=False,
                reason=f"The requested sales analysis is missing required roles: {', '.join(missing)}.",
                required_roles=required,
                missing_roles=missing,
                limit=limit,
                params=routed,
                clarification=(
                    "I need the missing column roles before I can run that sales analysis: "
                    f"{', '.join(missing)}. I can still summarize the dataset or report missing values."
                ),
            )
        return AnalysisPlan(dataset_type, intent, f"sales.{intent}", True, "Matched a sales analysis tool.", required, [], limit, routed)

    if dataset_type == "customer":
        if any(word in query for word in ["top", "best", "highest", "valuable", "value", "spend", "customers"]):
            return AnalysisPlan(dataset_type, "top_customers", "customer.top_customers", True, "Rank customers by spend/value.", ["customer"], [], limit)
        if any(word in query for word in ["segment", "segments", "group"]):
            return AnalysisPlan(dataset_type, "customer_segmentation", "customer.customer_segmentation", True, "Segment customers using available segment/location/spend columns.", [], [], limit)
        if any(word in query for word in ["country", "city", "location", "where"]):
            return AnalysisPlan(dataset_type, "customer_locations", "customer.customer_locations", True, "Count customers by location.", [], [], limit)
        if any(word in query for word in ["recommend", "what should i", "strategy"]):
            return AnalysisPlan(dataset_type, "customer_recommendations", "customer.customer_recommendations", True, "Recommend customer actions from customer fields.", [], [], limit)
        return AnalysisPlan(dataset_type, "dataset_overview", "generic.dataset_overview", True, "Summarize customer dataset.", [], [], limit)

    if dataset_type == "finance":
        if any(word in query for word in ["expense", "expenses", "cost", "spending"]):
            return AnalysisPlan(dataset_type, "expense_summary", "finance.expense_summary", True, "Summarize expenses by category/account.", [], [], limit)
        if any(phrase in query for phrase in ["income vs expense", "income", "cash flow", "profit"]):
            return AnalysisPlan(dataset_type, "income_vs_expense", "finance.income_vs_expense", True, "Compare income and expense columns.", [], [], limit)
        if any(word in query for word in ["monthly", "trend", "over time"]):
            return AnalysisPlan(dataset_type, "finance_monthly_trend", "finance.monthly_trend", True, "Group finance metrics by month.", [], [], limit)
        if any(word in query for word in ["category", "breakdown"]):
            return AnalysisPlan(dataset_type, "finance_category_breakdown", "finance.category_breakdown", True, "Break finance rows down by category.", [], [], limit)
        return AnalysisPlan(dataset_type, "dataset_overview", "generic.dataset_overview", True, "Summarize finance dataset.", [], [], limit)

    if any(phrase in query for phrase in ["unique values", "repeated", "duplicates by column", "values by column"]):
        return AnalysisPlan(dataset_type, "unique_values", "generic.unique_values", True, "Count common values by column.", [], [], limit)
    if intent in {"missing_values", "correlation", "outliers", "dataset_overview"}:
        return AnalysisPlan(dataset_type, intent, f"generic.{intent}", True, "Matched a generic dataframe analysis.", [], [], limit)
    return AnalysisPlan(dataset_type, "dataset_overview", "generic.dataset_overview", True, "Fallback to safe dataset overview.", [], [], limit)
