"""Gemini (Google AI Studio) client using the REST Interactions API.

Called directly over httpx rather than through the google-genai SDK: it keeps the dependency
footprint small and gives explicit control over timeouts, retries and error mapping.

Requests set ``store: false`` so prompts are not retained for later retrieval. Note: on the free
tier Google may use submitted content to improve its products; Briefly sends only publisher
feed text, never user data.
"""

import json
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.config import Settings
from app.services.llm import (
    LLMConfigurationError,
    LLMRateLimitError,
    LLMResponseError,
    LLMResult,
    LLMTimeoutError,
    LLMUnavailableError,
    TokenUsage,
)
from app.services.llm.throttle import Throttle

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_ERROR_DETAIL_LIMIT = 200


def _usage(body: dict[str, Any]) -> TokenUsage:
    usage = body.get("usage") or {}
    return TokenUsage(
        input_tokens=int(usage.get("total_input_tokens") or 0),
        output_tokens=int(usage.get("total_output_tokens") or 0),
        thought_tokens=int(usage.get("total_thought_tokens") or 0),
    )


def _output_text(body: dict[str, Any]) -> str:
    """``output_text`` is a convenience field; fall back to concatenating model output steps."""
    if isinstance(body.get("output_text"), str):
        return str(body["output_text"])
    parts: list[str] = []
    for step in body.get("steps") or []:
        if step.get("type") not in (None, "model_output"):
            continue
        for content in step.get("content") or []:
            if content.get("type") == "text" and isinstance(content.get("text"), str):
                parts.append(content["text"])
    return "".join(parts)


def _error_message(response: httpx.Response) -> str:
    """Provider error text, trimmed. Never includes request headers (where the key lives)."""
    try:
        error = response.json().get("error") or {}
        detail = error.get("status") or error.get("message") or ""
    except (ValueError, AttributeError):
        detail = ""
    return f"HTTP {response.status_code} {str(detail)[:_ERROR_DETAIL_LIMIT]}".strip()


class GeminiClient:
    provider = "gemini"

    def __init__(
        self,
        http_client: httpx.Client,
        *,
        api_key: str,
        model: str,
        base_url: str,
        api_revision: str,
        max_retries: int = 2,
        backoff_base: float = 2.0,
        backoff_max: float = 60.0,
        throttle: Throttle | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise LLMConfigurationError("GEMINI_API_KEY is not set")
        self._http = http_client
        self._api_key = api_key
        self.model = model
        self._url = f"{base_url.rstrip('/')}/interactions"
        self._revision = api_revision
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self._throttle = throttle
        self._sleep = sleep

    @classmethod
    def from_settings(cls, http_client: httpx.Client, settings: Settings) -> "GeminiClient":
        key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else ""
        return cls(
            http_client,
            api_key=key,
            model=settings.gemini_model,
            base_url=settings.gemini_api_base_url,
            api_revision=settings.gemini_api_revision,
            max_retries=settings.llm_max_retries,
            throttle=Throttle(settings.llm_requests_per_minute),
        )

    def generate_json(
        self,
        *,
        system_instruction: str,
        prompt: str,
        schema: dict[str, Any],
        max_output_tokens: int,
    ) -> LLMResult:
        payload = {
            "model": self.model,
            "system_instruction": system_instruction,
            "input": prompt,
            "response_format": {"type": "text", "mime_type": "application/json", "schema": schema},
            "generation_config": {"max_output_tokens": max_output_tokens},
            "store": False,
        }
        attempt = 0
        while True:
            try:
                return self._call(payload)
            except (LLMRateLimitError, LLMUnavailableError, LLMTimeoutError) as exc:
                if attempt >= self._max_retries:
                    raise
                delay = min(self._backoff_max, exc.retry_after or self._backoff_base * (2**attempt))
                logger.warning("Gemini call failed (%s); retrying in %.1fs", exc.code, delay)
                self._sleep(delay)
                attempt += 1

    def _call(self, payload: dict[str, Any]) -> LLMResult:
        if self._throttle:
            self._throttle.wait()
        started = time.monotonic()
        headers = {
            "x-goog-api-key": self._api_key,
            "Api-Revision": self._revision,
            "Content-Type": "application/json",
        }
        try:
            response = self._http.post(self._url, headers=headers, content=json.dumps(payload))
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("Gemini request timed out", latency_ms=_ms(started)) from exc
        except httpx.TransportError as exc:
            raise LLMUnavailableError(
                f"network error: {type(exc).__name__}", latency_ms=_ms(started)
            ) from exc
        latency = _ms(started)

        if response.status_code in RETRYABLE_STATUS:
            error_cls = LLMRateLimitError if response.status_code == 429 else LLMUnavailableError
            raise error_cls(
                _error_message(response), latency_ms=latency, retry_after=_retry_after(response)
            )
        if response.status_code >= 400:
            raise LLMConfigurationError(_error_message(response), latency_ms=latency)

        try:
            body = response.json()
        except ValueError as exc:
            raise LLMResponseError("response body is not JSON", latency_ms=latency) from exc

        usage = _usage(body)
        status = body.get("status")
        if status != "completed":
            raise LLMResponseError(
                f"interaction status '{status}'", usage=usage, latency_ms=latency
            )
        text = _output_text(body)
        if not text.strip():
            raise LLMResponseError("empty model output", usage=usage, latency_ms=latency)
        return LLMResult(
            text=text, model=str(body.get("model") or self.model), usage=usage, latency_ms=latency
        )


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    try:
        return max(0.0, float(value)) if value else None
    except ValueError:
        return None


def build_llm_http_client(settings: Settings) -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(settings.llm_timeout_seconds, connect=10.0))
