from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from ..config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """OpenAI-compatible JSON client for the configured Qwen/DashScope model."""

    def __init__(self) -> None:
        self.enabled = settings.llm_enabled

    def generate_json(
        self,
        *,
        system: str,
        prompt: str,
        schema_hint: dict[str, Any],
        max_tokens: int = 1200,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("LLM is not configured. Set LLM_API_KEY, LLM_BASE_URL and LLM_MODEL.")

        payload = {
            "model": settings.llm_model,
            "temperature": 0.1,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"{system}\n"
                        "Return valid compact JSON only. Do not use markdown. "
                        "Write all user-facing business content in Simplified Chinese. "
                        "Do not infer sensitive attributes. Do not present correlation as causation. "
                        "Keep each string under 40 Chinese characters. "
                        "Use short category, interest, product, and action keywords."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"{prompt}\n\n"
                        "Return JSON strictly following this shape:\n"
                        f"{json.dumps(schema_hint, ensure_ascii=False)}"
                    ),
                },
            ],
        }
        try:
            timeout = httpx.Timeout(
                settings.llm_timeout_seconds,
                connect=min(5.0, settings.llm_timeout_seconds),
                read=settings.llm_timeout_seconds,
                write=min(10.0, settings.llm_timeout_seconds),
                pool=min(5.0, settings.llm_timeout_seconds),
            )
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    f"{settings.llm_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.llm_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        except (
            httpx.HTTPError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            logger.warning("LLM generation failed: %s", exc)
            raise RuntimeError(f"LLM generation failed: {exc}") from exc
