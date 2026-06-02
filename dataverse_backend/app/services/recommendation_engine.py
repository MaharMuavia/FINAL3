"""Dataset-specific follow-up suggestions and lightweight recommendations."""
from __future__ import annotations

from typing import Any


def follow_up_suggestions(dataset_type: str, semantic_columns: dict[str, Any] | None = None) -> list[str]:
    semantic = semantic_columns or {}
    if dataset_type == "business_leads":
        suggestions = []
        if semantic.get("country"):
            suggestions.append("Which countries have the most businesses?")
        if semantic.get("industry"):
            suggestions.append("Which industries are most common?")
        suggestions.append("Which businesses look like the highest-value leads?")
        if semantic.get("employee_range"):
            suggestions.append("Segment businesses by employee range.")
        if semantic.get("revenue_range"):
            suggestions.append("Segment businesses by yearly revenue range.")
        suggestions.append("Create an outreach strategy for these leads.")
        if semantic.get("website"):
            suggestions.append("Which businesses have no website?")
        return suggestions

    if dataset_type == "sales":
        suggestions = []
        if semantic.get("product"):
            suggestions.append("What are the top products?")
        if semantic.get("product") and semantic.get("date"):
            suggestions.append("Which products are trending?")
        if semantic.get("revenue") and semantic.get("date"):
            suggestions.append("Show revenue by month.")
        if semantic.get("category"):
            suggestions.append("Which category performs best?")
        return suggestions or ["Summarize this dataset.", "Which columns have missing values?"]

    if dataset_type == "customer":
        return [
            "Who are the top customers?",
            "Segment customers by value.",
            "Show customer locations.",
            "Which customers look high-value?",
        ]

    if dataset_type == "finance":
        return [
            "Show expense summary.",
            "Compare income vs expense.",
            "Show monthly trend.",
            "Break this down by category.",
        ]

    return [
        "Summarize this dataset.",
        "Which columns have missing values?",
        "Show unique values by column.",
        "Find important patterns.",
    ]
