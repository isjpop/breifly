import re

from flask import Flask
from flask.testing import FlaskClient


def test_openapi_document_is_served_bare(client: FlaskClient) -> None:
    spec = client.get("/api/openapi.json").get_json()
    assert spec["openapi"].startswith("3.1")
    assert "ArticleCard" in spec["components"]["schemas"]
    assert "Error" in spec["components"]["schemas"]


def test_every_api_route_is_documented(app: Flask, client: FlaskClient) -> None:
    spec = client.get("/api/openapi.json").get_json()
    documented = {(path, method.upper()) for path, ops in spec["paths"].items() for method in ops}
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api"):
            continue
        path = re.sub(r"<(?:[^:>]+:)?([^>]+)>", "{id}", rule.rule)
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            assert (path, method) in documented, f"{method} {path} is not in the OpenAPI spec"


def test_all_schema_refs_resolve(client: FlaskClient) -> None:
    spec = client.get("/api/openapi.json").get_json()
    text = str(spec)
    for name in re.findall(r"#/components/schemas/(\w+)", text):
        assert name in spec["components"]["schemas"], f"dangling $ref {name}"
