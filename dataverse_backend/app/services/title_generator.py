"""Generate short ChatGPT-style chat titles from dataset/query context."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .llm_provider import LLMProvider


MONTHS = {
    "jan": "January",
    "feb": "February",
    "mar": "March",
    "apr": "April",
    "may": "May",
    "jun": "June",
    "jul": "July",
    "aug": "August",
    "sep": "September",
    "oct": "October",
    "nov": "November",
    "dec": "December",
}


class TitleGenerator:
    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self.llm_provider = llm_provider or LLMProvider(provider="openai")

    async def generate(
        self,
        *,
        filename: str | None = None,
        query: str | None = None,
        dataset_type: str | None = None,
        semantic_map: dict[str, Any] | None = None,
    ) -> str:
        fallback = self.fallback(filename=filename, query=query, dataset_type=dataset_type or semantic_map_get(semantic_map, "dataset_type"))
        if not self.llm_provider.is_configured():
            return fallback
        prompt = (
            "Generate a concise analytics chat title. Max 5 words. No punctuation unless needed. "
            "Do not use generic 'New Chat'.\n"
            f"Filename: {filename or ''}\n"
            f"Dataset type: {dataset_type or semantic_map_get(semantic_map, 'dataset_type') or ''}\n"
            f"User query: {query or ''}\n"
            f"Fallback idea: {fallback}"
        )
        text = await self.llm_provider.generate(prompt, system_prompt="Return only the short title.", json_mode=False)
        return clean_title(text) if text else fallback

    def fallback(self, *, filename: str | None = None, query: str | None = None, dataset_type: str | None = None) -> str:
        source = " ".join(part for part in [filename or "", query or "", dataset_type or ""] if part)
        normalized = source.lower()
        month = next((label for key, label in MONTHS.items() if re.search(rf"\b{key}[a-z]*\b", normalized)), None)
        if not month and re.search(r"\b20\d{2}[-_/ ](0[1-9]|1[0-2])\b", normalized):
            try:
                month_num = int(re.search(r"\b20\d{2}[-_/ ](0[1-9]|1[0-2])\b", normalized).group(1))  # type: ignore[union-attr]
                month = datetime(2000, month_num, 1).strftime("%B")
            except Exception:
                month = None

        dataset_label = (dataset_type or "").replace("_", " ").title()
        if "churn" in normalized:
            base = "Customer Churn"
        elif any(word in normalized for word in ["inventory", "stock"]):
            base = "Inventory Trend"
        elif any(word in normalized for word in ["sales", "revenue", "retail", "invoice", "order"]):
            base = "Sales Analysis"
        elif dataset_label and dataset_label != "Generic Tabular":
            base = dataset_label
        else:
            stem = Path(filename or "Dataset").stem
            base = re.sub(r"[_\-.]+", " ", stem).strip().title() or "Dataset Analysis"

        title = f"{month} {base}" if month and month.lower() not in base.lower() else base
        if "report" not in title.lower() and any(word in normalized for word in ["report", "pdf", "download"]):
            title = f"{title} Report"
        return clean_title(title)


def semantic_map_get(value: dict[str, Any] | None, key: str) -> str | None:
    if isinstance(value, dict) and isinstance(value.get(key), str):
        return value[key]
    return None


def clean_title(value: str | None) -> str:
    text = re.sub(r"[^A-Za-z0-9 &/-]+", "", (value or "").strip())
    words = [word for word in text.replace("_", " ").split() if word]
    if not words:
        return "Dataset Analysis"
    title = " ".join(words[:5])
    if title.lower() == "new chat":
        return "Dataset Analysis"
    return title
