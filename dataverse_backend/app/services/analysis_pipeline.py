"""Clean deterministic AI data analyst pipeline."""
from __future__ import annotations

from typing import Any

import pandas as pd

from .data_profiler import profile_dataframe
from .ai_khata import AI_KHATA_TYPES, business_summary, monthly_sales_revenue
from .business_metrics import answer_business_query, calculate_business_metrics, compute_product_trends
from .data_quality import (
    build_chart_specs,
    compute_correlations,
    compute_data_quality,
    compute_eda,
    compute_outliers,
    compute_trends,
    json_safe,
    normalize_chart_specs,
)
from .modeling import train_prediction
from .query_planner import QueryPlanner
from .report_narrator import ReportNarrator
from .semantic_mapper import SemanticMapper
from .session_store import create_session_id, persist_dataframe_for_session
from .xai import explain_model

try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False



class AnalysisPipeline:
    """Run profile, quality, EDA, trends, prediction, XAI, charts, and narration."""

    def __init__(self, narrator: ReportNarrator | None = None):
        self.narrator = narrator or ReportNarrator()

    def run_full_analysis(
        self,
        df: pd.DataFrame,
        query: str | None = None,
        target_column: str | None = None,
        task_type: str | None = None,
        run_predictions: bool = True,
        run_xai: bool = True,
        session_id: str | None = None,
        filename: str | None = None,
        use_llm: bool = True,
        provider: str | None = None,
        semantic_map: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        semantic_map = semantic_map or SemanticMapper().map_dataframe(df, filename=filename, query=query)
        query_plan = QueryPlanner().plan(query or "dataset overview", semantic_map, None)
        facts = self._compute(
            df,
            query=query,
            target_column=target_column,
            task_type=task_type,
            run_predictions=run_predictions,
            run_xai=run_xai,
            session_id=session_id,
            filename=filename,
            semantic_map=semantic_map,
            query_plan=query_plan,
        )
        narration = self.narrator.narrate(facts, use_llm=use_llm, provider=provider)
        return self._merge_narration(facts, narration)

    async def run_full_analysis_async(
        self,
        df: pd.DataFrame,
        query: str | None = None,
        target_column: str | None = None,
        task_type: str | None = None,
        run_predictions: bool = True,
        run_xai: bool = True,
        session_id: str | None = None,
        filename: str | None = None,
        use_llm: bool = True,
        provider: str | None = None,
        semantic_map: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        semantic_map = semantic_map or await SemanticMapper().map_dataframe_async(df, filename=filename, query=query)
        query_plan = await QueryPlanner().plan_async(query or "dataset overview", semantic_map, None)
        facts = self._compute(
            df,
            query=query,
            target_column=target_column,
            task_type=task_type,
            run_predictions=run_predictions,
            run_xai=run_xai,
            session_id=session_id,
            filename=filename,
            semantic_map=semantic_map,
            query_plan=query_plan,
        )
        narration = await self.narrator.narrate_async(facts, use_llm=use_llm, provider=provider)
        return self._merge_narration(facts, narration)

    def _compute(
        self,
        df: pd.DataFrame,
        *,
        query: str | None,
        target_column: str | None,
        task_type: str | None,
        run_predictions: bool,
        run_xai: bool,
        session_id: str | None,
        filename: str | None,
        semantic_map: dict[str, Any] | None = None,
        query_plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if df is None or df.empty or len(df.columns) == 0:
            raise ValueError("Dataset is empty or has no columns")
        work = df.copy()
        dataset_profile = self.profile_dataset(work)
        if filename:
            dataset_profile["filename"] = filename
        semantic_map = semantic_map or SemanticMapper().map_dataframe(work, filename=filename, query=query)
        dataset_profile["semantic_map_dataset_type"] = semantic_map.get("dataset_type")
        query_plan = query_plan or QueryPlanner().plan(query or "dataset overview", semantic_map, dataset_profile)
        business_metrics = calculate_business_metrics(work, semantic_map)
        product_analysis = compute_product_trends(work, semantic_map, business_metrics)
        query_answer = answer_business_query(query_plan, business_metrics)
        food_analysis = _food_catalog_analysis(work, semantic_map)
        if food_analysis:
            product_analysis = _merge_food_analysis(product_analysis, food_analysis)
            query_answer = _food_query_answer(query, food_analysis) or query_answer
        data_quality = self.compute_data_quality(work)
        dataset_profile["data_quality_score"] = data_quality.get("data_quality_score")
        if isinstance(dataset_profile.get("quality"), dict):
            dataset_profile["quality"]["score"] = data_quality.get("data_quality_score")
        outliers = self.compute_outliers(work)
        eda = self.compute_eda(work, outliers=outliers)
        eda.setdefault(
            "missing_values",
            {
                "total_missing": data_quality.get("missing_cells", 0),
                "columns": data_quality.get("missing_values_by_column", {}),
            },
        )
        trends = self.compute_trends(work)
        correlations = self.compute_correlations(work)
        effective_target, effective_task, effective_run_predictions = _prediction_request(
            df=work,
            query_plan=query_plan,
            query=query,
            target_column=target_column,
            task_type=task_type,
            run_predictions=run_predictions,
        )
        prediction, trained_bundle, target_suggestions = self.train_model(
            work,
            query=query,
            target_column=effective_target,
            task_type=effective_task,
            run_predictions=effective_run_predictions,
        )
        xai = self.run_xai(trained_bundle, prediction, run_xai=run_xai and effective_run_predictions)
        report_mode = str(query_plan.get("report_mode") or "focused_answer_report")
        charts = _report_charts_for_query(
            query_plan=query_plan,
            business_metrics=business_metrics,
            product_analysis=product_analysis,
            generic_charts=self.generate_charts(work, trends, correlations, outliers, prediction, xai),
            report_mode=report_mode,
        )
        is_ai_khata = dataset_profile.get("dataset_type") in AI_KHATA_TYPES or semantic_map.get("dataset_type") in AI_KHATA_TYPES
        summary = business_summary(work) if is_ai_khata else {}
        if summary:
            sales_revenue_by_month = monthly_sales_revenue(work, period="M")
            if not sales_revenue_by_month and business_metrics.get("revenue_by_month"):
                sales_revenue_by_month = [
                    {"period": row["period"], "sales_revenue": row["revenue"]}
                    for row in business_metrics.get("revenue_by_month", [])
                ]
            trends["business_revenue_by_month"] = sales_revenue_by_month
            charts.append(
                {
                    "type": "line",
                    "title": "Sales revenue by month",
                    "x_key": "period",
                    "y_key": "sales_revenue",
                    "data": sales_revenue_by_month,
                    "filter": "Category == SALES",
                }
            )
        warnings = list(dict.fromkeys(
            data_quality.get("warnings", [])
            + business_metrics.get("data_limitations", [])
            + food_analysis.get("warnings", [])
            + prediction.get("limitations", [])
            + xai.get("warnings", [])
        ))
        automl_alias = self._legacy_automl_alias(prediction)
        return {
            "session_id": session_id,
            "filename": filename,
            "dataset_profile": dataset_profile,
            "column_roles": dataset_profile.get("column_roles", {}),
            "semantic_map": semantic_map,
            "business_summary": summary,
            "business_metrics": business_metrics,
            "product_analysis": product_analysis,
            "food_analysis": food_analysis,
            "query_plan": query_plan,
            "query_answer": query_answer,
            "kpis": query_answer.get("kpis") or _default_kpis(business_metrics),
            "data_quality": data_quality,
            "eda": eda,
            "trends": trends,
            "correlations": correlations,
            "outliers": outliers,
            "target_suggestions": target_suggestions,
            "prediction": prediction,
            "automl": automl_alias,
            "xai": xai,
            "charts": charts,
            "warnings": list(dict.fromkeys(warnings + product_analysis.get("warnings", []))),
            "report_mode": report_mode,
        }

    def _legacy_automl_alias(self, prediction: dict[str, Any]) -> dict[str, Any]:
        alias = dict(prediction)
        if alias.get("status") == "complete":
            alias["status"] = "success"
            alias["best_model"] = alias.get("selected_model")
            alias["metrics"] = alias.get("test_metrics") or alias.get("model_metrics") or {}
        return alias

    def _merge_narration(self, facts: dict[str, Any], narration: dict[str, Any]) -> dict[str, Any]:
        normalized_charts, chart_warnings = normalize_chart_specs(facts.get("charts") or [], limit=20)
        result = {
            **facts,
            "executive_summary": narration["executive_summary"],
            "key_insights": narration["key_insights"],
            "recommendations": list(dict.fromkeys(narration["recommendations"] + (facts.get("product_analysis") or {}).get("recommendations", []))),
            "warnings": list(dict.fromkeys(facts.get("warnings", []) + narration.get("warnings", []) + chart_warnings)),
            "next_questions": list(dict.fromkeys(narration["next_questions"] + (facts.get("product_analysis") or {}).get("next_questions", []))),
            "report_sections": narration.get("report_sections", {}),
            "narration": narration,
        }
        result["charts"] = normalized_charts
        return json_safe(result)

    def profile_dataset(self, df: pd.DataFrame) -> dict[str, Any]:
        return profile_dataframe(df)

    def compute_data_quality(self, df: pd.DataFrame) -> dict[str, Any]:
        return compute_data_quality(df)

    def compute_eda(self, df: pd.DataFrame, outliers: dict[str, Any] | None = None) -> dict[str, Any]:
        return compute_eda(df, outliers=outliers)

    def compute_trends(self, df: pd.DataFrame) -> dict[str, Any]:
        return compute_trends(df)

    def compute_correlations(self, df: pd.DataFrame) -> dict[str, Any]:
        return compute_correlations(df)

    def compute_outliers(self, df: pd.DataFrame) -> dict[str, Any]:
        return compute_outliers(df)

    def train_model(
        self,
        df: pd.DataFrame,
        *,
        query: str | None,
        target_column: str | None,
        task_type: str | None,
        run_predictions: bool,
    ):
        return train_prediction(
            df,
            query=query,
            target_column=target_column,
            task_type=task_type,
            run_predictions=run_predictions,
        )

    def run_xai(self, trained_bundle: Any, prediction: dict[str, Any], run_xai: bool = True) -> dict[str, Any]:
        if not SHAP_AVAILABLE and prediction.get("status") == "complete":
            importance = prediction.get("feature_importance", [])
            if not importance:
                return {
                    "status": "limited",
                    "method": None,
                    "global_feature_importance": [],
                    "top_features": [],
                    "local_explanations": [],
                    "plain_english_explanation": "XAI could not be generated because the model did not expose valid feature importance.",
                    "warnings": ["Feature importance was unavailable."],
                }
            warnings = ["SHAP unavailable; used feature importance fallback."]
            warnings.extend(str(item) for item in prediction.get("limitations", []) if "leakage" in str(item).lower())
            return {
                "status": "fallback",
                "method": "feature_importance",
                "global_feature_importance": importance,
                "top_features": [item["feature"] for item in importance[:5]],
                "local_explanations": [],
                "plain_english_explanation": (
                    "Method used: feature importance fallback. "
                    "SHAP was unavailable, so model feature importance was used. "
                    f"Top features: {', '.join(item['feature'] for item in importance[:5])}."
                ),
                "warnings": list(dict.fromkeys(warnings)),
            }
        return explain_model(trained_bundle, prediction, run_xai=run_xai)

    def generate_charts(
        self,
        df: pd.DataFrame,
        trends: dict[str, Any],
        correlations: dict[str, Any],
        outliers: dict[str, Any],
        prediction: dict[str, Any],
        xai: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return build_chart_specs(df, trends, correlations, outliers, prediction, xai)


def _normalize_charts(charts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized, _warnings = normalize_chart_specs(charts, limit=20)
    return normalized


def _food_catalog_analysis(df: pd.DataFrame, semantic_map: dict[str, Any]) -> dict[str, Any]:
    if semantic_map.get("dataset_type") != "food_dataset":
        return {}
    columns = {str(column).lower(): str(column) for column in df.columns}
    frequency_specs = [
        ("food_name", "Most frequent food item", "food_name"),
        ("category", "Most common category", "category"),
        ("cuisine", "Most common cuisine", "cuisine"),
        ("main_ingredient", "Most common main ingredient", "main_ingredient"),
        ("spice_level", "Spice level distribution", "spice_level"),
    ]
    charts: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    insights: list[str] = []
    for lookup, title, key in frequency_specs:
        column = columns.get(lookup)
        if not column:
            continue
        rows = _frequency_rows(df, column, key)
        if not rows:
            continue
        charts.append({"type": "bar", "title": title, "x_key": key, "y_key": "count", "data": rows[:12]})
        tables.append({"title": title, "columns": [key, "count"], "rows": rows[:12]})
        leader = rows[0]
        insights.append(f"{title}: {leader[key]} appears {leader['count']} rows.")

    calories_col = columns.get("calories")
    calories_stats: dict[str, Any] = {}
    if calories_col:
        series = pd.to_numeric(df[calories_col], errors="coerce").dropna()
        if not series.empty:
            calories_stats = {
                "min": int(series.min()) if float(series.min()).is_integer() else round(float(series.min()), 2),
                "max": int(series.max()) if float(series.max()).is_integer() else round(float(series.max()), 2),
                "mean": round(float(series.mean()), 2),
                "median": round(float(series.median()), 2),
            }
            insights.append(
                "Calories range from "
                f"{calories_stats['min']} to {calories_stats['max']}, with mean {calories_stats['mean']} "
                f"and median {calories_stats['median']}."
            )

    limitation = (
        "This dataset does not contain sales, revenue, profit, quantity, order date, or transaction columns. "
        "Therefore revenue analysis, most-sold product analysis, sales trends, and profit analysis cannot be calculated."
    )
    return {
        "dataset_kind": "food_classification_catalog",
        "calories_stats": calories_stats,
        "charts": charts,
        "tables": tables,
        "insights": insights,
        "warnings": [limitation],
        "recommendations": [
            "Use frequency analysis for catalog composition, not sales performance.",
            "Collect order quantity, revenue, cost, and timestamps before asking sales or profit questions.",
            "Validate any category model on external food items before trusting perfect accuracy.",
        ],
        "next_questions": [
            "Which cuisines have the highest average calories?",
            "How does spice level vary by cuisine or main ingredient?",
            "Which categories are duplicated or overly deterministic?",
        ],
    }


def _merge_food_analysis(product_analysis: dict[str, Any], food_analysis: dict[str, Any]) -> dict[str, Any]:
    merged = dict(product_analysis)
    merged["charts"] = [*food_analysis.get("charts", []), *product_analysis.get("charts", [])]
    merged["tables"] = [*food_analysis.get("tables", []), *product_analysis.get("tables", [])]
    merged["insights"] = [*food_analysis.get("insights", []), *product_analysis.get("insights", [])]
    merged["recommendations"] = [*food_analysis.get("recommendations", []), *product_analysis.get("recommendations", [])]
    merged["next_questions"] = [*food_analysis.get("next_questions", []), *product_analysis.get("next_questions", [])]
    merged["warnings"] = [*food_analysis.get("warnings", []), *product_analysis.get("warnings", [])]
    return {key: list(dict.fromkeys(value)) if isinstance(value, list) and all(isinstance(item, str) for item in value) else value for key, value in merged.items()}


def _food_query_answer(query: str | None, food_analysis: dict[str, Any]) -> dict[str, Any] | None:
    q = (query or "").lower()
    if not q or not any(term in q for term in ["most sold", "best selling", "top selling", "sold product", "sales", "revenue", "profit"]):
        return None
    tables = [table for table in food_analysis.get("tables", []) if table.get("title") == "Most frequent food item"]
    charts = [chart for chart in food_analysis.get("charts", []) if chart.get("title") == "Most frequent food item"]
    return {
        "intent": "food_frequency_fallback",
        "answer": (
            "This dataset does not contain sales or quantity columns, so I cannot calculate the most sold product. "
            "I can show the most frequent food item instead."
        ),
        "tables": tables,
        "charts": charts,
        "warnings": food_analysis.get("warnings", []),
        "follow_up_ideas": [
            "Show the most common category.",
            "Show cuisine distribution.",
            "Show calories distribution.",
        ],
    }


def _frequency_rows(df: pd.DataFrame, column: str, key: str) -> list[dict[str, Any]]:
    counts = df[column].astype(str).str.strip().replace("", pd.NA).dropna().value_counts().head(20)
    return [{key: str(label), "count": int(count)} for label, count in counts.items()]


def _prediction_request(
    *,
    df: pd.DataFrame,
    query_plan: dict[str, Any],
    query: str | None,
    target_column: str | None,
    task_type: str | None,
    run_predictions: bool,
) -> tuple[str | None, str | None, bool]:
    if target_column or task_type:
        return target_column, task_type, run_predictions
    if not run_predictions:
        return None, None, False
    intent = str(query_plan.get("intent") or "")
    metric = str(query_plan.get("metric") or "revenue")
    report_mode = str(query_plan.get("report_mode") or "focused_answer_report")
    if intent == "prediction":
        if metric == "profit":
            target = _first_existing_column(df, ("profit", "total_profit", "net_profit"))
            return target, "regression", bool(target)
        if metric == "quantity":
            target = _first_existing_column(df, ("quantity", "total_quantity"))
            return target, "regression", bool(target)
        if "category" in (query or "").lower():
            target = _first_existing_column(df, ("category", "subcategory"))
            return target, "classification", bool(target)
        target = _first_existing_column(df, ("total_sales", "revenue", "sales", "net_sales"))
        return target, "regression", bool(target)
    if report_mode == "full_analysis_report" or intent == "full_report":
        return None, None, True
    else:
        return None, None, False


def _default_kpis(business_metrics: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"label": "Total Sales", "value": business_metrics.get("total_revenue")},
        {"label": "Total Quantity", "value": business_metrics.get("total_quantity")},
        {"label": "Total Profit", "value": business_metrics.get("total_profit")},
        {"label": "Gross Margin", "value": None if business_metrics.get("gross_margin") is None else f"{business_metrics.get('gross_margin')}%"},
        {"label": "Transactions", "value": business_metrics.get("transaction_count")},
    ]


def _report_charts_for_query(
    *,
    query_plan: dict[str, Any],
    business_metrics: dict[str, Any],
    product_analysis: dict[str, Any],
    generic_charts: list[dict[str, Any]],
    report_mode: str,
) -> list[dict[str, Any]]:
    intent = str(query_plan.get("intent") or "dataset_overview")
    product_charts = list(product_analysis.get("charts") or [])
    fallback_charts = [*product_charts, *generic_charts]
    if intent == "total_sales":
        return [
            _line_chart("Sales by month", business_metrics.get("revenue_by_month") or [], "period", "revenue"),
            _bar_chart("Sales by category", business_metrics.get("revenue_by_category") or [], "category", "revenue"),
            _bar_chart("Sales by region", business_metrics.get("top_regions") or [], "region", "revenue"),
        ]
    if intent in {"revenue_by_month", "revenue_trend"}:
        return [_line_chart("Revenue by month", business_metrics.get("revenue_by_month") or [], "period", "revenue")]
    if intent in {"top_product", "top_products"}:
        focused_charts = [
            _bar_chart("Top products by revenue", business_metrics.get("top_products") or [], "product", "revenue"),
            _bar_chart("Top products by quantity", business_metrics.get("top_products_by_quantity") or [], "product", "quantity"),
        ]
        if any(chart.get("data") for chart in focused_charts):
            return focused_charts
        return fallback_charts
    if intent == "category_performance":
        return [_bar_chart("Category revenue", business_metrics.get("top_categories") or [], "category", "revenue")]
    if intent == "region_performance":
        return [_bar_chart("Region revenue", business_metrics.get("top_regions") or [], "region", "revenue")]
    if intent in {"profit_summary", "dataset_overview"} and report_mode != "full_analysis_report":
        return []
    return fallback_charts


def _bar_chart(title: str, data: list[dict[str, Any]], x_key: str, y_key: str) -> dict[str, Any]:
    return {"type": "bar", "title": title, "x_key": x_key, "y_key": y_key, "data": data}


def _line_chart(title: str, data: list[dict[str, Any]], x_key: str, y_key: str) -> dict[str, Any]:
    return {"type": "line", "title": title, "x_key": x_key, "y_key": y_key, "data": data}


def _first_existing_column(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    by_normalized = {str(column).lower(): str(column) for column in df.columns}
    for candidate in candidates:
        match = by_normalized.get(candidate.lower())
        if match:
            return match
    return None


__all__ = ["AnalysisPipeline", "create_session_id", "persist_dataframe_for_session"]
