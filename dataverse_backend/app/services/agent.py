"""Agentic business analytics coordinator.

The "agent" chooses from safe predefined dataframe tools. It can optionally
ask an LLM to phrase computed facts, but every number comes from pandas.
"""
from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd

from .analysis_planner import AnalysisPlan, plan_analysis
from .analytics_tools import AnalyticsTools
from .business_leads_tools import BusinessLeadsTools
from .dataset_classifier import classify_dataset
from .llm_provider import LLMProvider
from .recommendation_engine import follow_up_suggestions
from .response_builder import build_dataset_overview
from .sales_tools import SalesTools


class DataAnalysisAgent:
    def __init__(self, llm_provider: LLMProvider | None = None):
        self.llm_provider = llm_provider or LLMProvider()

    def answer(
        self,
        df: pd.DataFrame,
        question: str,
        previous_result: dict[str, Any] | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:
        base_tools = AnalyticsTools(df)
        profile = base_tools.profile
        classification = classify_dataset(df, filename=filename, profile=profile)
        dataset_type = classification["dataset_type"]
        semantic = profile["semantic_columns"]
        query = question.lower().strip()
        plan = plan_analysis(question, dataset_type, semantic)
        intent = plan.intent
        limit = plan.limit or self._extract_limit(query)

        if self._asks_for_previous_chart(query) and previous_result:
            result = dict(previous_result)
            result["answer"] = "Here is the chart view for the previous analysis."
            return result

        if not plan.answerable:
            result = self._clarification_result(plan, profile)
        elif dataset_type == "business_leads":
            result = self._answer_business_leads(df, filename, intent, limit)
        elif dataset_type == "sales":
            result = self._answer_sales(df, intent, plan.params)
        elif dataset_type == "customer":
            result = self._answer_customer(df, intent, limit, base_tools)
        elif dataset_type == "finance":
            result = self._answer_finance(df, intent, limit, base_tools)
        else:
            result = self._answer_generic(df, dataset_type, filename, intent, base_tools)

        result.setdefault("dataset_type", dataset_type)
        result.setdefault("profile", profile)
        result.setdefault("suggestions", follow_up_suggestions(dataset_type, semantic))
        result.setdefault("dataset_classification", classification)
        result.setdefault("analysis_plan", plan.__dict__)
        return result

    async def answer_with_optional_llm(
        self,
        df: pd.DataFrame,
        question: str,
        previous_result: dict[str, Any] | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:
        result = self.answer(df, question, previous_result, filename)
        if not self.llm_provider.is_configured():
            result["llm_provider"] = None
            return result

        prompt = self._build_summary_prompt(question, result)
        try:
            narrative = await self.llm_provider.generate(prompt)
            if narrative:
                result["answer"] = narrative.strip()
                result["llm_provider"] = self.llm_provider.configured_order()[0]
        except Exception as exc:
            result["warnings"].append(f"LLM summary unavailable, used deterministic analysis answer instead: {exc}")
            result["llm_provider"] = None
        return result

    def _extract_limit(self, query: str) -> int:
        match = re.search(r"\b(\d{1,2})\b", query)
        if not match:
            return 10
        return max(1, min(25, int(match.group(1))))

    def _asks_for_previous_chart(self, query: str) -> bool:
        return any(phrase in query for phrase in ["show this as a chart", "chart this", "make a chart", "visualize this"])

    def _answer_business_leads(self, df: pd.DataFrame, filename: str | None, intent: str, limit: int) -> dict[str, Any]:
        tools = BusinessLeadsTools(df, filename=filename)
        if intent == "unsupported_sales_intent":
            return {
                "intent": "unsupported_intent",
                "dataset_type": "business_leads",
                "answer": (
                    "This dataset does not contain product sales data. It contains business lead records. "
                    "I can instead show top countries, industries, highest-value business leads, or no-website opportunities."
                ),
                "method": "Checked dataset type and refused a sales-only analysis because required sales/product columns are absent.",
                "tables": [],
                "charts": [],
                "warnings": ["Sales/product analysis is not valid for this dataset."],
                "recommendations": [],
                "profile": tools.profile,
                "suggestions": tools.follow_up_suggestions(),
            }
        mapping = {
            "dataset_overview": tools.dataset_overview,
            "missing_values": tools.missing_value_report,
            "country_distribution": tools.country_distribution,
            "industry_distribution": tools.industry_distribution,
            "employee_range_distribution": tools.employee_range_distribution,
            "revenue_range_distribution": tools.revenue_range_distribution,
            "no_website_analysis": tools.no_website_analysis,
            "outreach_recommendations": lambda: tools.outreach_recommendations(limit=limit),
            "high_value_leads": lambda: tools.high_value_leads(limit=limit),
        }
        return mapping.get(intent, tools.dataset_overview)()

    def _answer_sales(self, df: pd.DataFrame, intent: str, routed: dict[str, Any]) -> dict[str, Any]:
        tools = SalesTools(df)
        limit = routed.get("limit", 10)
        if intent == "trending_products":
            return tools.trending_products(limit=limit)
        if intent == "declining_products":
            return tools.declining_products(limit=limit)
        if intent == "sales_recommendations":
            return tools.recommendations()
        if intent == "forecast":
            return tools.forecast()
        if intent == "missing_values":
            return tools.missing_value_report()
        if intent == "correlation":
            return tools.correlation_analysis()
        if intent == "outliers":
            return tools.outlier_detection()
        if intent == "category_performance":
            return tools.dimension_performance("category", limit=limit)
        if intent == "region_performance":
            return tools.dimension_performance("region", limit=limit)
        if intent == "customer_performance":
            return tools.dimension_performance("customer", limit=limit)
        if intent == "revenue_trend":
            return tools.revenue_trend(period=routed.get("period", "M"))
        if intent == "top_products":
            return tools.top_products(limit=limit, ascending=bool(routed.get("ascending")))
        return build_dataset_overview(df, "sales", profile=tools.profile)

    def _answer_customer(self, df: pd.DataFrame, intent: str, limit: int, tools: AnalyticsTools) -> dict[str, Any]:
        if intent == "top_customers":
            return self._top_customers(df, limit, tools.profile)
        if intent == "customer_locations":
            return self._customer_distribution(df, ["country", "city", "region", "state"], "customer_locations", "Customer locations", tools.profile)
        if intent == "customer_segmentation":
            return self._customer_distribution(df, ["segment", "country", "city"], "customer_segmentation", "Customer segments", tools.profile)
        if intent == "customer_recommendations":
            top = self._top_customers(df, limit, tools.profile)
            segment = self._customer_distribution(df, ["segment", "country"], "customer_segmentation", "Customer segments", tools.profile)
            recommendations = [
                "Prioritize high-spend customers for retention and upsell campaigns.",
                "Create separate campaigns for the largest customer segments or countries.",
                "Use signup dates and recent spend fields, if present, to identify lifecycle or churn-risk follow-ups.",
            ]
            top["intent"] = "customer_recommendations"
            top["answer"] = f"{top['answer']} Recommended next step: focus retention and upsell work on the highest-value customers first."
            top["recommendations"] = recommendations
            if segment.get("tables"):
                top["tables"].append(segment["tables"][0])
            if segment.get("charts"):
                top["charts"].append(segment["charts"][0])
            return top
        return build_dataset_overview(df, "customer", profile=tools.profile)

    def _answer_finance(self, df: pd.DataFrame, intent: str, limit: int, tools: AnalyticsTools) -> dict[str, Any]:
        if intent == "expense_summary":
            return self._finance_expense_summary(df, limit, tools.profile)
        if intent == "income_vs_expense":
            return self._finance_income_vs_expense(df, tools.profile)
        if intent == "finance_monthly_trend":
            return self._finance_monthly_trend(df, tools.profile)
        if intent == "finance_category_breakdown":
            return self._finance_expense_summary(df, limit, tools.profile)
        return build_dataset_overview(df, "finance", profile=tools.profile)

    def _answer_generic(
        self,
        df: pd.DataFrame,
        dataset_type: str,
        filename: str | None,
        intent: str,
        tools: AnalyticsTools,
    ) -> dict[str, Any]:
        if intent == "missing_values":
            return tools.missing_value_report()
        if intent == "correlation":
            return tools.correlation_analysis()
        if intent == "outliers":
            return tools.outlier_detection()
        if intent == "unique_values":
            return self._unique_values(df, tools.profile)
        return build_dataset_overview(df, dataset_type, filename=filename, profile=tools.profile)

    def _clarification_result(self, plan: AnalysisPlan, profile: dict[str, Any]) -> dict[str, Any]:
        return {
            "intent": "clarification_needed",
            "dataset_type": plan.dataset_type,
            "answer": plan.clarification or "I need one clarification before I can answer that from this dataset.",
            "method": "Validated the requested analysis against detected dataset type and required column roles before running tools.",
            "tables": [],
            "charts": [],
            "warnings": [plan.reason] if plan.reason else [],
            "recommendations": [],
            "profile": profile,
            "analysis_plan": plan.__dict__,
        }

    def _table(self, columns: list[str], rows: list[dict[str, Any]], title: str) -> dict[str, Any]:
        return {"title": title, "columns": columns, "rows": rows}

    def _chart(self, chart_type: str, title: str, data: list[dict[str, Any]], x_key: str, y_key: str) -> dict[str, Any]:
        return {"type": chart_type, "title": title, "data": data, "x_key": x_key, "y_key": y_key}

    def _find_first_column(self, df: pd.DataFrame, names: list[str], role_map: dict[str, str] | None = None) -> str | None:
        role_map = role_map or {}
        for role in names:
            column = role_map.get(role)
            if column in df.columns:
                return column
        normalized = {str(column).lower().replace(" ", "_"): str(column) for column in df.columns}
        for name in names:
            key = name.lower().replace(" ", "_")
            if key in normalized:
                return normalized[key]
        for column in df.columns:
            column_norm = str(column).lower().replace(" ", "_")
            if any(name.lower().replace(" ", "_") in column_norm for name in names):
                return str(column)
        return None

    def _top_customers(self, df: pd.DataFrame, limit: int, profile: dict[str, Any]) -> dict[str, Any]:
        semantic = profile.get("semantic_columns", {})
        customer_col = self._find_first_column(df, ["customer", "customer_name", "client", "buyer"], semantic)
        spend_col = self._find_first_column(df, ["spend", "total_spend", "lifetime_value", "ltv", "revenue", "amount"], semantic)
        result = {
            "intent": "top_customers",
            "dataset_type": "customer",
            "answer": "",
            "method": "Ranked customers using the detected customer identifier and numeric spend/value column.",
            "tables": [],
            "charts": [],
            "warnings": [],
            "recommendations": [],
            "profile": profile,
        }
        if not customer_col or not spend_col or not pd.api.types.is_numeric_dtype(pd.to_numeric(df[spend_col], errors="coerce")):
            result["answer"] = "I need a customer name/id column and a numeric spend/value column to rank top customers."
            result["warnings"].append("Missing customer or spend/value column.")
            return result
        grouped = (
            df.assign(_metric=pd.to_numeric(df[spend_col], errors="coerce"))
            .dropna(subset=[customer_col, "_metric"])
            .groupby(customer_col)["_metric"]
            .sum()
            .sort_values(ascending=False)
            .head(limit)
        )
        total = float(pd.to_numeric(df[spend_col], errors="coerce").sum())
        rows = [
            {
                customer_col: str(customer),
                f"total_{spend_col}": round(float(value), 2),
                "share_pct": round((float(value) / total * 100) if total else 0, 1),
            }
            for customer, value in grouped.items()
        ]
        if rows:
            result["answer"] = f"{rows[0][customer_col]} is the top customer by {spend_col}, with {rows[0][f'total_{spend_col}']:,.2f}."
        else:
            result["answer"] = "No customer spend rows were available after cleaning."
        result["tables"].append(self._table([customer_col, f"total_{spend_col}", "share_pct"], rows, "Top customers"))
        result["charts"].append(self._chart("bar", "Top customers", rows, customer_col, f"total_{spend_col}"))
        return result

    def _customer_distribution(
        self,
        df: pd.DataFrame,
        candidate_columns: list[str],
        intent: str,
        title: str,
        profile: dict[str, Any],
    ) -> dict[str, Any]:
        semantic = profile.get("semantic_columns", {})
        column = self._find_first_column(df, candidate_columns, semantic)
        result = {
            "intent": intent,
            "dataset_type": "customer",
            "answer": "",
            "method": f"Counted customer records by {column or 'available segment'} column.",
            "tables": [],
            "charts": [],
            "warnings": [],
            "recommendations": [],
            "profile": profile,
        }
        if not column:
            result["answer"] = "I could not find a segment or location column for this customer analysis."
            result["warnings"].append("Missing segment/location column.")
            return result
        counts = df[column].fillna("Unknown").astype(str).value_counts().head(20)
        rows = [{"value": str(value), "customers": int(count)} for value, count in counts.items()]
        result["answer"] = f"{rows[0]['value']} has the most customers ({rows[0]['customers']})." if rows else "No customer groups were available."
        result["tables"].append(self._table(["value", "customers"], rows, title))
        result["charts"].append(self._chart("bar", title, rows, "value", "customers"))
        return result

    def _finance_expense_summary(self, df: pd.DataFrame, limit: int, profile: dict[str, Any]) -> dict[str, Any]:
        expense_col = self._find_first_column(df, ["expense", "expenses", "cost", "debit", "amount"], profile.get("semantic_columns", {}))
        category_col = self._find_first_column(df, ["category", "account", "type"], profile.get("semantic_columns", {}))
        result = {
            "intent": "expense_summary",
            "dataset_type": "finance",
            "answer": "",
            "method": "Grouped numeric expense values by category/account using pandas.",
            "tables": [],
            "charts": [],
            "warnings": [],
            "recommendations": [],
            "profile": profile,
        }
        if not expense_col:
            result["answer"] = "I could not find a numeric expense, debit, cost, or amount column."
            result["warnings"].append("Missing expense column.")
            return result
        values = pd.to_numeric(df[expense_col], errors="coerce").fillna(0)
        if category_col:
            grouped = df.assign(_expense=values).groupby(category_col)["_expense"].sum().sort_values(ascending=False).head(limit)
            rows = [{"category": str(name), "total_expense": round(float(value), 2)} for name, value in grouped.items()]
        else:
            rows = [{"category": "All expenses", "total_expense": round(float(values.sum()), 2)}]
        total = round(float(values.sum()), 2)
        leader = rows[0] if rows else None
        result["answer"] = (
            f"{leader['category']} is the largest expense category at {leader['total_expense']:,.2f}; total expenses are {total:,.2f}."
            if leader else f"Total expenses are {total:,.2f}."
        )
        result["tables"].append(self._table(["category", "total_expense"], rows, "Expense summary"))
        result["charts"].append(self._chart("bar", "Expense summary", rows, "category", "total_expense"))
        return result

    def _finance_income_vs_expense(self, df: pd.DataFrame, profile: dict[str, Any]) -> dict[str, Any]:
        income_col = self._find_first_column(df, ["income", "revenue", "credit"], profile.get("semantic_columns", {}))
        expense_col = self._find_first_column(df, ["expense", "expenses", "cost", "debit", "amount"], profile.get("semantic_columns", {}))
        result = {
            "intent": "income_vs_expense",
            "dataset_type": "finance",
            "answer": "",
            "method": "Summed detected income and expense columns.",
            "tables": [],
            "charts": [],
            "warnings": [],
            "recommendations": [],
            "profile": profile,
        }
        if not income_col or not expense_col:
            result["answer"] = "I need both income and expense columns to compare income vs expense."
            result["warnings"].append("Missing income or expense column.")
            return result
        income = float(pd.to_numeric(df[income_col], errors="coerce").fillna(0).sum())
        expense = float(pd.to_numeric(df[expense_col], errors="coerce").fillna(0).sum())
        net = income - expense
        rows = [
            {"metric": "income", "amount": round(income, 2)},
            {"metric": "expense", "amount": round(expense, 2)},
            {"metric": "net", "amount": round(net, 2)},
        ]
        result["answer"] = f"Income totals {income:,.2f}, expenses total {expense:,.2f}, so net is {net:,.2f}."
        result["tables"].append(self._table(["metric", "amount"], rows, "Income vs expense"))
        result["charts"].append(self._chart("bar", "Income vs expense", rows, "metric", "amount"))
        return result

    def _finance_monthly_trend(self, df: pd.DataFrame, profile: dict[str, Any]) -> dict[str, Any]:
        date_col = self._find_first_column(df, ["transaction_date", "date", "posted_date"], profile.get("semantic_columns", {}))
        amount_col = self._find_first_column(df, ["amount", "expense", "income", "revenue"], profile.get("semantic_columns", {}))
        result = {
            "intent": "finance_monthly_trend",
            "dataset_type": "finance",
            "answer": "",
            "method": "Grouped detected finance metric by transaction month.",
            "tables": [],
            "charts": [],
            "warnings": [],
            "recommendations": [],
            "profile": profile,
        }
        if not date_col or not amount_col:
            result["answer"] = "I need a transaction date and a numeric amount/income/expense column for a monthly trend."
            result["warnings"].append("Missing date or metric column.")
            return result
        working = df[[date_col, amount_col]].copy()
        working[date_col] = pd.to_datetime(working[date_col], errors="coerce")
        working[amount_col] = pd.to_numeric(working[amount_col], errors="coerce")
        working = working.dropna(subset=[date_col, amount_col])
        working["_period"] = working[date_col].dt.to_period("M")
        grouped = working.groupby("_period")[amount_col].sum().sort_index()
        rows = [{"period": str(period), amount_col: round(float(value), 2)} for period, value in grouped.items()]
        result["answer"] = f"{amount_col} is available across {len(rows)} monthly periods." if rows else "No valid dated finance rows were available."
        result["tables"].append(self._table(["period", amount_col], rows, "Monthly finance trend"))
        result["charts"].append(self._chart("line", "Monthly finance trend", rows, "period", amount_col))
        return result

    def _unique_values(self, df: pd.DataFrame, profile: dict[str, Any]) -> dict[str, Any]:
        rows = []
        for column in df.columns:
            counts = df[column].fillna("Missing").astype(str).value_counts().head(5)
            rows.append(
                {
                    "column": str(column),
                    "unique_values": int(df[column].nunique(dropna=True)),
                    "top_values": ", ".join(f"{value} ({count})" for value, count in counts.items()),
                }
            )
        return {
            "intent": "unique_values",
            "dataset_type": "generic",
            "answer": f"Computed unique-value counts for {len(df.columns)} columns.",
            "method": "Counted distinct and most common values per column.",
            "tables": [self._table(["column", "unique_values", "top_values"], rows, "Unique values by column")],
            "charts": [],
            "warnings": [],
            "recommendations": [],
            "profile": profile,
        }

    def _build_summary_prompt(self, question: str, result: dict[str, Any]) -> str:
        facts = {
            "intent": result.get("intent"),
            "method": result.get("method"),
            "answer": result.get("answer"),
            "tables": result.get("tables", [])[:1],
            "warnings": result.get("warnings", []),
            "recommendations": result.get("recommendations", []),
        }
        return (
            "Rewrite these computed analytics facts in concise business language. "
            "Use only the facts and numbers provided, include a warning if present, "
            "and do not invent extra calculations.\n\n"
            f"User question: {question}\n"
            f"Computed facts JSON:\n{json.dumps(facts, default=str)}"
        )
