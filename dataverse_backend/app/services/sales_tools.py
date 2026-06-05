"""Sales-specific deterministic dataframe tools."""
from __future__ import annotations

from typing import Any

import pandas as pd

from .analytics_tools import AnalyticsTools
from .data_profiler import profile_dataframe


class SalesTools:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.profile = profile_dataframe(self.df)
        self.semantic = self.profile.get("semantic_columns", {})
        self.generic = AnalyticsTools(self.df)

    def _table(self, columns: list[str], rows: list[dict[str, Any]], title: str) -> dict[str, Any]:
        return {"title": title, "columns": columns, "rows": rows}

    def _chart(self, chart_type: str, title: str, data: list[dict[str, Any]], x_key: str, y_key: str) -> dict[str, Any]:
        return {"type": chart_type, "title": title, "data": data, "x_key": x_key, "y_key": y_key}

    def _finish(self, result: dict[str, Any]) -> dict[str, Any]:
        if result.get("tables"):
            result["table"] = result["tables"][0]
        if result.get("charts"):
            result["chart"] = result["charts"][0]
        if result.get("warnings"):
            result["warning"] = result["warnings"][0]
        return result

    def top_products(self, limit: int = 10, ascending: bool = False) -> dict[str, Any]:
        result = self.generic.top_products(limit=limit, ascending=ascending)
        result["profile"] = self.profile
        return result

    def trending_products(self, limit: int = 10) -> dict[str, Any]:
        result = self.generic.trending_products(limit=limit)
        result["profile"] = self.profile
        return result

    def declining_products(self, limit: int = 10) -> dict[str, Any]:
        return self.top_products(limit=limit, ascending=True)

    def revenue_trend(self, period: str = "M") -> dict[str, Any]:
        date_col = self.semantic.get("date") or self.semantic.get("order_date")
        revenue_col = self.semantic.get("revenue") or self.semantic.get("sales_amount")
        rows: list[dict[str, Any]] = []
        if date_col and revenue_col:
            work = self.df[[date_col, revenue_col]].copy()
            work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
            work[revenue_col] = pd.to_numeric(work[revenue_col], errors="coerce")
            work = work.dropna(subset=[date_col, revenue_col])
            if not work.empty:
                work["_period"] = work[date_col].dt.to_period(period)
                grouped = work.groupby("_period")[revenue_col].sum().sort_index()
                rows = [{"period": str(index), str(revenue_col): round(float(value), 2)} for index, value in grouped.items()]
        result = {
            "intent": "revenue_trend",
            "dataset_type": "sales",
            "answer": f"Revenue is available across {len(rows)} periods." if rows else "No dated revenue rows were available.",
            "method": "Grouped the detected revenue column by calendar period.",
            "tables": [self._table(["period", str(revenue_col)], rows, "revenue trend")] if revenue_col else [],
            "charts": [self._chart("line", "Revenue trend", rows, "period", str(revenue_col))] if rows and revenue_col else [],
            "warnings": [] if rows else ["Missing valid date or revenue values."],
            "recommendations": [],
            "profile": self.profile,
        }
        return self._finish(result)

    def dimension_performance(self, role: str, limit: int = 10) -> dict[str, Any]:
        dimension_col = self.semantic.get(role)
        revenue_col = self.semantic.get("revenue") or self.semantic.get("sales_amount")
        rows: list[dict[str, Any]] = []
        if dimension_col and revenue_col:
            grouped = (
                self.df.assign(_revenue=pd.to_numeric(self.df[revenue_col], errors="coerce"))
                .dropna(subset=[dimension_col, "_revenue"])
                .groupby(dimension_col)["_revenue"]
                .sum()
                .sort_values(ascending=False)
                .head(limit)
            )
            rows = [{str(dimension_col): str(name), str(revenue_col): round(float(value), 2)} for name, value in grouped.items()]
        result = {
            "intent": f"{role}_performance",
            "dataset_type": "sales",
            "answer": f"{rows[0][str(dimension_col)]} performs best by {revenue_col}." if rows and dimension_col else f"No {role} performance rows were available.",
            "method": f"Grouped revenue by detected {role} column.",
            "tables": [self._table([str(dimension_col), str(revenue_col)], rows, f"{role.title()} performance")] if dimension_col and revenue_col else [],
            "charts": [self._chart("bar", f"{role.title()} performance", rows, str(dimension_col), str(revenue_col))] if rows and dimension_col and revenue_col else [],
            "warnings": [] if rows else [f"Missing {role} or revenue column."],
            "recommendations": [],
            "profile": self.profile,
        }
        return self._finish(result)

    def forecast(self) -> dict[str, Any]:
        result = self.revenue_trend()
        result["intent"] = "forecast"
        result["answer"] = "A simple forecast needs more history; review the revenue trend first."
        return result

    def recommendations(self) -> dict[str, Any]:
        top = self.top_products()
        top["intent"] = "sales_recommendations"
        top["recommendations"] = [
            "Prioritize the highest revenue products.",
            "Review declining products before discounting or restocking.",
            "Track monthly revenue and margin together before making inventory decisions.",
        ]
        return top

    def missing_value_report(self) -> dict[str, Any]:
        return self.generic.missing_value_report()

    def correlation_analysis(self) -> dict[str, Any]:
        return self.generic.correlation_analysis()

    def outlier_detection(self) -> dict[str, Any]:
        return self.generic.outlier_detection()
