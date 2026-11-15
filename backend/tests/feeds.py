"""Helpers for building synthetic feeds and mocked HTTP responses in tests."""

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import feedparser
import httpx

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def rss(items: list[dict[str, Any]], *, extra_ns: str = "") -> bytes:
    """Build a minimal RSS 2.0 document. Item keys: title, link, guid, pubDate, description,
    and ``raw`` (pre-escaped XML inserted verbatim). ``None`` values omit the element."""
    parts = []
    for item in items:
        fields = []
        for key in ("title", "link", "guid", "pubDate", "description"):
            if item.get(key) is not None:
                fields.append(f"<{key}>{escape(str(item[key]))}</{key}>")
        fields.append(item.get("raw", ""))
        parts.append(f"<item>{''.join(fields)}</item>")
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0" {extra_ns}><channel>'
        f"<title>Test</title><link>https://example.com</link><description>t</description>"
        f"{''.join(parts)}</channel></rss>"
    ).encode()


def parse_entries(body: bytes) -> list[Any]:
    return list(feedparser.parse(body).entries)


Route = httpx.Response | Callable[[httpx.Request], httpx.Response] | Exception


def mock_transport(routes: Mapping[str, Route], calls: list[httpx.Request] | None = None):
    """httpx transport serving fixed responses per URL; unknown URLs return 404."""

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        route = routes.get(str(request.url))
        if route is None:
            return httpx.Response(404)
        if isinstance(route, Exception):
            raise route
        if callable(route):
            return route(request)
        return route

    return httpx.MockTransport(handler)


def xml_response(body: bytes, status: int = 200, headers: dict[str, str] | None = None):
    return httpx.Response(
        status, content=body, headers={"Content-Type": "application/rss+xml", **(headers or {})}
    )
