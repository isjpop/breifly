"""Duplicate detection and cross-publisher grouping.

Levels, from strongest to weakest evidence:

1. Exact URL match.
2. Normalized URL match (tracking parameters, ``www.``, trailing slashes, http/https removed).
3. Same feed GUID from the same source.
4. Content hash match (identical body/description text, e.g. syndicated copies).
5. Headline similarity:
   - same source + near-identical headline  →  DUPLICATE (re-published / URL changed)
   - different source + strong topical overlap  →  RELATED (separate reporting on one event;
     kept, and grouped into a story cluster)

Exact-key checks query the database for the whole batch at once; headline comparison uses an
in-memory window of recent articles loaded once per run.
"""

import enum
import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, or_, select

from app.database import DbSession
from app.ingestion.normalizer import NormalizedArticle
from app.models import Article

# Same-source headlines at or above this Jaccard similarity are the same article.
DUPLICATE_TITLE_THRESHOLD = 0.85
# Cross-source "related coverage" rules as (min shared significant words, min overlap
# coefficient); any rule matching is enough. Tuned on real feed headlines for precision over
# recall: headline overlap is weak evidence, so a false grouping is worse than a missed one.
RELATED_RULES: tuple[tuple[int, float], ...] = ((3, 0.6), (4, 0.5))
MIN_TOKENS_FOR_COMPARISON = 3

_APOSTROPHE = "\u2019"  # typographic apostrophe, common in headlines
_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "how",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "over",
        "says",
        "than",
        "that",
        "the",
        "their",
        "this",
        "to",
        "up",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "after",
        "about",
        "new",
        "more",
        "not",
        "you",
        "your",
        "can",
        "could",
        "would",
        "should",
        "may",
        "might",
        "just",
        "now",
        "out",
        "we",
        "our",
        "us",
        "he",
        "she",
        "they",
        "them",
        "his",
        "her",
        "been",
        "being",
        "do",
        "does",
        "did",
        "i",
    ]
)


