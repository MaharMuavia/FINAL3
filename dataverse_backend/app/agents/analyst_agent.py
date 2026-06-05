"""AnalystAgent to run planning, Pandas computations, EDA, modeling, XAI, and narration."""
from __future__ import annotations

from typing import Any
import pandas as pd

from ..services.analysis_pipeline import AnalysisPipeline
from ..core.config import settings


class AnalystAgent:
    """Agent responsible for understanding the query, running computations, modeling, XAI, and report narration."""

    def __init__(self):
        self.pipeline = AnalysisPipeline()

    async def run_analysis(
        self,
        df: pd.DataFrame,
        session_id: str,
        query: str | None = None,
        target_column: str | None = None,
        task_type: str | None = None,
        run_predictions: bool = True,
        run_xai: bool = True,
        use_llm: bool = False,
        provider: str | None = None,
        semantic_map: dict[str, Any] | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:
        """Runs the deterministic analytical pipeline, with row count and prediction checks."""
        row_count = len(df)
        min_rows = settings.MIN_ROWS_FOR_PREDICTION

        # Run the standard pipeline first
        report = await self.pipeline.run_full_analysis_async(
            df=df,
            query=query,
            target_column=target_column,
            task_type=task_type,
            run_predictions=run_predictions,
            run_xai=run_xai,
            session_id=session_id,
            filename=filename,
            use_llm=use_llm,
            provider=provider,
            semantic_map=semantic_map,
        )

        # Enforce user-friendly prediction constraints if data is too small
        if row_count < min_rows:
            report["prediction"] = {
                "status": "skipped",
                "reason": f"Dataset has fewer than {min_rows} rows (found {row_count} rows). Prediction was skipped because reliable ML models require a minimum of {min_rows} rows to train and evaluate.",
                "required_columns_info": "To train a machine learning model, the dataset needs at least one target column (e.g., continuous numeric for regression like 'revenue', or categorical/binary for classification like 'churn') and one or more independent feature columns.",
                "upload_requirements": {
                    "minimum_rows": min_rows,
                    "target_column_needed": True,
                    "features_needed": "At least one numeric or low-cardinality categorical column distinct from the target.",
                },
                "limitations": [f"minimum rows >= {min_rows}"],
            }
            # Add to warnings list
            warning_msg = f"Prediction skipped: Dataset must have at least {min_rows} rows (currently has {row_count} rows)."
            if warning_msg not in report.get("warnings", []):
                report.setdefault("warnings", []).append(warning_msg)

            # Update final narrations/summary if the query specifically asked for ML
            query_lower = (query or "").lower()
            if query_lower and any(w in query_lower for w in ["predict", "forecast", "model", "classify"]):
                report["query_answer"] = {
                    "answer": f"I cannot build a predictive model because the dataset only has {row_count} rows. Reliable machine learning requires at least {min_rows} rows. However, I have compiled descriptive insights, trends, and correlations below.",
                    "facts": {},
                }
                report["executive_summary"] = (
                    f"Descriptive analytics succeeded. Prediction was skipped because the dataset contains only {row_count} rows (minimum required is {min_rows}). "
                    "Suggest uploading a larger dataset to enable predictive modeling."
                )

        return report
