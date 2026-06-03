"""Agent 1: Data Understanding Agent.

Analyses a DataFrame to understand its structure, columns, quality,
semantic meaning, and feasibility of user requests.

Pure Python — no LLM needed. Uses existing profiler, classifier,
and target inference services.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class DataUnderstandingAgent:
    """Builds a structured understanding of a dataset for Agent 2.

    Returns a dictionary with:
      - dataset_summary: basic shape, types
      - detected_columns: semantic roles (date, revenue, product, etc.)
      - data_quality: missing values, duplicates, outliers
      - possible_tasks: list of analysis types this dataset supports
      - missing_requirements: what's missing for the user's question
      - analysis_plan: recommended analysis steps
    """

    def understand(self, df: pd.DataFrame, prompt: str) -> dict[str, Any]:
        """Run full understanding pipeline.

        Args:
            df: The loaded pandas DataFrame.
            prompt: User's natural language question.

        Returns:
            Structured understanding dictionary.
        """
        summary = self._build_summary(df)
        detected = self._detect_columns(df)
        quality = self._assess_quality(df)
        possible_tasks = self._determine_possible_tasks(detected, df)
        missing = self._check_requirements(prompt, detected, df)
        plan = self._build_analysis_plan(prompt, detected, df)

        return {
            "dataset_summary": summary,
            "detected_columns": detected,
            "data_quality": quality,
            "possible_tasks": possible_tasks,
            "missing_requirements": missing,
            "analysis_plan": plan,
        }

    # ── Internal methods ──────────────────────────────────────────

    def _build_summary(self, df: pd.DataFrame) -> dict[str, Any]:
        """Basic shape and type summary."""
        return {
            "rows": len(df),
            "columns": len(df.columns),
            "column_names": list(df.columns),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "memory_mb": round(df.memory_usage(deep=True).sum() / 1024 / 1024, 2),
        }

    def _detect_columns(self, df: pd.DataFrame) -> dict[str, list[str]]:
        """Detect semantic roles of columns by name and content patterns."""
        date_cols: list[str] = []
        revenue_cols: list[str] = []
        sales_cols: list[str] = []
        quantity_cols: list[str] = []
        product_cols: list[str] = []
        customer_cols: list[str] = []
        category_cols: list[str] = []
        id_cols: list[str] = []
        numeric_cols: list[str] = []
        text_cols: list[str] = []
        target_candidates: list[str] = []

        for col in df.columns:
            col_lower = col.lower().strip()
            dtype = df[col].dtype

            # Date columns
            if pd.api.types.is_datetime64_any_dtype(dtype):
                date_cols.append(col)
            elif any(kw in col_lower for kw in ("date", "time", "timestamp", "created", "updated", "year", "month")):
                try:
                    pd.to_datetime(df[col], errors="raise", infer_datetime_format=True)
                    date_cols.append(col)
                except Exception:
                    if any(kw in col_lower for kw in ("year", "month")):
                        date_cols.append(col)

            # Revenue / monetary columns
            if any(kw in col_lower for kw in ("revenue", "sales", "amount", "total", "price", "cost", "profit", "income", "spend")):
                if pd.api.types.is_numeric_dtype(dtype):
                    revenue_cols.append(col)

            # Quantity columns
            if any(kw in col_lower for kw in ("quantity", "qty", "count", "units", "volume")):
                if pd.api.types.is_numeric_dtype(dtype):
                    quantity_cols.append(col)
                    sales_cols.append(col)

            # Product columns
            if any(kw in col_lower for kw in ("product", "item", "sku", "goods", "service")):
                product_cols.append(col)

            # Customer columns
            if any(kw in col_lower for kw in ("customer", "client", "user", "buyer", "account")):
                customer_cols.append(col)

            # Category columns
            if any(kw in col_lower for kw in ("category", "type", "group", "segment", "class", "department", "region", "area", "channel")):
                category_cols.append(col)

            # ID columns
            if any(kw in col_lower for kw in ("id", "key", "code", "number")) and col_lower.endswith(("id", "key", "code")):
                id_cols.append(col)

            # Numeric columns (for ML)
            if pd.api.types.is_numeric_dtype(dtype):
                numeric_cols.append(col)
                if col not in id_cols:
                    target_candidates.append(col)

            # Text columns
            if dtype == "object" and col not in id_cols:
                text_cols.append(col)

        # Add sales_cols from revenue if empty
        if not sales_cols and revenue_cols:
            sales_cols = revenue_cols.copy()

        return {
            "date_columns": date_cols,
            "revenue_columns": revenue_cols,
            "sales_columns": sales_cols,
            "quantity_columns": quantity_cols,
            "product_columns": product_cols,
            "customer_columns": customer_cols,
            "category_columns": category_cols,
            "id_columns": id_cols,
            "numeric_columns": numeric_cols,
            "text_columns": text_cols,
            "target_candidates": target_candidates,
        }

    def _assess_quality(self, df: pd.DataFrame) -> dict[str, Any]:
        """Assess data quality: missing values, duplicates, outliers."""
        missing = {}
        for col in df.columns:
            miss_count = int(df[col].isnull().sum())
            if miss_count > 0:
                missing[col] = {
                    "count": miss_count,
                    "percent": round(miss_count / len(df) * 100, 1),
                }

        duplicates = int(df.duplicated().sum())

        # Simple outlier detection on numeric columns (IQR method)
        outlier_cols = {}
        for col in df.select_dtypes(include=[np.number]).columns:
            q1 = df[col].quantile(0.25)
            q3 = df[col].quantile(0.75)
            iqr = q3 - q1
            if iqr > 0:
                outlier_count = int(((df[col] < q1 - 1.5 * iqr) | (df[col] > q3 + 1.5 * iqr)).sum())
                if outlier_count > 0:
                    outlier_cols[col] = outlier_count

        return {
            "missing_values": missing,
            "total_missing": sum(m["count"] for m in missing.values()),
            "duplicate_rows": duplicates,
            "outlier_columns": outlier_cols,
            "completeness_percent": round(
                (1 - df.isnull().sum().sum() / (len(df) * len(df.columns))) * 100, 1
            ),
        }

    def _determine_possible_tasks(self, detected: dict, df: pd.DataFrame) -> list[str]:
        """Determine what analysis tasks this dataset supports."""
        tasks = ["Summarize this dataset", "Show data quality issues"]

        if detected["revenue_columns"] or detected["numeric_columns"]:
            tasks.append("Find highest/lowest values")

        if detected["date_columns"] and detected["revenue_columns"]:
            tasks.append("Show trends over time")

        if detected["product_columns"]:
            tasks.append("Analyze top products")

        if detected["customer_columns"]:
            tasks.append("Analyze top customers")

        if detected["category_columns"]:
            tasks.append("Compare by category")

        if len(detected["numeric_columns"]) >= 2:
            tasks.append("Find correlations")
            tasks.append("Run prediction model")

        if detected["date_columns"] and detected["numeric_columns"]:
            tasks.append("Predict future values")

        if detected["category_columns"] and detected["numeric_columns"]:
            tasks.append("Segment analysis")

        return tasks

    def _check_requirements(self, prompt: str, detected: dict, df: pd.DataFrame) -> list[str]:
        """Check if the dataset supports the user's request."""
        prompt_lower = prompt.lower()
        missing = []

        # Trend analysis needs date columns
        if any(kw in prompt_lower for kw in ("trend", "over time", "monthly", "weekly", "yearly", "by month", "by year")):
            if not detected["date_columns"]:
                missing.append("date/time column for trend analysis")

        # Revenue analysis needs numeric columns
        if any(kw in prompt_lower for kw in ("revenue", "sales", "income", "profit")):
            if not detected["revenue_columns"] and not detected["numeric_columns"]:
                missing.append("numeric column for revenue analysis")

        # Product analysis needs product columns
        if any(kw in prompt_lower for kw in ("product", "item", "sku")):
            if not detected["product_columns"]:
                missing.append("product/item column")

        # Prediction needs enough rows
        if any(kw in prompt_lower for kw in ("predict", "forecast", "estimate")):
            if len(df) < 20:
                missing.append(f"at least 20 rows for prediction (have {len(df)})")
            if len(detected["numeric_columns"]) < 2:
                missing.append("at least 2 numeric columns for prediction")

        return missing

    def _build_analysis_plan(self, prompt: str, detected: dict, df: pd.DataFrame) -> list[str]:
        """Suggest analysis steps based on the prompt and data."""
        prompt_lower = prompt.lower()
        plan = []

        if any(kw in prompt_lower for kw in ("top", "best", "highest", "lowest", "most", "least", "biggest", "smallest")):
            plan.append("ranking_analysis")
        if any(kw in prompt_lower for kw in ("trend", "over time", "monthly", "by month", "by year", "weekly")):
            plan.append("trend_analysis")
        if any(kw in prompt_lower for kw in ("predict", "forecast", "estimate", "next")):
            plan.append("prediction")
        if any(kw in prompt_lower for kw in ("segment", "cluster", "group")):
            plan.append("segmentation")
        if any(kw in prompt_lower for kw in ("correlat", "relationship", "affect")):
            plan.append("correlation")
        if any(kw in prompt_lower for kw in ("clean", "quality", "missing", "issue", "problem")):
            plan.append("data_quality")
        if any(kw in prompt_lower for kw in ("summary", "overview", "describe", "tell me about")):
            plan.append("summary")
        if any(kw in prompt_lower for kw in ("compare", "versus", "vs", "difference")):
            plan.append("comparison")
        if any(kw in prompt_lower for kw in ("recommend", "suggest", "advice", "should", "focus", "improve")):
            plan.append("recommendation")

        # Default to summary if no plan determined
        if not plan:
            plan.append("general_analysis")

        return plan
