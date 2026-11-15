"""Provider-neutral LLM interface.

The summarizer depends only on ``LLMClient``; swapping Gemini for another provider means adding
one module that implements ``generate_json`` and raises these error types.
"""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    thought_tokens: int = 0


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    usage: TokenUsage
    latency_ms: int


class LLMError(Exception):
    """Base class. ``code`` is a short, safe identifier stored in usage records."""

    code = "error"

    def __init__(
        self,
        message: str,
        *,
        usage: TokenUsage | None = None,
        latency_ms: int = 0,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.usage = usage or TokenUsage()
        self.latency_ms = latency_ms
        self.retry_after = retry_after  # seconds, when the provider says when to retry


class LLMRateLimitError(LLMError):
    code = "rate_limited"


class LLMTimeoutError(LLMError):
    code = "timeout"


class LLMUnavailableError(LLMError):
    """Provider-side failure (5xx, network). Transient."""

    code = "unavailable"


class LLMConfigurationError(LLMError):
    """Bad key, unknown model, rejected schema: retrying will not help."""

    code = "configuration"


class LLMResponseError(LLMError):
    """The provider answered but produced no usable output (blocked, incomplete, empty)."""

    code = "bad_response"


class LLMClient(Protocol):
    provider: str
    model: str

    def generate_json(
        self,
        *,
        system_instruction: str,
        prompt: str,
        schema: dict[str, Any],
        max_output_tokens: int,
    ) -> LLMResult: ...


__all__ = [
    "LLMClient",
    "LLMConfigurationError",
    "LLMError",
    "LLMRateLimitError",
    "LLMResponseError",
    "LLMResult",
    "LLMTimeoutError",
    "LLMUnavailableError",
    "TokenUsage",
]
