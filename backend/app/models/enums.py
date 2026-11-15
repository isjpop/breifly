import enum


class Category(enum.StrEnum):
    FINANCE = "finance"
    TECHNOLOGY = "technology"
    BUSINESS = "business"
    SCIENCE = "science"
    BREAKING_NEWS = "breaking_news"

    @property
    def label(self) -> str:
        return CATEGORY_LABELS[self]


CATEGORY_LABELS: dict[Category, str] = {
    Category.FINANCE: "Finance",
    Category.TECHNOLOGY: "Technology",
    Category.BUSINESS: "Business",
    Category.SCIENCE: "Science",
    Category.BREAKING_NEWS: "Breaking News",
}


class SourceType(enum.StrEnum):
    RSS = "rss"
    API = "api"


class FetchStatus(enum.StrEnum):
    SUCCESS = "success"
    NOT_MODIFIED = "not_modified"
    FAILED = "failed"


class ContentAvailability(enum.StrEnum):
    """How much article text the publisher's feed provided. Nothing is fetched beyond the feed."""

    FEED_CONTENT = "feed_content"  # feed carried article body text (may still be truncated)
    DESCRIPTION_ONLY = "description_only"  # only a teaser / description
    HEADLINE_ONLY = "headline_only"


class ProcessingStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class GenerationStatus(enum.StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INSUFFICIENT_CONTENT = "insufficient_content"


class RunStatus(enum.StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"  # some sources failed
    FAILED = "failed"


class RunTrigger(enum.StrEnum):
    SCHEDULER = "scheduler"
    MANUAL = "manual"


class CategorySource(enum.StrEnum):
    RULES = "rules"  # keyword classifier + source default
    AI = "ai"  # validated model output


class SourceCoverage(enum.StrEnum):
    """What the summary was based on, shown to readers alongside it."""

    ARTICLE_TEXT = "article_text"  # feed carried body text
    EXCERPT = "excerpt"  # only the publisher's short description was available


class UsageStatus(enum.StrEnum):
    SUCCESS = "success"
    INVALID_OUTPUT = "invalid_output"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    ERROR = "error"
