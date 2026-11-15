from app.utils.text import content_fingerprint, first_image_src, html_to_text, truncate


def test_html_to_text_strips_markup_scripts_and_decodes_entities() -> None:
    html = "<p>Hello <b>world</b> &amp; friends</p><script>evil()</script><p>Second</p>"
    assert html_to_text(html) == "Hello world & friends\n\nSecond"


def test_html_to_text_handles_double_encoded_entities_and_empty_input() -> None:
    assert html_to_text("AT&amp;amp;T") == "AT&T"
    assert html_to_text(None) == ""
    assert html_to_text("") == ""


def test_html_to_text_never_returns_markup_from_malformed_html() -> None:
    text = html_to_text("<div><p>Unclosed <a href='x'>link<img src=y")
    assert "<" not in text and "Unclosed" in text


def test_first_image_src() -> None:
    assert first_image_src('<p>x</p><img src="https://a/b.jpg">') == "https://a/b.jpg"
    assert first_image_src("<p>no image</p>") is None


def test_truncate() -> None:
    assert truncate("short", 10) == "short"
    assert truncate("a" * 20, 10) == "a" * 9 + "…"
    assert truncate(None, 5) is None


def test_content_fingerprint_ignores_case_and_whitespace() -> None:
    assert content_fingerprint("Hello   World\n") == content_fingerprint("hello world")
    assert content_fingerprint("hello world") != content_fingerprint("hello there")
