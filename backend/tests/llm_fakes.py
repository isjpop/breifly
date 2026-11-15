"""Deterministic stand-ins for the LLM provider."""

import json
from collections.abc import Iterable
from typing import Any

from app.services.llm import LLMError, LLMResult, TokenUsage


def valid_output(**overrides: Any) -> str:
    data: dict[str, Any] = {
        "insufficient_information": False,
        "limitations": "",
        "headline": "Chipmaker launches 2nm data-center processor",
        "category": "Technology",
        "summary": [
            "The company unveiled a 2-nanometer processor for data centers.",
            "It claims 40% better energy efficiency than the previous generation.",
            "Shipments are expected in the second quarter, per the CEO.",
        ],
        "why_it_matters": "More efficient chips could lower the cost of running AI workloads.",
        "impact_score": 7,
        "significance_score": 6,
        "key_entities": ["Example Chips Inc.", "2nm process"],
    }
    data.update(overrides)
    return json.dumps(data)


class FakeLLM:
    """Returns queued responses in order: a string becomes model output, an exception is raised."""

    provider = "fake"
    model = "fake-model-1"

    def __init__(self, responses: Iterable[str | LLMError] = (), *, default: str | None = None):
        self._responses = list(responses)
        self._default = default
        self.calls: list[dict[str, Any]] = []

    def generate_json(
        self,
        *,
        system_instruction: str,
        prompt: str,
        schema: dict[str, Any],
        max_output_tokens: int,
    ) -> LLMResult:
        self.calls.append({"system": system_instruction, "prompt": prompt, "schema": schema})
        item = self._responses.pop(0) if self._responses else self._default
        if item is None:
            raise AssertionError("FakeLLM ran out of responses")
        if isinstance(item, LLMError):
            raise item
        return LLMResult(text=item, model=self.model, usage=TokenUsage(1000, 200, 50), latency_ms=5)
