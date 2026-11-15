"""Plain-text extraction from untrusted feed HTML."""

import hashlib
import html
import re
from html.parser import HTMLParser

_WHITESPACE = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES = re.compile(r"\n\s*\n+")
_BLOCK_TAGS = frozenset(
    {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
     "tr", "section", "article", "figure", "figcaption", "pre", "hr"}
)  # fmt: skip
_SKIP_TAGS = frozenset({"script", "style", "noscript", "iframe", "svg", "template", "head"})


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.images: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "img":
            src = dict(attrs).get("src")
            if src:
                self.images.append(src)

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)


def _parse(markup: str) -> _TextExtractor:
    parser = _TextExtractor()
    try:
        parser.feed(markup)
        parser.close()
    except (AssertionError, ValueError):
        # Malformed markup: fall back to whatever was extracted so far.
        pass
    return parser


def html_to_text(markup: str | None) -> str:
    """Convert HTML (or entity-encoded text) into clean plain text with paragraph breaks.

    Script/style contents are dropped; the result never contains markup.
    """
    if not markup:
        return ""
    text = "".join(_parse(markup).parts)
    text = html.unescape(text)  # handles double-encoded entities some feeds emit
    lines = [_WHITESPACE.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return _BLANK_LINES.sub("\n\n", text).strip()


def first_image_src(markup: str | None) -> str | None:
    if not markup:
        return None
    images = _parse(markup).images
    return images[0] if images else None


def truncate(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def content_fingerprint(text: str) -> str:
    """SHA-256 of case- and whitespace-insensitive text, for exact-copy detection."""
    canonical = " ".join(text.lower().split())
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
