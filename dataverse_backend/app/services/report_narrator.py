"""Analyst-style report narration from computed facts only."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from ..core.config import settings
from .llm_provider import LLMProvider


class ReportNarrator:
    """Build deterministic reports and optionally polish them with an LLM."""

    def __init__(self, llm_provider: Any | None = None):
        self.llm_provider = llm_provider if llm_provider is not None else LLMProvider()

    def narrate(self, facts: dict[str, Any], *, use_llm: bool = True, provider: str | None = None) -> dict[str, Any]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.narrate_async(facts, use_llm=use_llm, provider=provider))
        return self._deterministic(facts)

    async def narrate_async(self, facts: dict[str, Any], *, use_llm: bool = True, provider: str | None = None) -> dict[str, Any]:
        fallback = self._deterministic(facts)
        if not use_llm or provider == "deterministic":
            fallback["warnings"] = list(dict.fromkeys([
                *fallback.get("warnings", []),
                "LLM narration is disabled; deterministic narration was used.",
            ])) if not use_llm else fallback.get("warnings", [])
            return fallback
        llm_provider = LLMProvider(provider=provider) if provider else self.llm_provider
        is_configured = getattr(llm_provider, "is_configured", None)
        if callable(is_configured) and not is_configured():
            requested = provider or settings.LLM_PROVIDER or "auto"
            fallback["warnings"] = list(dict.fromkeys([
                *fallback.get("warnings", []),
                f"LLM narration requested with provider '{requested}', but no configured provider key was found; deterministic narration was used.",
            ]))
            return fallback
        try:
            text = await asyncio.wait_for(
                llm_provider.generate(self._prompt(facts)),
                timeout=settings.REPORT_NARRATOR_TIMEOUT_SECONDS,
            )
            if text:
                fallback["executive_summary"] = self._preserve_required_facts(text.strip(), facts, fallback)
                fallback["narration_provider"] = getattr(llm_provider, "last_provider", "llm")
            else:
                fallback["warnings"] = list(dict.fromkeys([
                    *fallback.get("warnings", []),
                    "LLM narration returned no text; deterministic narration was used.",
                    *getattr(llm_provider, "last_errors", []),
                ]))
        except Exception:
            fallback["warnings"] = list(dict.fromkeys([
                *fallback.get("warnings", []),
                "LLM narration failed or timed out; deterministic narration was used.",
                *getattr(llm_provider, "last_errors", []),
            ]))
        return fallback

    def _preserve_required_facts(self, text: str, facts: dict[str, Any], fallback: dict[str, Any]) -> str:
        business_summary = facts.get("business_summary") or {}
        if not business_summary:
            return text
        required = (
            f"Business summary: sales Rs {business_summary.get('total_sales', 0)}, "
            f"expenses Rs {business_summary.get('total_expenses', 0)}, "
            f"udhaar Rs {business_summary.get('udhaar_outstanding', 0)}, "
            f"net profit Rs {business_summary.get('net_profit', 0)}."
        )
        if f"sales Rs {business_summary.get('total_sales', 0)}" in text:
            return text
        return f"{text}\n\n{required or fallback.get('executive_summary', '')}".strip()

    def _prompt(self, facts: dict[str, Any]) -> str:
        safe = {
            "dataset_profile": facts.get("dataset_profile"),
            "semantic_map": facts.get("semantic_map"),
            "business_summary": facts.get("business_summary"),
            "business_metrics": facts.get("business_metrics"),
            "query_answer": facts.get("query_answer"),
            "data_quality": facts.get("data_quality"),
            "eda": _cap(facts.get("eda")),
            "trends": facts.get("trends"),
            "correlations": facts.get("correlations"),
            "outliers": facts.get("outliers"),
            "target_suggestions": facts.get("target_suggestions"),
            "prediction": facts.get("prediction"),
            "xai": facts.get("xai"),
        }
        return (
            "Write a concise professional AI data analyst report with these sections: "
            "Executive Summary, Dataset Overview, Data Quality, Key Insights, Trends, Correlations, "
            "Outliers, Prediction Results, XAI Explanation, Risks and Limitations, Recommendations, Next Questions. "
            "Use only the computed facts below and do not invent numbers.\n"
            f"{json.dumps(safe, default=str)[:12000]}"
        )

    def _deterministic(self, facts: dict[str, Any]) -> dict[str, Any]:
        profile = facts.get("dataset_profile") or {}
        quality = facts.get("data_quality") or {}
        trends = facts.get("trends") or {}
        correlations = facts.get("correlations") or {}
        outliers = facts.get("outliers") or {}
        prediction = facts.get("prediction") or {}
        xai = facts.get("xai") or {}
        suggestions = facts.get("target_suggestions") or []
        report_summary = profile.get("report_summary") or {}
        business_summary = facts.get("business_summary") or profile.get("business_summary") or {}
        semantic_map = facts.get("semantic_map") or {}
        business_metrics = facts.get("business_metrics") or {}
        product_analysis = facts.get("product_analysis") or {}
        food_analysis = facts.get("food_analysis") or {}
        query_answer = facts.get("query_answer") or {}
        query_plan = facts.get("query_plan") or {}
        is_ai_khata = semantic_map.get("dataset_type") in {"ai_khata_transaction_report", "business_transaction_dataset"}
        is_food_dataset = semantic_map.get("dataset_type") == "food_dataset"
        is_focused = str(query_plan.get("report_mode")) == "focused_answer_report"
        intent = str(query_plan.get("intent") or "dataset_overview")

        key_insights = [
            f"Dataset contains {profile.get('row_count', 0)} rows and {profile.get('column_count', 0)} columns.",
            f"Semantic dataset type is {semantic_map.get('dataset_type', profile.get('dataset_type', 'generic_tabular'))}.",
            f"Data quality score is {quality.get('data_quality_score', 'unknown')}.",
        ]
        if business_metrics.get("total_revenue") is not None:
            key_insights.append(f"Total revenue is {business_metrics.get('total_revenue')}.")
        if business_metrics.get("total_quantity") is not None:
            key_insights.append(f"Total quantity is {business_metrics.get('total_quantity')}.")
        if business_metrics.get("total_profit") is not None:
            key_insights.append(f"Total profit is {business_metrics.get('total_profit')} with gross margin {business_metrics.get('gross_margin')}.")
        if business_metrics.get("top_products"):
            top_product = business_metrics["top_products"][0]
            key_insights.append(f"Top product: {top_product.get('product') or top_product}.")
        if business_metrics.get("top_categories"):
            top_category = business_metrics["top_categories"][0]
            key_insights.append(f"Top category: {top_category.get('category') or top_category}.")
        if trends.get("series"):
            first_trend = trends["series"][0]
            key_insights.append(f"{first_trend['value_column']} trend is {first_trend['direction']} with slope {first_trend['slope']}.")
        if correlations.get("strong_pairs"):
            pair = correlations["strong_pairs"][0]
            key_insights.append(f"Strongest correlation: {pair['column_a']} and {pair['column_b']} ({pair['correlation']}).")
        if prediction.get("status") == "complete":
            key_insights.append(f"Prediction model trained for {prediction.get('target_column')} using {prediction.get('selected_model')}.")
        elif suggestions:
            key_insights.append(f"Best target suggestion is {suggestions[0]['column']} ({suggestions[0]['task_type']}).")
        for key in ("Total Sales", "Total Expenses", "Udhaar Outstanding", "Net Profit", "Profit Status"):
            if key in report_summary:
                key_insights.append(f"{key}: {report_summary[key]}.")
        if product_analysis.get("insights"):
            key_insights.extend(product_analysis["insights"])
        if food_analysis.get("warnings"):
            key_insights.append(food_analysis["warnings"][0])
        if business_summary and is_ai_khata:
            key_insights.append(
                "Business summary: "
                f"sales Rs {business_summary.get('total_sales', 0)}, "
                f"expenses Rs {business_summary.get('total_expenses', 0)}, "
                f"udhaar Rs {business_summary.get('udhaar_outstanding', 0)}, "
                f"net profit Rs {business_summary.get('net_profit', 0)}."
            )
        if business_metrics.get("top_categories"):
            top_category = business_metrics["top_categories"][0]
            key_insights.append(f"{top_category.get('category')} is top category by revenue with {top_category.get('revenue')}.")
        if business_metrics.get("top_categories_by_transactions"):
            top_category_count = business_metrics["top_categories_by_transactions"][0]
            key_insights.append(f"{top_category_count.get('category')} is top category by transaction count with {top_category_count.get('transaction_count')} rows.")
        if business_metrics.get("top_regions"):
            top_region = business_metrics["top_regions"][0]
            key_insights.append(f"{top_region.get('region')} is top region by revenue with {top_region.get('revenue')}.")

        warnings = list(dict.fromkeys((quality.get("warnings") or []) + (business_metrics.get("data_limitations") or []) + (prediction.get("limitations") or []) + (xai.get("warnings") or [])))
        recommendations = [
            "Review missing values, duplicate rows, high-cardinality columns, and outliers before operational decisions.",
            "Validate inferred target columns and model drivers with domain expertise.",
            "Render the chart-ready JSON specs to inspect distributions, trends, correlations, and model behavior.",
        ]
        if is_food_dataset:
            recommendations = [
                "Use frequency analysis for catalog composition, not sales performance.",
                "Collect order quantity, revenue, cost, and timestamps before asking sales or profit questions.",
                "Validate any category model on external food items before trusting perfect accuracy.",
            ]
        if business_summary and is_ai_khata:
            recommendations.append("For AI Khata reports, calculate revenue only from SALES rows; keep EXPENSE and UDHAAR separate.")
        recommendations.extend(product_analysis.get("recommendations") or [])
        if prediction.get("status") == "complete":
            recommendations.append("Compare model test metrics with a business baseline before deployment.")
        else:
            recommendations.append("Provide target_column or improve target confidence to enable prediction.")

        next_questions = [
            "Which target column should be optimized for prediction?",
            "Should outliers or missing values be cleaned and the analysis rerun?",
            "Which segment, region, product, or category should be explored next?",
        ]
        if prediction.get("status") == "complete":
            next_questions.append("Should the model be validated on a time-based holdout or external dataset?")

        if is_focused and not is_food_dataset and intent != "full_report":
            sections = {
                "Executive Summary": query_answer.get("answer") or " ".join(key_insights[:4]),
                "Dataset Overview": f"Rows: {profile.get('row_count', 0)}. Columns: {profile.get('column_count', 0)}. Type: {semantic_map.get('dataset_type', profile.get('dataset_type', 'generic_tabular'))}.",
                "Data Quality": f"Missing cells: {quality.get('missing_cells', 0)}. Duplicate rows: {quality.get('duplicate_rows', 0)}. Quality score: {quality.get('data_quality_score', 'unknown')}.",
                "Limitations": " ".join(warnings) if warnings else "No major automated warnings.",
                "Recommendations": " ".join((query_answer.get("recommendations") or recommendations)[:3]),
                "Next Questions": " ".join((query_answer.get("follow_up_ideas") or next_questions)[:3]),
            }
            return {
                "executive_summary": sections["Executive Summary"],
                "report_sections": sections,
                "key_insights": key_insights[:6],
                "recommendations": query_answer.get("recommendations") or recommendations[:3],
                "warnings": warnings,
                "next_questions": query_answer.get("follow_up_ideas") or next_questions[:3],
                "narration_provider": "deterministic",
            }

        sections = {
            "Executive Summary": " ".join(key_insights),
            "Dataset Overview": f"Rows: {profile.get('row_count', 0)}. Columns: {profile.get('column_count', 0)}. Type: {profile.get('dataset_type', 'generic')}.",
            "Semantic Mapping": f"Detected {semantic_map.get('dataset_type', 'generic_tabular')} with column roles: {semantic_map.get('column_roles', {})}.",
            "Business Summary": (
                f"Sales: {business_summary.get('total_sales', 0)}. "
                f"Expenses: {business_summary.get('total_expenses', 0)}. "
                f"Udhaar: {business_summary.get('udhaar_outstanding', 0)}. "
                f"Net profit: {business_summary.get('net_profit', 0)}."
                if business_summary and is_ai_khata
                else (
                    f"Revenue: {business_metrics.get('total_revenue')}. "
                    f"Quantity: {business_metrics.get('total_quantity')}. "
                    f"Profit: {business_metrics.get('total_profit')}. "
                    f"Gross margin: {business_metrics.get('gross_margin')}."
                )
            ),
            "Data Quality": f"Missing cells: {quality.get('missing_cells', 0)}. Duplicate rows: {quality.get('duplicate_rows', 0)}.",
            "Key Insights": " ".join(key_insights),
            "Query Answer": query_answer.get("answer", "No query-specific answer was requested."),
            "Trends": f"Detected {len(trends.get('series', []))} trend series.",
            "Correlations": f"Detected {len(correlations.get('strong_pairs', []))} strong correlation pairs.",
            "Outliers": f"Detected {outliers.get('total_outlier_cells', 0)} numeric outlier flags.",
            "Prediction Results": prediction.get("reason") or prediction.get("status", "not run"),
            "XAI Explanation": xai.get("plain_english_explanation", "XAI was not run."),
            "Risks and Limitations": " ".join(warnings) if warnings else "No major automated warnings.",
            "Recommendations": " ".join(recommendations),
            "Next Questions": " ".join(next_questions),
        }
        if is_food_dataset:
            sections = {
                "Executive Summary": " ".join(key_insights),
                "Dataset Overview": (
                    f"Rows: {profile.get('row_count', 0)}. Columns: {profile.get('column_count', 0)}. "
                    "Detected as a food classification / food catalog dataset."
                ),
                "Data Quality": f"Missing cells: {quality.get('missing_cells', 0)}. Duplicate rows: {quality.get('duplicate_rows', 0)}.",
                "Dataset Limitations": food_analysis.get("warnings", [""])[0],
                "Food Frequency Analysis": " ".join(food_analysis.get("insights", [])) or "Food frequency analysis was unavailable.",
                "Category Distribution": _table_summary(food_analysis, "Most common category"),
                "Cuisine Distribution": _table_summary(food_analysis, "Most common cuisine"),
                "Main Ingredient Distribution": _table_summary(food_analysis, "Most common main ingredient"),
                "Spice Level Distribution": _table_summary(food_analysis, "Spice level distribution"),
                "Calories Statistics": json.dumps(food_analysis.get("calories_stats") or {}, default=str),
                "Prediction/Model Summary": _prediction_summary(prediction),
                "XAI Explanation": _xai_summary(xai, prediction),
                "Risks and Limitations": " ".join(warnings) if warnings else food_analysis.get("warnings", ["No major automated warnings."])[0],
                "Recommendations": " ".join(recommendations),
                "Next Questions": " ".join(food_analysis.get("next_questions") or next_questions),
            }

        return {
            "executive_summary": sections["Executive Summary"],
            "report_sections": sections,
            "key_insights": key_insights,
            "recommendations": recommendations,
            "warnings": warnings,
            "next_questions": next_questions,
            "narration_provider": "deterministic",
        }


def _cap(value: Any, max_chars: int = 4000) -> Any:
    text = json.dumps(value, default=str)
    if len(text) <= max_chars:
        return value
    return {"truncated": True, "preview": text[:max_chars]}


def _table_summary(food_analysis: dict[str, Any], title: str) -> str:
    table = next((item for item in food_analysis.get("tables", []) if item.get("title") == title), None)
    rows = table.get("rows", []) if isinstance(table, dict) else []
    if not rows:
        return f"{title} was unavailable."
    first = rows[0]
    label_key = next((key for key in first.keys() if key != "count"), "value")
    return f"{first.get(label_key)} is the leading value with {first.get('count')} rows."


def _prediction_summary(prediction: dict[str, Any]) -> str:
    if prediction.get("status") != "complete":
        return prediction.get("reason") or "Prediction/modeling was not run."
    metrics = prediction.get("test_metrics") or {}
    summary = (
        f"{prediction.get('selected_model')} was trained for {prediction.get('target_column')} "
        f"as a {prediction.get('task_type')} task. Test metrics: {metrics}."
    )
    limitations = " ".join(str(item) for item in prediction.get("limitations", []))
    return f"{summary} {limitations}".strip()


def _xai_summary(xai: dict[str, Any], prediction: dict[str, Any]) -> str:
    if not xai.get("top_features"):
        return "XAI could not be generated because the model did not expose valid feature importance."
    warnings = " ".join(str(item) for item in xai.get("warnings", []))
    leakage = " ".join(str(item) for item in prediction.get("limitations", []) if "leakage" in str(item).lower())
    return (
        f"Method used: {xai.get('method')}. Top features: {', '.join(xai.get('top_features', []))}. "
        f"{xai.get('plain_english_explanation', '')} {warnings} {leakage}"
    ).strip()
