import httpx
import pytest

from app.ingestion.http import FeedFetcher, FeedFetchError
from tests.feeds import mock_transport, xml_response

URL = "https://feeds.example.com/rss"


def make_fetcher(routes, *, calls=None, delays=None, **kwargs) -> FeedFetcher:
    client = httpx.Client(transport=mock_transport(routes, calls))
    sleeps = delays if delays is not None else []
    return FeedFetcher(client, sleep=sleeps.append, **{"max_retries": 3, **kwargs})


def sequence(*responses: httpx.Response | Exception):
    queue = list(responses)

    def handler(_request: httpx.Request) -> httpx.Response:
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return handler


def test_successful_fetch_returns_body_and_validators() -> None:
    fetcher = make_fetcher({URL: xml_response(b"<rss/>", headers={"ETag": '"v1"'})})
    result = fetcher.fetch(URL)
    assert result.status_code == 200
    assert result.body == b"<rss/>"
    assert result.etag == '"v1"'
    assert not result.not_modified


def test_conditional_request_headers_and_304() -> None:
    calls: list[httpx.Request] = []
    fetcher = make_fetcher({URL: httpx.Response(304)}, calls=calls)
    result = fetcher.fetch(URL, etag='"v1"', last_modified="Sat, 14 Nov 2026 00:00:00 GMT")

    assert result.not_modified
    assert calls[0].headers["If-None-Match"] == '"v1"'
    assert calls[0].headers["If-Modified-Since"] == "Sat, 14 Nov 2026 00:00:00 GMT"
    assert result.etag == '"v1"'  # preserved when the 304 omits it


def test_transient_errors_retry_with_exponential_backoff() -> None:
    delays: list[float] = []
    handler = sequence(httpx.Response(503), httpx.Response(502), xml_response(b"<rss/>"))
    fetcher = make_fetcher({URL: handler}, delays=delays, backoff_base=1.0)

    assert fetcher.fetch(URL).body == b"<rss/>"
    assert delays == [1.0, 2.0]


def test_retry_after_header_is_honoured_and_capped() -> None:
    delays: list[float] = []
    handler = sequence(httpx.Response(429, headers={"Retry-After": "120"}), xml_response(b"<rss/>"))
    fetcher = make_fetcher({URL: handler}, delays=delays, backoff_max=30.0)

    fetcher.fetch(URL)
    assert delays == [30.0]


def test_timeouts_retry_then_fail_with_safe_message() -> None:
    delays: list[float] = []
    timeout = httpx.ReadTimeout("slow")
    fetcher = make_fetcher({URL: sequence(timeout, timeout, timeout)}, delays=delays, max_retries=2)

    with pytest.raises(FeedFetchError, match="timed out \\(after 3 attempts\\)"):
        fetcher.fetch(URL)
    assert len(delays) == 2


def test_client_errors_are_not_retried() -> None:
    calls: list[httpx.Request] = []
    fetcher = make_fetcher({URL: httpx.Response(403)}, calls=calls)
    with pytest.raises(FeedFetchError, match="HTTP 403"):
        fetcher.fetch(URL)
    assert len(calls) == 1


def test_oversized_responses_are_rejected() -> None:
    fetcher = make_fetcher({URL: xml_response(b"x" * 20_000)}, max_bytes=10_000)
    with pytest.raises(FeedFetchError, match="exceeds"):
        fetcher.fetch(URL)
