from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.services.ranking import (
    UNASSESSED_SCORE,
    RankingWeights,
    credibility_score,
    importance_score,
    recency_score,
)

NOW = datetime(2026, 11, 15, 12, tzinfo=UTC)
WEIGHTS = RankingWeights(0.35, 0.30, 0.20, 0.15, recency_half_life_hours=12)


def score(**kwargs: object) -> float:
    args: dict[str, object] = {
        "impact": 5,
        "significance": 5,
        "credibility_weight": 0.8,
        "published_at": NOW,
        "now": NOW,
        "weights": WEIGHTS,
    }
    args.update(kwargs)
    return importance_score(**args)  # type: ignore[arg-type]


def test_recency_halves_each_half_life() -> None:
    assert recency_score(NOW, NOW, 12) == 10
    assert recency_score(NOW - timedelta(hours=12), NOW, 12) == pytest.approx(5.5)
    assert recency_score(NOW - timedelta(days=30), NOW, 12) == pytest.approx(1, abs=0.01)
    assert recency_score(NOW + timedelta(hours=1), NOW, 12) == 10  # clock skew


def test_credibility_scaling() -> None:
    assert credibility_score(0) == 1 and credibility_score(1) == 10


def test_weighted_formula() -> None:
    # 0.35*8 + 0.30*6 + 0.20*(1+9*0.8) + 0.15*10 = 2.8 + 1.8 + 1.64 + 1.5
    assert score(impact=8, significance=6) == pytest.approx(7.74)


def test_meaningful_development_outranks_fresher_routine_one() -> None:
    major = score(impact=9, significance=8, published_at=NOW - timedelta(hours=10))
    routine = score(impact=2, significance=2, published_at=NOW)
    assert major > routine


def test_unassessed_articles_use_neutral_low_default() -> None:
    assert score(impact=None, significance=None) == score(
        impact=UNASSESSED_SCORE, significance=UNASSESSED_SCORE
    )


def test_score_is_clamped_to_1_10() -> None:
    assert (
        1
        <= score(
            impact=1, significance=1, credibility_weight=0, published_at=NOW - timedelta(days=99)
        )
        <= 10
    )
    assert score(impact=10, significance=10, credibility_weight=1) == 10


def test_weights_are_configurable_and_validated() -> None:
    settings = Settings(
        ranking_weight_impact=0.5,
        ranking_weight_significance=0.2,
        ranking_weight_credibility=0.2,
        ranking_weight_recency=0.1,
    )
    assert RankingWeights.from_settings(settings).impact == 0.5
    with pytest.raises(ValidationError, match=r"sum to 1\.0"):
        Settings(ranking_weight_impact=0.9)
