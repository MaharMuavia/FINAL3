"""Generic dataframe analytics tools used by the legacy agent."""
from __future__ import annotations

from typing import Any

import pandas as pd

from .data_profiler import profile_dataframe


class AnalyticsTools:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.profile = profile_dataframe(self.df)

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

    def trending_products(self, limit: int = 10) -> dict[str, Any]:
        semantic = self.profile.get("semantic_columns", {})
        product_col = semantic.get("product")
        revenue_col = semantic.get("revenue") or semantic.get("sales_amount")
        date_col = semantic.get("date") or semantic.get("order_date")
        if not product_col or not revenue_col:
            return self._finish({
                "intent": "top_products",
                "answer": "I need product and revenue columns to rank products.",
                "method": "Checked semantic product and revenue roles before ranking.",
                "tables": [],
                "charts": [],
                "warnings": ["Missing product or revenue column."],
                "recommendations": [],
                "profile": self.profile,
            })
        if not date_col:
            result = self.top_products(limit=limit)
            result["warning"] = "No date column was available, so trending analysis fell back to top products."
            result["warnings"] = [result["warning"]]
            return result

        work = self.df[[product_col, revenue_col, date_col]].copy()
        work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
        work[revenue_col] = pd.to_numeric(work[revenue_col], errors="coerce")
        work = work.dropna(subset=[product_col, revenue_col, date_col])
        if work.empty:
            return self.top_products(limit=limit)
        periods = sorted(work[date_col].dt.to_period("M").dropna().unique())
        if len(periods) < 2:
            return self.top_products(limit=limit)
        recent_period = periods[-1]
        previous_period = periods[-2]
        recent = work[work[date_col].dt.to_period("M") == recent_period].groupby(product_col)[revenue_col].sum()
        previous = work[work[date_col].dt.to_period("M") == previous_period].groupby(product_col)[revenue_col].sum()
        products = sorted(set(recent.index) | set(previous.index))
        rows = []
        for product in products:
            recent_value = float(recent.get(product, 0))
            previous_value = float(previous.get(product, 0))
            growth_pct = ((recent_value - previous_value) / previous_value * 100) if previous_value else (100.0 if recent_value else 0.0)
            rows.append({
                str(product_col): str(product),
                "recent_revenue": round(recent_value, 2),
                "previous_revenue": round(previous_value, 2),
                "growth_pct": round(growth_pct, 1),
            })
        rows.sort(key=lambda row: row["growth_pct"], reverse=True)
        rows = rows[:limit]
        result = {
            "intent": "trending_products",
            "answer": f"{rows[0][str(product_col)]} is trending fastest with {rows[0]['growth_pct']}% revenue growth." if rows else "No product trend rows were available.",
            "method": "Compared product revenue in the latest month with the previous month.",
            "tables": [self._table([str(product_col), "recent_revenue", "previous_revenue", "growth_pct"], rows, "Trending products")],
            "charts": [self._chart("bar", "Trending products", rows, str(product_col), "growth_pct")],
            "warnings": [],
            "recommendations": [],
            "profile": self.profile,
        }
        return self._finish(result)

    def top_products(self, limit: int = 10, ascending: bool = False) -> dict[str, Any]:
        semantic = self.profile.get("semantic_columns", {})
        product_col = semantic.get("product")
        revenue_col = semantic.get("revenue") or semantic.get("sales_amount")
        if not product_col or not revenue_col:
            rows: list[dict[str, Any]] = []
        else:
            grouped = (
                self.df.assign(_revenue=pd.to_numeric(self.df[revenue_col], errors="coerce"))
                .dropna(subset=[product_col, "_revenue"])
                .groupby(product_col)["_revenue"]
                .sum()
                .sort_values(ascending=ascending)
                .head(limit)
            )
            rows = [{str(product_col): str(name), str(revenue_col): round(float(value), 2)} for name, value in grouped.items()]
        result = {
            "intent": "top_products",
            "answer": f"{rows[0][str(product_col)]} is the top product by {revenue_col}." if rows and product_col else "No product revenue rows were available.",
            "method": "Calculated product totals by summing the detected revenue column.",
            "tables": [self._table([str(product_col), str(revenue_col)], rows, "Top products")] if product_col and revenue_col else [],
            "charts": [self._chart("bar", "Top products", rows, str(product_col), str(revenue_col))] if rows and product_col and revenue_col else [],
            "warnings": [],
            "recommendations": [],
            "profile": self.profile,
        }
        return self._finish(result)

    def missing_value_report(self) -> dict[str, Any]:
        rows = [
            {"column": str(column), "missing": int(self.df[column].isna().sum())}
            for column in self.df.columns
        ]
        return self._finish({
            "intent": "missing_values",
            "answer": f"Calculated missing values for {len(rows)} columns.",
            "method": "Counted null values per column.",
            "tables": [self._table(["column", "missing"], rows, "Missing values")],
            "charts": [self._chart("bar", "Missing values", rows, "column", "missing")],
            "warnings": [],
            "recommendations": [],
            "profile": self.profile,
        })

    def correlation_analysis(self) -> dict[str, Any]:
        numeric = self.df.select_dtypes(include="number")
        rows: list[dict[str, Any]] = []
        if numeric.shape[1] >= 2:
            corr = numeric.corr(numeric_only=True)
            for i, col_a in enumerate(corr.columns):
                for col_b in corr.columns[i + 1:]:
                    rows.append({"column_a": str(col_a), "column_b": str(col_b), "correlation": round(float(corr.loc[col_a, col_b]), 4)})
            rows.sort(key=lambda row: abs(row["correlation"]), reverse=True)
        return self._finish({
            "intent": "correlation",
            "answer": f"Found {len(rows)} numeric correlation pairs.",
            "method": "Computed Pearson correlations across numeric columns.",
            "tables": [self._table(["column_a", "column_b", "correlation"], rows[:20], "Correlations")],
            "charts": [],
            "warnings": [] if rows else ["At least two numeric columns are required for correlation."],
            "recommendations": [],
            "profile": self.profile,
        })

    def outlier_detection(self) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for column in self.df.select_dtypes(include="number").columns:
            values = pd.to_numeric(self.df[column], errors="coerce").dropna()
            if values.empty:
                continue
            q1 = values.quantile(0.25)
            q3 = values.quantile(0.75)
            iqr = q3 - q1
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            rows.append({"column": str(column), "outliers": int(((values < lower) | (values > upper)).sum())})
        return self._finish({
            "intent": "outliers",
            "answer": f"Checked outliers for {len(rows)} numeric columns.",
            "method": "Used the 1.5 IQR rule per numeric column.",
            "tables": [self._table(["column", "outliers"], rows, "Outliers")],
            "charts": [self._chart("bar", "Outliers", rows, "column", "outliers")] if rows else [],
            "warnings": [],
            "recommendations": [],
            "profile": self.profile,
        })
