"""URL validation and canonicalization for deduplication and safe rendering."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ALLOWED_SCHEMES = frozenset({"http", "https"})

# Query parameters that only track the referral and never change the article. Deliberately
# conservative: generic names like ``source``/``id``/``cid`` can identify content on some sites,
# and wrongly merging two articles is worse than missing a duplicate.
TRACKING_PARAM_PREFIXES = ("utm_", "mc_", "pk_", "itm_")
TRACKING_PARAMS = frozenset(
    {
        "fbclid", "gclid", "dclid", "msclkid", "yclid", "igshid", "cmpid", "ncid", "ocid",
        "ref", "ref_src", "taid", "mod", "smid", "smtyp", "guccounter", "__source",
        "sr_share", "traffic_source",
    }
)  # fmt: skip


def is_safe_http_url(value: str | None) -> bool:
    """True for absolute http(s) URLs with a host. Rejects javascript:, data:, relative, etc."""
    if not value or len(value) > 2048 or any(c.isspace() for c in value.strip()):
        return False
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return False
    return parts.scheme.lower() in ALLOWED_SCHEMES and bool(parts.hostname)


def normalize_url(value: str) -> str:
    """Canonical form used to detect the same article behind cosmetically different URLs.

    - lowercases scheme and host, drops ``www.``, default ports, fragments and credentials
    - removes tracking query parameters and sorts the remaining ones
    - strips trailing slashes (except root) and ``/amp`` suffixes
    - treats http and https as equivalent
    """
    parts = urlsplit(value.strip())
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    port = parts.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"

    path = parts.path or "/"
    for suffix in ("/amp", "/amp/"):
        if path.endswith(suffix):
            path = path[: -len(suffix)] or "/"
    if len(path) > 1:
        path = path.rstrip("/")

    query_pairs = [
        (key, val)
        for key, val in parse_qsl(parts.query, keep_blank_values=False)
        if key.lower() not in TRACKING_PARAMS
        and not key.lower().startswith(TRACKING_PARAM_PREFIXES)
    ]
    query = urlencode(sorted(query_pairs))

    return urlunsplit(("https", netloc, path, query, ""))
