"""Optional DeepAnalyze client using OpenAI-compatible HTTP APIs."""
from __future__ import annotations

from typing import Any

import httpx

from ..core.config import settings


class DeepAnalyzeClient:
    """Call remote or local DeepAnalyze safely.

    This client is optional. It returns None on missing configuration, timeout,
    or provider errors so deterministic analytics never depend on DeepAnalyze.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        local_base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ):
        self.api_key = api_key if api_key is not None else settings.DEEPANALYZE_API_KEY
        self.api_base = (api_base if api_base is not None else settings.DEEPANALYZE_API_BASE) or ""
        self.local_base_url = (local_base_url if local_base_url is not None else settings.DEEPANALYZE_LOCAL_BASE_URL) or ""
        self.model = model or settings.DEEPANALYZE_MODEL
        self.timeout = float(timeout or settings.REPORT_NARRATOR_TIMEOUT_SECONDS)

    def configured_base_url(self) -> tuple[str, str | None] | None:
        if self.api_key and self.api_base:
            return self.api_base.rstrip("/"), self.api_key
        if self.local_base_url:
            return self.local_base_url.rstrip("/"), self.api_key
        return None

    async def generate(self, prompt: str, computed_facts: dict[str, Any] | None = None, max_tokens: int = 700) -> str | None:
        configured = self.configured_base_url()
        if not configured:
            return None
        base_url, api_key = configured
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Explain computed data analysis facts. Do not invent numbers."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"] or None
        except Exception:
            return None
