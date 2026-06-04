"""Optional LLM provider chain for report narration only."""
from __future__ import annotations

import os
from collections.abc import Awaitable, Callable

from ..core.config import settings
from .deepanalyze_client import DeepAnalyzeClient


Generator = Callable[[str], Awaitable[str | None]]


class LLMProvider:
    """OpenAI/Gemini/Anthropic/DeepAnalyze provider with deterministic fallback."""

    VALID_PROVIDERS = {"auto", "openai", "gemini", "anthropic", "deepanalyze", "deterministic"}

    def __init__(
        self,
        provider: str | None = None,
        openai_api_key: str | None = None,
        gemini_api_key: str | None = None,
        anthropic_api_key: str | None = None,
        deepanalyze_api_key: str | None = None,
        openai_generate: Generator | None = None,
        gemini_generate: Generator | None = None,
        anthropic_generate: Generator | None = None,
        deepanalyze_generate: Generator | None = None,
    ):
        requested = (provider or settings.LLM_PROVIDER or os.getenv("LLM_PROVIDER") or "auto").strip().lower()
        self.provider = requested if requested in self.VALID_PROVIDERS else "auto"
        self._openai_api_key = openai_api_key
        self._gemini_api_key = gemini_api_key
        self._anthropic_api_key = anthropic_api_key
        self._deepanalyze_api_key = deepanalyze_api_key
        self._openai_generate = openai_generate
        self._gemini_generate = gemini_generate
        self._anthropic_generate = anthropic_generate
        self._deepanalyze_generate = deepanalyze_generate
        self.last_provider: str | None = None
        self.last_errors: list[str] = []

    def configured_order(self) -> list[str]:
        if self.provider == "deterministic":
            return []
        order = []
        if self._openai_api_key or settings.OPENAI_API_KEY:
            order.append("openai")
        if self._gemini_api_key or settings.GEMINI_API_KEY or os.getenv("GOOGLE_API_KEY"):
            order.append("gemini")
        if self._anthropic_api_key or settings.ANTHROPIC_API_KEY:
            order.append("anthropic")
        if self._deepanalyze_api_key or (settings.DEEPANALYZE_API_KEY and settings.DEEPANALYZE_API_BASE) or settings.DEEPANALYZE_LOCAL_BASE_URL:
            order.append("deepanalyze")
        if self.provider in {"openai", "gemini", "anthropic", "deepanalyze"}:
            order = [self.provider, *[item for item in order if item != self.provider]]
        return order

    def is_configured(self) -> bool:
        return bool(self.configured_order())

    async def generate(self, prompt: str, *, system_prompt: str | None = None, json_mode: bool = False) -> str | None:
        self.last_provider = None
        self.last_errors = []
        for provider in self.configured_order():
            try:
                if provider == "openai":
                    text = await self._generate_openai(prompt, system_prompt=system_prompt, json_mode=json_mode)
                elif provider == "gemini":
                    text = await self._generate_gemini(prompt, system_prompt=system_prompt, json_mode=json_mode)
                elif provider == "anthropic":
                    text = await self._generate_anthropic(prompt, system_prompt=system_prompt, json_mode=json_mode)
                else:
                    text = await self._generate_deepanalyze(prompt)
                if text:
                    self.last_provider = provider
                    return text
            except Exception as exc:
                self.last_errors.append(f"{provider}: {type(exc).__name__}")
        return None

    async def _generate_openai(self, prompt: str, *, system_prompt: str | None = None, json_mode: bool = False) -> str | None:
        if self._openai_generate:
            return await self._openai_generate(prompt)
        api_key = self._openai_api_key or settings.OPENAI_API_KEY
        if not api_key:
            return None
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key, timeout=settings.REPORT_NARRATOR_TIMEOUT_SECONDS, max_retries=0)
        kwargs = {
            "model": settings.OPENAI_CHAT_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt or "Narrate computed analytics only. Do not invent facts."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 900,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = await client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    async def _generate_gemini(self, prompt: str, *, system_prompt: str | None = None, json_mode: bool = False) -> str | None:
        if self._gemini_generate:
            return await self._gemini_generate(prompt)
        key = self._gemini_api_key or settings.GEMINI_API_KEY or os.getenv("GOOGLE_API_KEY")
        if not key:
            return None
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=key)
        model = genai.GenerativeModel(settings.GEMINI_MODEL)
        response = await model.generate_content_async(
            f"{system_prompt or ''}\n\n{prompt}".strip(),
            generation_config={"temperature": 0.2, "max_output_tokens": 900},
            request_options={"timeout": settings.REPORT_NARRATOR_TIMEOUT_SECONDS},
        )
        return getattr(response, "text", None)

    async def _generate_anthropic(self, prompt: str, *, system_prompt: str | None = None, json_mode: bool = False) -> str | None:
        if self._anthropic_generate:
            return await self._anthropic_generate(prompt)
        api_key = self._anthropic_api_key or settings.ANTHROPIC_API_KEY
        if not api_key:
            return None
        from anthropic import AsyncAnthropic  # type: ignore

        client = AsyncAnthropic(api_key=api_key, timeout=settings.REPORT_NARRATOR_TIMEOUT_SECONDS, max_retries=0)
        response = await client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=900,
            temperature=0.2,
            system=system_prompt or "Use only the provided facts. Do not invent values.",
            messages=[{"role": "user", "content": prompt}],
        )
        return "\n".join(getattr(part, "text", "") for part in response.content if getattr(part, "text", ""))

    async def _generate_deepanalyze(self, prompt: str) -> str | None:
        if self._deepanalyze_generate:
            return await self._deepanalyze_generate(prompt)
        return await DeepAnalyzeClient().generate(prompt)
