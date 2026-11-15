"""Structured LLM output: the JSON schema sent to the model and strict validation of the reply.

The model's schema adherence is not trusted: the provider ignores several JSON Schema keywords
(e.g. string lengths), so every constraint is re-checked here before anything is stored.
"""

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.models.enums import CATEGORY_LABELS, Category, SourceCoverage

MAX_HEADLINE = 200
MAX_BULLET = 400
MAX_WHY = 500
MAX_ENTITIES = 10
MAX_ENTITY = 100
MAX_LIMITATIONS = 300

BULLET_RANGE: dict[SourceCoverage, tuple[int, int]] = {
    SourceCoverage.ARTICLE_TEXT: (3, 5),
    SourceCoverage.EXCERPT: (1, 3),
}

_LABEL_TO_CATEGORY = {label.lower(): cat for cat, label in CATEGORY_LABELS.items()}
_LABEL_TO_CATEGORY.update({cat.value: cat for cat in Category})

SUMMARY_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "insufficient_information": {
            "type": "boolean",
            "description": "True if the text is too thin to summarize without guessing.",
        },
        "limitations": {
            "type": "string",
            "description": "Caveat about the source material, or an empty string.",
        },
        "headline": {"type": "string", "description": "Clear, factual headline."},
        "category": {"type": "string", "enum": list(CATEGORY_LABELS.values())},
        "summary": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 5,
            "description": "Concise factual takeaways.",
        },
        "why_it_matters": {"type": "string", "description": "One sentence."},
        "impact_score": {"type": "integer", "minimum": 1, "maximum": 10},
        "significance_score": {"type": "integer", "minimum": 1, "maximum": 10},
        "key_entities": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_ENTITIES},
    },
    "required": [
        "insufficient_information",
        "limitations",
        "headline",
        "category",
        "summary",
        "why_it_matters",
        "impact_score",
        "significance_score",
        "key_entities",
    ],
}


class InvalidSummaryOutput(ValueError):
    """The model's reply cannot be stored. The message is safe to persist."""


def _clean(value: str) -> str:
    return " ".join(value.split())


class SummaryOutput(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    insufficient_information: bool
    limitations: str = Field(default="", max_length=MAX_LIMITATIONS)
    headline: str = Field(max_length=MAX_HEADLINE)
    category: Category
    summary: list[str] = Field(max_length=5)
    why_it_matters: str = Field(max_length=MAX_WHY)
    impact_score: int = Field(ge=1, le=10)
    significance_score: int = Field(ge=1, le=10)
    key_entities: list[str] = Field(default_factory=list)

    @field_validator("headline", "why_it_matters", "limitations", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return _clean(value) if isinstance(value, str) else value

    @field_validator("category", mode="before")
    @classmethod
    def known_category(cls, value: Any) -> Category:
        category = _LABEL_TO_CATEGORY.get(str(value).strip().lower())
        if category is None:
            raise ValueError(f"unsupported category {str(value)[:40]!r}")
        return category

    @field_validator("summary", mode="before")
    @classmethod
    def clean_bullets(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        bullets: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("summary items must be strings")
            text = _clean(item).lstrip("-•* ").strip()
            if len(text) > MAX_BULLET:
                raise ValueError("summary item too long")
            if text and text.lower() not in {b.lower() for b in bullets}:
                bullets.append(text)
        return bullets

    @field_validator("key_entities", mode="before")
    @classmethod
    def clean_entities(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        seen: dict[str, str] = {}
        for item in value:
            text = _clean(str(item))
            if text and len(text) <= MAX_ENTITY and text.lower() not in seen:
                seen[text.lower()] = text
        return list(seen.values())[:MAX_ENTITIES]


def parse_summary_output(raw: str, coverage: SourceCoverage) -> SummaryOutput:
    """Parse and validate model output for the given source coverage."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidSummaryOutput("model returned malformed JSON") from exc
    if not isinstance(data, dict):
        raise InvalidSummaryOutput("model returned a non-object JSON value")
    try:
        output = SummaryOutput.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(p) for p in first["loc"]) or "output"
        raise InvalidSummaryOutput(f"invalid {field}: {first['msg']}") from exc

    if output.insufficient_information:
        return output
    low, high = BULLET_RANGE[coverage]
    if not low <= len(output.summary) <= high:
        raise InvalidSummaryOutput(
            f"expected {low}-{high} summary points for {coverage.value}, got {len(output.summary)}"
        )
    if not output.headline or not output.why_it_matters:
        raise InvalidSummaryOutput("headline and why_it_matters are required")
    return output
