"""Importance ranking.

importance = w_impact * impact + w_significance * significance
           + w_credibility * credibility + w_recency * recency          (each component 1-10)

Impact and significance come from the model's assessment. Until an article has one (or when it
cannot be summarized) they default to a neutral-low value, so unassessed stories do not outrank
assessed important ones. Credibility is the source weight scaled to 1-10. Recency decays
exponentially with the configured half-life, so scores are recomputed as articles age.
Popularity (how many outlets covered a story) is deliberately not an input.
"""

from dataclasses import dataclass
from datetime import datetime

from app.config import Settings

UNASSESSED_SCORE = 4.0


@dataclass(frozen=True)
class RankingWeights:
    impact: float
    significance: float
    credibility: float
    recency: float
    recency_half_life_hours: float

    @classmethod
    def from_settings(cls, settings: Settings) -> "RankingWeights":
        return cls(
            impact=settings.ranking_weight_impact,
            significance=settings.ranking_weight_significance,
            credibility=settings.ranking_weight_credibility,
            recency=settings.ranking_weight_recency,
            recency_half_life_hours=settings.ranking_recency_half_life_hours,
        )


def _clamp(value: float) -> float:
    return max(1.0, min(10.0, value))


def recency_score(published_at: datetime, now: datetime, half_life_hours: float) -> float:
    age_hours = max(0.0, (now - published_at).total_seconds() / 3600)
    return 1.0 + 9.0 * 0.5 ** (age_hours / half_life_hours)


def credibility_score(weight: float) -> float:
    return 1.0 + 9.0 * max(0.0, min(1.0, weight))


def importance_score(
    *,
    impact: float | None,
    significance: float | None,
    credibility_weight: float,
    published_at: datetime,
    now: datetime,
    weights: RankingWeights,
) -> float:
    score = (
        weights.impact * _clamp(impact if impact is not None else UNASSESSED_SCORE)
        + weights.significance
        * _clamp(significance if significance is not None else UNASSESSED_SCORE)
        + weights.credibility * credibility_score(credibility_weight)
        + weights.recency * recency_score(published_at, now, weights.recency_half_life_hours)
    )
    return round(_clamp(score), 2)
