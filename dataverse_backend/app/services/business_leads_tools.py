"""Business-leads dataframe tools."""
from __future__ import annotations

from typing import Any

import pandas as pd

from .data_profiler import profile_dataframe


def _range_score(value: Any) -> int:
    text = str(value or "").lower()
    if any(token in text for token in ["100m", "201-500", "500", "enterprise"]):
        return 4
    if any(token in text for token in ["50m", "51-200", "200"]):
        return 3
    if any(token in text for token in ["10m", "11-50", "50"]):
        return 2
    if text.strip():
        return 1
    return 0


class BusinessLeadsTools:
    def __init__(self, df: pd.DataFrame, filename: str | None = None):
        self.df = df.copy()
        self.filename = filename
        self.profile = profile_dataframe(self.df)
        self.semantic = self.profile.get("semantic_columns", {})

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

    def follow_up_suggestions(self) -> list[str]:
        from .recommendation_engine import follow_up_suggestions

        return follow_up_suggestions("business_leads", self.semantic)

    def dataset_overview(self) -> dict[str, Any]:
        website_col = self.semantic.get("website")
        missing_websites = self._missing_website_count(website_col)
        answer = (
            f"This business leads dataset has {len(self.df)} business records across {len(self.df.columns)} columns. "
            f"It includes lead attributes such as country, industry, employee range, revenue range, and website availability. "
            f"{missing_websites} records are missing website values."
        )
        rows = [
            {"metric": "Business records", "value": int(len(self.df))},
            {"metric": "Columns", "value": int(len(self.df.columns))},
            {"metric": "Missing websites", "value": missing_websites},
        ]
        return self._finish({
            "intent": "dataset_overview",
            "dataset_type": "business_leads",
            "answer": answer,
            "method": "Profiled business lead roles and counted website coverage.",
            "tables": [self._table(["metric", "value"], rows, "Business leads overview")],
            "charts": [],
            "warnings": [],
            "recommendations": [],
            "profile": self.profile,
            "suggestions": self.follow_up_suggestions(),
        })

    def _missing_website_count(self, website_col: str | None) -> int:
        if not website_col or website_col not in self.df.columns:
            return 0
        values = self.df[website_col]
        return int(values.isna().sum() + (values.fillna("").astype(str).str.strip() == "").sum())

    def _distribution(self, role: str, title: str) -> dict[str, Any]:
        column = self.semantic.get(role)
        rows: list[dict[str, Any]] = []
        if column in self.df.columns:
            counts = self.df[column].fillna("Unknown").astype(str).value_counts().head(20)
            rows = [{"value": str(value), "businesses": int(count)} for value, count in counts.items()]
        return self._finish({
            "intent": f"{role}_distribution",
            "dataset_type": "business_leads",
            "answer": f"{rows[0]['value']} has the most businesses ({rows[0]['businesses']})." if rows else f"No {role} column was available.",
            "method": f"Counted business leads by detected {role} column.",
            "tables": [self._table(["value", "businesses"], rows, title)],
            "charts": [self._chart("bar", title, rows, "value", "businesses")] if rows else [],
            "warnings": [] if rows else [f"Missing {role} column."],
            "recommendations": [],
            "profile": self.profile,
        })

    def country_distribution(self) -> dict[str, Any]:
        return self._distribution("country", "Country distribution")

    def industry_distribution(self) -> dict[str, Any]:
        return self._distribution("industry", "Industry distribution")

    def employee_range_distribution(self) -> dict[str, Any]:
        return self._distribution("employee_range", "Employee range distribution")

    def revenue_range_distribution(self) -> dict[str, Any]:
        return self._distribution("revenue_range", "Revenue range distribution")

    def missing_value_report(self) -> dict[str, Any]:
        rows = [{"column": str(column), "missing": int(self.df[column].isna().sum())} for column in self.df.columns]
        return self._finish({
            "intent": "missing_values",
            "dataset_type": "business_leads",
            "answer": f"Calculated missing values for {len(rows)} lead fields.",
            "method": "Counted null values per column.",
            "tables": [self._table(["column", "missing"], rows, "Missing lead fields")],
            "charts": [],
            "warnings": [],
            "recommendations": [],
            "profile": self.profile,
        })

    def no_website_analysis(self) -> dict[str, Any]:
        website_col = self.semantic.get("website")
        count = self._missing_website_count(website_col)
        rows = [{"metric": "missing_websites", "businesses": count}]
        return self._finish({
            "intent": "no_website_analysis",
            "dataset_type": "business_leads",
            "answer": f"{count} businesses are missing websites.",
            "method": "Counted empty or null website values.",
            "tables": [self._table(["metric", "businesses"], rows, "No website opportunities")],
            "charts": [self._chart("bar", "No website opportunities", rows, "metric", "businesses")],
            "warnings": [],
            "recommendations": ["Prioritize missing-website businesses for website or digital presence outreach."],
            "profile": self.profile,
        })

    def high_value_leads(self, limit: int = 10) -> dict[str, Any]:
        name_col = self.semantic.get("business_name") or "business_name"
        industry_col = self.semantic.get("industry")
        country_col = self.semantic.get("country")
        employee_col = self.semantic.get("employee_range")
        revenue_col = self.semantic.get("revenue_range")
        rows = []
        for _, row in self.df.iterrows():
            score = _range_score(row.get(employee_col)) + (_range_score(row.get(revenue_col)) * 2)
            rows.append({
                "business_name": str(row.get(name_col, "Unknown")),
                "country": str(row.get(country_col, "")) if country_col else "",
                "industry": str(row.get(industry_col, "")) if industry_col else "",
                "lead_score": int(score),
            })
        rows.sort(key=lambda item: item["lead_score"], reverse=True)
        rows = rows[:limit]
        return self._finish({
            "intent": "high_value_leads",
            "dataset_type": "business_leads",
            "answer": f"{rows[0]['business_name']} looks like the highest-value lead." if rows else "No business leads were available.",
            "method": "Scored leads from employee range and yearly revenue range.",
            "tables": [self._table(["business_name", "country", "industry", "lead_score"], rows, "Lead scoring")],
            "charts": [self._chart("bar", "Lead scoring", rows, "business_name", "lead_score")] if rows else [],
            "warnings": [],
            "recommendations": ["Use lead score as a prioritization aid, then validate fit manually."],
            "profile": self.profile,
        })

    def outreach_recommendations(self, limit: int = 10) -> dict[str, Any]:
        result = self.high_value_leads(limit=limit)
        website_missing = self._missing_website_count(self.semantic.get("website"))
        industry_col = self.semantic.get("industry")
        top_industry = None
        if industry_col in self.df.columns:
            top_industry = str(self.df[industry_col].fillna("Unknown").astype(str).value_counts().idxmax())
        result["intent"] = "outreach_recommendations"
        result["answer"] = (
            f"Start with high-value leads and the {website_missing} businesses missing websites. "
            f"{top_industry or 'The leading industry'} is a strong segment for outreach."
        )
        result["recommendations"] = [
            "Prioritize high-score leads with missing websites for digital presence outreach.",
            f"Build an industry-specific pitch for {top_industry}." if top_industry else "Build industry-specific pitch variants.",
            "Validate phone/email/contact data before campaign launch.",
        ]
        return result
