"""LLM service — single interface for AI text generation.

Supports OpenAI and Gemini. Falls back gracefully if no API key configured.
Used only for natural language explanations — never for calculations.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class LLMService:
    """Simple LLM wrapper that tries OpenAI first, then Gemini, then returns template text."""

    def __init__(self):
        from ..core.config import settings
        self._openai_key = settings.OPENAI_API_KEY
        self._gemini_key = settings.GEMINI_API_KEY
        self._openai_model = settings.OPENAI_CHAT_MODEL
        self._gemini_model = settings.GEMINI_MODEL

    async def generate(self, prompt: str, system: str = "", max_tokens: int = 1024) -> Optional[str]:
        """Generate text using configured LLM.

        Returns None if no LLM is available.
        """
        if self._openai_key:
            return await self._generate_openai(prompt, system, max_tokens)
        if self._gemini_key:
            return await self._generate_gemini(prompt, system, max_tokens)
        return None

    def generate_sync(self, prompt: str, system: str = "", max_tokens: int = 1024) -> Optional[str]:
        """Synchronous LLM call — uses OpenAI sync client or returns None."""
        if self._openai_key:
            return self._generate_openai_sync(prompt, system, max_tokens)
        return None

    async def _generate_openai(self, prompt: str, system: str, max_tokens: int) -> Optional[str]:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self._openai_key)
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            response = await client.chat.completions.create(
                model=self._openai_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.3,
            )
            return response.choices[0].message.content
        except Exception:
            logger.warning("OpenAI generation failed", exc_info=True)
            return None

    def _generate_openai_sync(self, prompt: str, system: str, max_tokens: int) -> Optional[str]:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self._openai_key)
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=self._openai_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.3,
            )
            return response.choices[0].message.content
        except Exception:
            logger.warning("OpenAI sync generation failed", exc_info=True)
            return None

    async def _generate_gemini(self, prompt: str, system: str, max_tokens: int) -> Optional[str]:
        try:
            import httpx
            full_prompt = f"{system}\n\n{prompt}" if system else prompt
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self._gemini_model}:generateContent"
            payload = {
                "contents": [{"parts": [{"text": full_prompt}]}],
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    url,
                    json=payload,
                    params={"key": self._gemini_key},
                )
                resp.raise_for_status()
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            logger.warning("Gemini generation failed", exc_info=True)
            return None
