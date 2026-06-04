"""Clean deterministic AI data analyst pipeline."""
from __future__ import annotations

from typing import Any

import pandas as pd

from .data_profiler import profile_dataframe
from .ai_khata import AI_KHATA_TYPES, business_summary, monthly_sales_revenue
from .business_metrics import answer_business_query, calculate_business_metrics
from .data_quality import (
    build_chart_specs,
    compute_correlations,
    compute_data_quality,
    compute_eda,
    compute_outliers,
    compute_trends,
    json_safe,
)
from .modeling import train_prediction
from .query_planner import QueryPlanner
from .report_narrator import ReportNarrator
from .semantic_mapper import SemanticMapper
from .session_store import create_session_id, persist_dataframe_for_session
from .xai import explain_model

SHAP_AVAILABLE = True


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
        query_answer = answer_business_query(query_plan, business_metrics)
        data_quality = self.compute_data_quality(work)
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
        prediction, trained_bundle, target_suggestions = self.train_model(
            work,
            query=query,
            target_column=target_column,
            task_type=task_type,
            run_predictions=run_predictions,
        )
        xai = self.run_xai(trained_bundle, prediction, run_xai=run_xai)
        charts = self.generate_charts(work, trends, correlations, outliers, prediction, xai)
        summary = business_summary(work) if dataset_profile.get("dataset_type") in AI_KHATA_TYPES else {
            "total_revenue": business_metrics.get("total_revenue"),
            "total_quantity": business_metrics.get("total_quantity"),
            "total_cost": business_metrics.get("total_cost"),
            "total_expenses": business_metrics.get("total_expenses"),
            "total_profit": business_metrics.get("total_profit"),
            "gross_margin": business_metrics.get("gross_margin"),
            "average_order_value": business_metrics.get("average_order_value"),
            "transaction_count": business_metrics.get("transaction_count"),
            "sales_transaction_count": business_metrics.get("sales_transaction_count"),
        }
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
                    "x": "period",
                    "y": "sales_revenue",
                    "data": sales_revenue_by_month,
                    "filter": "Category == SALES",
                }
            )
        warnings = list(dict.fromkeys(data_quality.get("warnings", []) + business_metrics.get("data_limitations", []) + prediction.get("limitations", []) + xai.get("warnings", [])))
        automl_alias = self._legacy_automl_alias(prediction)
        return {
            "session_id": session_id,
            "filename": filename,
            "dataset_profile": dataset_profile,
            "column_roles": dataset_profile.get("column_roles", {}),
            "semantic_map": semantic_map,
            "business_summary": summary,
            "business_metrics": business_metrics,
            "query_plan": query_plan,
            "query_answer": query_answer,
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
            "warnings": warnings,
        }

    def _legacy_automl_alias(self, prediction: dict[str, Any]) -> dict[str, Any]:
        alias = dict(prediction)
        if alias.get("status") == "complete":
            alias["status"] = "success"
            alias["best_model"] = alias.get("selected_model")
            alias["metrics"] = alias.get("test_metrics") or alias.get("model_metrics") or {}
        return alias

    def _merge_narration(self, facts: dict[str, Any], narration: dict[str, Any]) -> dict[str, Any]:
        result = {
            **facts,
            "executive_summary": narration["executive_summary"],
            "key_insights": narration["key_insights"],
            "recommendations": narration["recommendations"],
            "warnings": list(dict.fromkeys(facts.get("warnings", []) + narration.get("warnings", []))),
            "next_questions": narration["next_questions"],
            "report_sections": narration.get("report_sections", {}),
            "narration": narration,
        }
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
            return {
                "status": "fallback",
                "method": "feature_importance",
                "global_feature_importance": prediction.get("feature_importance", []),
                "top_features": [item["feature"] for item in prediction.get("feature_importance", [])[:5]],
                "local_explanations": [],
                "plain_english_explanation": "SHAP was unavailable, so feature importance was used as the explanation fallback.",
                "warnings": ["SHAP unavailable; used feature importance fallback."],
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


__all__ = ["AnalysisPipeline", "create_session_id", "persist_dataframe_for_session"]