def title_tokens(title: str) -> frozenset[str]:
    tokens = set()
    for raw in _TOKEN.findall(title.lower().replace(_APOSTROPHE, "'")):
        word = raw.split("'")[0]
        if word in _STOPWORDS or len(word) < 2:
            continue
        # Light plural folding so "catches"/"catch", "chips"/"chip" match.
        if len(word) > 4 and word.endswith("es") and word[-3] in "sxzh":
            word = word[:-2]
        elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        tokens.add(word)
    return frozenset(tokens)


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def overlap(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


class Verdict(enum.StrEnum):
    NEW = "new"
    DUPLICATE = "duplicate"
    RELATED = "related"


class MatchReason(enum.StrEnum):
    EXACT_URL = "exact_url"
    NORMALIZED_URL = "normalized_url"
    GUID = "guid"
    CONTENT_HASH = "content_hash"
    SIMILAR_TITLE = "similar_title"
    RELATED_TITLE = "related_title"


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    reason: MatchReason | None = None
    matched_article_id: uuid.UUID | None = None
    matched_cluster_id: uuid.UUID | None = None
    score: float | None = None


@dataclass(frozen=True)
class Fingerprint:
    article_id: uuid.UUID
    source_id: uuid.UUID
    url: str
    normalized_url: str
    guid: str | None
    content_hash: str | None
    tokens: frozenset[str]
    story_cluster_id: uuid.UUID | None = None


@dataclass
class _KeyIndex:
    urls: dict[str, uuid.UUID] = field(default_factory=dict)
    normalized_urls: dict[str, uuid.UUID] = field(default_factory=dict)
    guids: dict[tuple[uuid.UUID, str], uuid.UUID] = field(default_factory=dict)
    hashes: dict[str, uuid.UUID] = field(default_factory=dict)

    def add(self, fp: Fingerprint) -> None:
        self.urls.setdefault(fp.url, fp.article_id)
        self.normalized_urls.setdefault(fp.normalized_url, fp.article_id)
        if fp.guid:
            self.guids.setdefault((fp.source_id, fp.guid), fp.article_id)
        if fp.content_hash:
            self.hashes.setdefault(fp.content_hash, fp.article_id)


class Deduplicator:
    """Stateful for one ingestion run. Use ``prefetch`` per source batch, ``check`` per entry,
    ``register`` after staging an insert, and ``commit``/``rollback`` with the DB transaction."""

    def __init__(self, session: DbSession, recent: Iterable[Fingerprint] = ()) -> None:
        self._session = session
        self._keys = _KeyIndex()
        self._recent: dict[uuid.UUID, Fingerprint] = {}
        self._pending: list[Fingerprint] = []
        for fp in recent:
            self._remember(fp)

    @classmethod
    def for_run(cls, session: DbSession, since: datetime) -> "Deduplicator":
        rows = session.execute(select(*_FINGERPRINT_COLUMNS).where(Article.created_at >= since))
        return cls(session, (_fingerprint_from_row(row) for row in rows))

    def prefetch(self, source_id: uuid.UUID, candidates: Sequence[NormalizedArticle]) -> None:
        """Load any stored articles that share an exact key with this batch (one query)."""
        if not candidates:
            return
        urls = {c.url for c in candidates}
        normalized = {c.normalized_url for c in candidates}
        hashes = {c.content_hash for c in candidates if c.content_hash}
        guids = {c.guid for c in candidates if c.guid}
        conditions: list[ColumnElement[bool]] = [
            Article.url.in_(urls),
            Article.normalized_url.in_(normalized),
        ]
        if hashes:
            conditions.append(Article.content_hash.in_(hashes))
        if guids:
            conditions.append((Article.source_id == source_id) & Article.guid.in_(guids))
        rows = self._session.execute(select(*_FINGERPRINT_COLUMNS).where(or_(*conditions)))
        for row in rows:
            self._keys.add(_fingerprint_from_row(row))

    def check(self, source_id: uuid.UUID, candidate: NormalizedArticle) -> Decision:
        keys = self._keys
        if (match := keys.urls.get(candidate.url)) is not None:
            return Decision(Verdict.DUPLICATE, MatchReason.EXACT_URL, match)
        if (match := keys.normalized_urls.get(candidate.normalized_url)) is not None:
            return Decision(Verdict.DUPLICATE, MatchReason.NORMALIZED_URL, match)
        if candidate.guid and (match := keys.guids.get((source_id, candidate.guid))) is not None:
            return Decision(Verdict.DUPLICATE, MatchReason.GUID, match)
        if candidate.content_hash and (match := keys.hashes.get(candidate.content_hash)):
            return Decision(Verdict.DUPLICATE, MatchReason.CONTENT_HASH, match)
        return self._check_titles(source_id, title_tokens(candidate.title))

    def _check_titles(self, source_id: uuid.UUID, tokens: frozenset[str]) -> Decision:
        if len(tokens) < MIN_TOKENS_FOR_COMPARISON:
            return Decision(Verdict.NEW)
        best_related: Decision | None = None
        for fp in self._recent.values():
            if len(fp.tokens) < MIN_TOKENS_FOR_COMPARISON:
                continue
            if fp.source_id == source_id:
                score = jaccard(tokens, fp.tokens)
                if score >= DUPLICATE_TITLE_THRESHOLD:
                    return Decision(
                        Verdict.DUPLICATE, MatchReason.SIMILAR_TITLE, fp.article_id, score=score
                    )
                continue
            shared = len(tokens & fp.tokens)
            score = overlap(tokens, fp.tokens)
            is_related = any(shared >= n and score >= t for n, t in RELATED_RULES)
            if is_related and (best_related is None or score > (best_related.score or 0)):
                best_related = Decision(
                    Verdict.RELATED,
                    MatchReason.RELATED_TITLE,
                    fp.article_id,
                    fp.story_cluster_id,
                    score,
                )
        return best_related or Decision(Verdict.NEW)

    def register(self, article: Article) -> None:
        """Make a staged (flushed, uncommitted) article visible to later checks in this run."""
        fp = Fingerprint(
            article_id=article.id,
            source_id=article.source_id,
            url=article.url,
            normalized_url=article.normalized_url,
            guid=article.guid,
            content_hash=article.content_hash,
            tokens=title_tokens(article.title),
            story_cluster_id=article.story_cluster_id,
        )
        self._pending.append(fp)
        self._remember(fp)

    def assign_cluster(self, article_id: uuid.UUID, cluster_id: uuid.UUID) -> None:
        if (fp := self._recent.get(article_id)) is not None:
            self._recent[article_id] = replace(fp, story_cluster_id=cluster_id)

    def commit(self) -> None:
        self._pending.clear()

    def rollback(self) -> None:
        """Forget entries staged in a transaction that was rolled back."""
        for fp in self._pending:
            self._recent.pop(fp.article_id, None)
        self._pending.clear()
        self._keys = _KeyIndex()
        for fp in self._recent.values():
            self._keys.add(fp)

    def _remember(self, fp: Fingerprint) -> None:
        self._recent[fp.article_id] = fp
        self._keys.add(fp)


_FINGERPRINT_COLUMNS = (
    Article.id,
    Article.source_id,
    Article.url,
    Article.normalized_url,
    Article.guid,
    Article.content_hash,
    Article.title,
    Article.story_cluster_id,
)


def _fingerprint_from_row(row: Any) -> Fingerprint:
    return Fingerprint(
        article_id=row.id,
        source_id=row.source_id,
        url=row.url,
        normalized_url=row.normalized_url,
        guid=row.guid,
        content_hash=row.content_hash,
        tokens=title_tokens(row.title),
        story_cluster_id=row.story_cluster_id,
    )
