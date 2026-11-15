"""Rule-based categorization: a free, deterministic first pass for every article.

Runs without the LLM so articles are categorized even when AI is disabled, over budget, or the
article has too little text to summarize. A validated AI category replaces it later.
"""

import re

from app.models.enums import Category

# Keywords are matched as whole words/phrases, case-insensitively. Title hits weigh most.
KEYWORDS: dict[Category, tuple[str, ...]] = {
    Category.FINANCE: (
        "stock", "stocks", "market", "markets", "shares", "investor", "investors", "earnings",
        "fed", "federal reserve", "interest rate", "interest rates", "rate cut", "inflation",
        "bond", "bonds", "treasury", "yields", "nasdaq", "s&p", "s&p 500", "dow", "crypto",
        "bitcoin", "bank", "banks", "trading", "etf", "dividend", "currency", "dollar", "gdp",
        "recession", "wall street", "credit", "portfolio", "hedge fund", "tariff", "tariffs",
    ),
    Category.TECHNOLOGY: (
        "ai", "artificial intelligence", "software", "app", "apps", "chip", "chips",
        "semiconductor", "nvidia", "apple", "google", "microsoft", "openai", "cyberattack",
        "cybersecurity", "hack", "hackers", "smartphone", "iphone", "android", "cloud",
        "data center", "data centers", "robot", "robots", "robotics", "quantum computing",
        "llm", "chatbot", "algorithm", "browser", "windows", "linux", "gpu", "processor",
    ),
    Category.BUSINESS: (
        "ceo", "company", "companies", "acquisition", "acquire", "acquires", "merger", "deal",
        "startup", "startups", "funding", "raises", "layoffs", "revenue", "retail", "antitrust",
        "lawsuit", "executive", "board", "ipo", "valuation", "venture", "supply chain",
        "workers", "union", "profit", "sales",
    ),
    Category.SCIENCE: (
        "research", "researchers", "scientists", "study", "nasa", "space", "spacex", "rocket",
        "starship", "climate", "physics", "biology", "gene", "genetic", "vaccine", "medical",
        "fusion", "telescope", "species", "astronomers", "mars", "moon", "lunar", "orbit",
        "disease", "cancer", "drug", "clinical trial", "biotech", "fossil", "asteroid",
    ),
    Category.BREAKING_NEWS: (
        "breaking", "live updates", "earthquake", "hurricane", "tsunami", "wildfire",
        "shooting", "explosion", "evacuation", "evacuated", "ground stop", "killed",
        "state of emergency", "outage", "invasion", "ceasefire", "coup",
    ),
}  # fmt: skip

TITLE_WEIGHT = 3
TAG_WEIGHT = 2
BODY_WEIGHT = 1


def _patterns() -> dict[Category, re.Pattern[str]]:
    compiled = {}
    for category, words in KEYWORDS.items():
        alternation = "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
        compiled[category] = re.compile(rf"(?<![\w&])(?:{alternation})(?![\w&])", re.IGNORECASE)
    return compiled


_PATTERNS = _patterns()


def categorize(
    *, title: str, description: str | None, tags: list[str], default: Category
) -> Category:
    scores: dict[Category, int] = {}
    tag_text = " ".join(tags)
    for category, pattern in _PATTERNS.items():
        score = (
            TITLE_WEIGHT * len(pattern.findall(title))
            + TAG_WEIGHT * len(pattern.findall(tag_text))
            + BODY_WEIGHT * len(pattern.findall(description or ""))
        )
        if category is Category.BREAKING_NEWS and not pattern.search(title):
            score = 0  # breaking news must be evident from the headline itself
        scores[category] = score

    best = max(scores.values())
    if best == 0:
        return default
    leaders = [c for c, s in scores.items() if s == best]
    return default if default in leaders else leaders[0]
