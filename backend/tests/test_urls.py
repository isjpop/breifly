import pytest

from app.utils.urls import is_safe_http_url, normalize_url


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("https://www.example.com/story/", "http://example.com/story"),
        ("https://example.com/story?utm_source=rss&utm_medium=x", "https://example.com/story"),
        ("https://example.com/story#comments", "https://example.com/story"),
        ("https://EXAMPLE.com:443/story", "https://example.com/story"),
        ("https://example.com/story?b=2&a=1", "https://example.com/story?a=1&b=2"),
        ("https://example.com/story/amp", "https://example.com/story"),
        ("https://example.com/s?fbclid=abc&id=7", "https://example.com/s?id=7"),
    ],
)
def test_equivalent_urls_normalize_identically(a: str, b: str) -> None:
    assert normalize_url(a) == normalize_url(b)


def test_content_identifying_query_params_are_kept() -> None:
    assert normalize_url("https://example.com/a?id=1") != normalize_url(
        "https://example.com/a?id=2"
    )
    assert normalize_url("https://example.com/a?source=x") != normalize_url("https://example.com/a")


def test_different_paths_stay_distinct() -> None:
    assert normalize_url("https://example.com/a") != normalize_url("https://example.com/b")


@pytest.mark.parametrize(
    "url",
    ["https://example.com/a", "http://example.com", "https://sub.example.co.uk/x?y=1"],
)
def test_safe_urls(url: str) -> None:
    assert is_safe_http_url(url)


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "javascript:alert(1)",
        "data:text/html,hi",
        "/relative/path",
        "ftp://example.com/file",
        "https://",
        "https://exa mple.com",
        "https://example.com/" + "a" * 3000,
    ],
)
def test_unsafe_urls(url: str | None) -> None:
    assert not is_safe_http_url(url)
