"""Pandas analytics for business leads and prospecting datasets."""
from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from .data_profiler import profile_dataframe


def _safe_text(value: Any, default: str = "Unknown") -> str:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return default
    return str(value)


def _range_midpoint(value: Any) -> float:
    """Approximate employee/revenue range strings for ranking only."""
    if value is None or pd.isna(value):
        return 0.0
    text = str(value).lower().replace(",", "").strip()
    if not text:
        return 0.0

    multipliers = {"k": 1_000, "m": 1_000_000, "million": 1_000_000, "b": 1_000_000_000}
    numbers = []
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(k|m|million|b)?", text):
        number = float(match.group(1))
        suffix = match.group(2)
        if suffix:
            number *= multipliers.get(suffix, 1)
        numbers.append(number)
    if not numbers:
        return 0.0
    if any(token in text for token in ["+", "over", "above"]):
        return max(numbers) * 1.15
    return float(sum(numbers) / len(numbers))


class BusinessLeadsTools:
    """Business lead analytics implemented with dataframe calculations."""

    def __init__(self, df: pd.DataFrame, filename: str | None = None):
        self.df = df.copy()
        self.filename = filename
        self.profile = profile_dataframe(self.df)
        self.semantic = self.profile["semantic_columns"]

    def _base_result(self, intent: str, method: str) -> dict[str, Any]:
        return {
            "intent": intent,
            "dataset_type": "business_leads",
            "answer": "",
            "method": method,
            "tables": [],
            "charts": [],
            "warnings": [],
            "recommendations": [],
            "profile": self.profile,
            "suggestions": self.follow_up_suggestions(),
        }

    def _table(self, columns: list[str], rows: list[dict[str, Any]], title: str) -> dict[str, Any]:
        return {"title": title, "columns": columns, "rows": rows}

    def _chart(self, chart_type: str, title: str, data: list[dict[str, Any]], x_key: str, y_key: str) -> dict[str, Any]:
        return {"type": chart_type, "title": title, "data": data, "x_key": x_key, "y_key": y_key}

    def _column(self, role: str) -> str | None:
        column = self.semantic.get(role)
        return column if column in self.df.columns else None

    def dataset_overview(self) -> dict[str, Any]:
        result = self._base_result("dataset_overview", "Profiled rows, columns, roles, missing values and lead-oriented distributions.")
        rows = self.profile["row_count"]
        cols = self.profile["column_count"]
        website_col = self._column("website")
        country_col = self._column("country")
        industry_col = self._column("industry")
        employee_col = self._column("employee_range")
        revenue_col = self._column("revenue_range")

        website_missing = None
        if website_col:
            missing_info = self.profile["missing_values"].get(website_col, {})
            website_missing = float(missing_info.get("pct", 0))

        important = []
        for label, column in [
            ("business names", self._column("business_name")),
            ("websites", website_col),
            ("employee ranges", employee_col),
            ("yearly revenue ranges", revenue_col),
            ("countries", country_col),
            ("regions", self._column("region")),
            ("industries/NAICS descriptions", industry_col),
            ("business IDs", self._column("business_id")),
        ]:
            if column:
                important.append(f"{label} (`{column}`)")

        purpose = "a business leads/prospecting dataset"
        filename_norm = (self.filename or "").lower()
        if "no_website" in filename_norm or (website_col and website_missing == 100.0):
            purpose = "a no-website business leads/prospecting dataset"

        answer_parts = [
            f"This dataset contains {rows:,} business records with {cols} columns.",
            f"It appears to be {purpose}.",
        ]
        if important:
            answer_parts.append(f"It includes {', '.join(important)}.")
        if website_col and website_missing is not None:
            if website_missing == 100.0:
                answer_parts.append(
                    f"The `{website_col}` column is 100% empty, which fits a no-website lead-generation list."
                )
            elif website_missing:
                answer_parts.append(f"The `{website_col}` column is {website_missing:.1f}% empty.")
        if country_col:
            answer_parts.append("Countries can be analyzed for market prioritization.")
        if employee_col or revenue_col:
            answer_parts.append("Employee and revenue ranges can be used for lead prioritization.")
        if industry_col:
            answer_parts.append("The industry/NAICS column can be used for outreach targeting.")

        result["answer"] = " ".join(answer_parts)
        result["tables"].append(
            self._table(
                ["column", "role", "missing_pct", "unique"],
                [
                    {
                        "column": item["name"],
                        "role": item["role"],
                        "missing_pct": item["missing_pct"],
                        "unique": item["unique"],
                    }
                    for item in self.profile["column_profiles"]
                ],
                "Detected column roles",
            )
        )
        key_insights = []
        if website_col:
            key_insights.append(f"{website_missing:.1f}% of website values are missing.")
        if country_col:
            key_insights.append(f"{self.df[country_col].nunique(dropna=True)} countries are represented.")
        if industry_col:
            key_insights.append(f"{self.df[industry_col].nunique(dropna=True)} industries are represented.")
        result["recommendations"] = key_insights
        return result

    def missing_value_report(self) -> dict[str, Any]:
        result = self._base_result("missing_values", "Counted missing values by column.")
        rows = [
            {"column": column, "missing": info["count"], "missing_pct": info["pct"]}
            for column, info in self.profile["missing_values"].items()
            if info["count"] > 0
        ]
        rows.sort(key=lambda row: row["missing"], reverse=True)
        result["answer"] = f"The dataset has {self.profile['quality']['total_missing']:,} missing cells."
        result["tables"].append(self._table(["column", "missing", "missing_pct"], rows, "Missing value report"))
        return result

    def distribution(self, role: str, intent: str, title: str) -> dict[str, Any]:
        result = self._base_result(intent, f"Grouped business records by detected {role} column.")
        column = self._column(role)
        if not column:
            result["answer"] = f"I could not find a {role.replace('_', ' ')} column in this dataset."
            result["warnings"].append(f"Missing {role} column.")
            return result
        counts = self.df[column].fillna("Unknown").astype(str).value_counts().head(20)
        rows = [{"value": str(index), "businesses": int(value)} for index, value in counts.items()]
        result["answer"] = (
            f"{rows[0]['value']} has the most businesses ({rows[0]['businesses']}) by {role.replace('_', ' ')}."
            if rows
            else f"No {role.replace('_', ' ')} values were available."
        )
        result["tables"].append(self._table(["value", "businesses"], rows, title))
        result["charts"].append(self._chart("bar", title, rows, "value", "businesses"))
        return result

    def country_distribution(self) -> dict[str, Any]:
        return self.distribution("country", "country_distribution", "Country-wise business distribution")

    def industry_distribution(self) -> dict[str, Any]:
        return self.distribution("industry", "industry_distribution", "Industry distribution")

    def employee_range_distribution(self) -> dict[str, Any]:
        return self.distribution("employee_range", "employee_range_distribution", "Employee range distribution")

    def revenue_range_distribution(self) -> dict[str, Any]:
        return self.distribution("revenue_range", "revenue_range_distribution", "Revenue range distribution")

    def no_website_analysis(self) -> dict[str, Any]:
        result = self._base_result("no_website_analysis", "Calculated website missingness and grouped no-website leads.")
        website_col = self._column("website")
        if not website_col:
            result["answer"] = "I could not find a website column in this dataset."
            result["warnings"].append("Missing website column.")
            return result
        missing_mask = self.df[website_col].isna() | (self.df[website_col].astype(str).str.strip() == "")
        missing_count = int(missing_mask.sum())
        pct = missing_count / max(1, len(self.df)) * 100
        result["answer"] = f"{missing_count:,} of {len(self.df):,} businesses ({pct:.1f}%) have missing websites."
        rows = [
            {"website_status": "Missing website", "businesses": missing_count},
            {"website_status": "Website present", "businesses": int(len(self.df) - missing_count)},
        ]
        result["tables"].append(self._table(["website_status", "businesses"], rows, "Website availability"))
        result["charts"].append(self._chart("bar", "Website availability", rows, "website_status", "businesses"))
        return result

    def lead_scoring(self, limit: int = 10) -> dict[str, Any]:
        result = self._base_result("lead_scoring", "Scored leads using revenue range, employee range and missing-website opportunity.")
        scored = self._scored_leads(limit=limit)
        result["answer"] = (
            f"{scored[0]['business_name']} is the highest-scored lead with a score of {scored[0]['lead_score']}."
            if scored
            else "No lead rows could be scored from the available columns."
        )
        result["tables"].append(self._table(list(scored[0].keys()) if scored else [], scored, "Lead scoring"))
        return result

    def high_value_leads(self, limit: int = 10) -> dict[str, Any]:
        result = self.lead_scoring(limit=limit)
        result["intent"] = "high_value_leads"
        result["answer"] = result["answer"].replace("highest-scored lead", "highest-value prospect")
        return result

    def outreach_recommendations(self, limit: int = 10) -> dict[str, Any]:
        result = self._base_result("outreach_recommendations", "Calculated lead segments and generated outreach recommendations from those outputs.")
        scored = self._scored_leads(limit=limit)
        country = self.country_distribution()
        industry = self.industry_distribution()
        employees = self.employee_range_distribution()
        revenue = self.revenue_range_distribution()
        no_website = self.no_website_analysis()

        website_sentence = no_website["answer"]
        top_country = country.get("tables", [{}])[0].get("rows", [{}])[0].get("value", "the top country")
        top_industry = industry.get("tables", [{}])[0].get("rows", [{}])[0].get("value", "the most common industry")
        top_employee = employees.get("tables", [{}])[0].get("rows", [{}])[0].get("value", "larger employee ranges")
        top_revenue = revenue.get("tables", [{}])[0].get("rows", [{}])[0].get("value", "higher revenue ranges")

        recommendations = [
            f"Prioritize leads with {top_revenue} revenue ranges and {top_employee} employee ranges first.",
            f"Create separate outreach campaigns for {top_country} and other countries with meaningful lead volume.",
            f"Use industry-specific messaging for {top_industry} and other common sectors.",
            "Pitch website development, SEO, Google Business Profile setup, lead-generation automation, CRM integration, and digital transformation services.",
        ]
        result["answer"] = (
            f"{website_sentence} This is ideal for website-development outreach. "
            f"The most common industry is {top_industry}. Prioritize higher revenue and employee ranges, "
            f"then localize campaigns by country."
        )
        result["recommendations"] = recommendations
        if scored:
            result["tables"].append(self._table(list(scored[0].keys()), scored, "Lead scoring"))
        for source in (country, industry, revenue, employees):
            if source.get("tables"):
                result["tables"].append(source["tables"][0])
            if source.get("charts"):
                result["charts"].append(source["charts"][0])
        return result

    def _scored_leads(self, limit: int = 10) -> list[dict[str, Any]]:
        name_col = self._column("business_name")
        website_col = self._column("website")
        employee_col = self._column("employee_range")
        revenue_col = self._column("revenue_range")
        country_col = self._column("country")
        industry_col = self._column("industry")

        working = self.df.copy()
        revenue_values = working[revenue_col].map(_range_midpoint) if revenue_col else pd.Series(0, index=working.index)
        employee_values = working[employee_col].map(_range_midpoint) if employee_col else pd.Series(0, index=working.index)

        def normalize(series: pd.Series) -> pd.Series:
            series = pd.to_numeric(series, errors="coerce").fillna(0)
            max_value = float(series.max()) if len(series) else 0.0
            return series / max_value if max_value else series

        website_missing = (
            working[website_col].isna() | (working[website_col].astype(str).str.strip() == "")
            if website_col else pd.Series(False, index=working.index)
        )
        score = normalize(revenue_values) * 45 + normalize(employee_values) * 35 + website_missing.astype(int) * 20
        working["_lead_score"] = score.round(1)
        working = working.sort_values("_lead_score", ascending=False).head(limit)

        rows = []
        for _, row in working.iterrows():
            rows.append(
                {
                    "business_name": _safe_text(row.get(name_col), "Unnamed business") if name_col else "Unnamed business",
                    "country": _safe_text(row.get(country_col)) if country_col else "Unknown",
                    "industry": _safe_text(row.get(industry_col)) if industry_col else "Unknown",
                    "employee_range": _safe_text(row.get(employee_col)) if employee_col else "Unknown",
                    "revenue_range": _safe_text(row.get(revenue_col)) if revenue_col else "Unknown",
                    "website_status": "Missing website" if bool(website_missing.loc[row.name]) else "Website present",
                    "lead_score": float(row["_lead_score"]),
                }
            )
        return rows

    def follow_up_suggestions(self) -> list[str]:
        suggestions = []
        available = self.semantic
        if available.get("country"):
            suggestions.append("Which countries have the most businesses?")
        if available.get("industry"):
            suggestions.append("Which industries are most common?")
        suggestions.append("Which businesses look like the highest-value leads?")
        if available.get("employee_range"):
            suggestions.append("Segment businesses by employee range.")
        if available.get("revenue_range"):
            suggestions.append("Segment businesses by yearly revenue range.")
        suggestions.append("Create an outreach strategy for these leads.")
        if available.get("website"):
            suggestions.append("Which businesses have no website?")
        return suggestions[:7]
