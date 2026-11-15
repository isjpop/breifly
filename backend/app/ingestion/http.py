"""Polite, resilient feed downloads.

- Conditional GET (ETag / Last-Modified) so unchanged feeds cost one 304.
- Timeouts on every request; retries with exponential backoff for transient failures only
  (network errors, 408/425/429/5xx), honouring ``Retry-After``.
- Response size cap so a misbehaving server cannot exhaust memory.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
ACCEPT_HEADER = (
    "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.1"
)


class FeedFetchError(Exception):
    """A feed could not be downloaded. ``message`` is safe to store and display."""


@dataclass(frozen=True)
class FetchResult:
    status_code: int
    body: bytes | None
    etag: str | None
    last_modified: str | None

    @property
    def not_modified(self) -> bool:
        return self.status_code == 304


class _RetryableError(Exception):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def build_http_client(settings: Settings) -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(settings.http_timeout_seconds, connect=5.0),
        follow_redirects=True,
        max_redirects=5,
        headers={"User-Agent": settings.ingestion_user_agent, "Accept": ACCEPT_HEADER},
    )


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None  # HTTP-date form: fall back to our own backoff


class FeedFetcher:
    def __init__(
        self,
        client: httpx.Client,
        *,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        backoff_max: float = 30.0,
        max_bytes: int = 5_000_000,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self._max_bytes = max_bytes
        self._sleep = sleep

    @classmethod
    def from_settings(
        cls, client: httpx.Client, settings: Settings, **overrides: object
    ) -> "FeedFetcher":
        options: dict[str, object] = {
            "max_retries": settings.http_max_retries,
            "backoff_base": settings.http_backoff_base_seconds,
            "backoff_max": settings.http_backoff_max_seconds,
            "max_bytes": settings.feed_max_bytes,
            **overrides,
        }
        return cls(client, **options)  # type: ignore[arg-type]

    def fetch(
        self, url: str, *, etag: str | None = None, last_modified: str | None = None
    ) -> FetchResult:
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        attempt = 0
        while True:
            try:
                return self._attempt(url, headers)
            except _RetryableError as exc:
                if attempt >= self._max_retries:
                    raise FeedFetchError(f"{exc} (after {attempt + 1} attempts)") from exc
                delay = min(self._backoff_max, self._backoff_base * (2**attempt))
                if exc.retry_after is not None:
                    delay = min(self._backoff_max, max(delay, exc.retry_after))
                logger.warning("Fetch of %s failed (%s); retrying in %.1fs", url, exc, delay)
                self._sleep(delay)
                attempt += 1

    def _attempt(self, url: str, headers: dict[str, str]) -> FetchResult:
        try:
            with self._client.stream("GET", url, headers=headers) as response:
                status = response.status_code
                if status == 304:
                    return FetchResult(304, None, *self._validators(response, headers))
                if status in RETRYABLE_STATUS:
                    raise _RetryableError(
                        f"HTTP {status}", _parse_retry_after(response.headers.get("Retry-After"))
                    )
                if not 200 <= status < 300:
                    raise FeedFetchError(f"HTTP {status}")
                body = self._read_capped(response)
                return FetchResult(status, body, *self._validators(response, {}))
        except httpx.TimeoutException as exc:
            raise _RetryableError("request timed out") from exc
        except httpx.TransportError as exc:
            raise _RetryableError(f"network error: {type(exc).__name__}") from exc
        except httpx.TooManyRedirects as exc:
            raise FeedFetchError("too many redirects") from exc

    def _read_capped(self, response: httpx.Response) -> bytes:
        declared = response.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > self._max_bytes:
            raise FeedFetchError(f"response exceeds {self._max_bytes} bytes")
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > self._max_bytes:
                raise FeedFetchError(f"response exceeds {self._max_bytes} bytes")
            chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _validators(
        response: httpx.Response, sent: dict[str, str]
    ) -> tuple[str | None, str | None]:
        # On 304 some servers omit validators; keep the ones we sent.
        etag = response.headers.get("ETag") or sent.get("If-None-Match")
        last_modified = response.headers.get("Last-Modified") or sent.get("If-Modified-Since")
        return etag, last_modified
