"""OpenAPI 3.1 document for the REST API, generated from the Pydantic response models so the
documentation cannot drift from what the endpoints actually return.

Served at ``GET /api/openapi.json``. A test asserts every ``/api`` route is documented.
"""

from typing import Any

from flask import Blueprint, Response, jsonify
from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from app.models.enums import Category
from app.schemas.api import (
    ArticleCard,
    ArticleDetail,
    Briefing,
    CategoryOut,
    Pagination,
    SourceOut,
)

bp = Blueprint("docs", __name__, url_prefix="/api")

REF = "#/components/schemas/{model}"


def _ref(model: type[BaseModel]) -> dict[str, str]:
    return {"$ref": REF.format(model=model.__name__)}


def _envelope(data: dict[str, Any], meta: dict[str, Any] | None = None) -> dict[str, Any]:
    properties: dict[str, Any] = {"data": data}
    if meta:
        properties["meta"] = meta
    return {"type": "object", "properties": properties, "required": ["data"]}


def _ok(description: str, data: dict[str, Any], meta: dict[str, Any] | None = None) -> dict:
    return {
        "description": description,
        "content": {"application/json": {"schema": _envelope(data, meta)}},
    }


def _err(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
    }


def _query(name: str, schema: dict[str, Any], description: str, required: bool = False) -> dict:
    return {
        "name": name,
        "in": "query",
        "required": required,
        "schema": schema,
        "description": description,
    }


PAGE_PARAMS = [
    _query("page", {"type": "integer", "minimum": 1, "maximum": 1000, "default": 1}, "Page."),
    _query(
        "per_page", {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}, "Page size."
    ),
]
PAGINATION_META = {"type": "object", "properties": {"pagination": _ref(Pagination)}}
ID_PARAM = {
    "name": "id",
    "in": "path",
    "required": True,
    "schema": {"type": "string", "format": "uuid"},
}
CARD_LIST = {"type": "array", "items": _ref(ArticleCard)}
BAD_REQUEST = _err("Invalid parameters (`validation_error`) or identifier (`invalid_id`).")


def build_openapi() -> dict[str, Any]:
    _, schemas = models_json_schema(
        [
            (m, "serialization")
            for m in (ArticleCard, ArticleDetail, Briefing, CategoryOut, SourceOut, Pagination)
        ],
        ref_template=REF,
    )
    components = schemas.get("$defs", {})
    components["Error"] = {
        "type": "object",
        "properties": {
            "error": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "message": {"type": "string"},
                    "details": {"type": "object"},
                },
                "required": ["code", "message"],
            }
        },
        "required": ["error"],
    }
    categories = {"type": "string", "enum": [c.value for c in Category]}

    paths: dict[str, Any] = {
        "/api/health": {
            "get": {
                "summary": "Liveness and database readiness",
                "responses": {
                    "200": _ok("Healthy", {"type": "object"}),
                    "503": _ok("Database unavailable (`status: degraded`)", {"type": "object"}),
                },
            }
        },
        "/api/articles": {
            "get": {
                "summary": "List articles",
                "parameters": [
                    *PAGE_PARAMS,
                    _query("category", categories, "Filter by category slug."),
                    _query("source", {"type": "string"}, "Comma-separated source slugs."),
                    _query("from", {"type": "string"}, "Start (YYYY-MM-DD or ISO datetime)."),
                    _query("to", {"type": "string"}, "End; a bare date includes that day."),
                    _query(
                        "sort",
                        {
                            "type": "string",
                            "enum": ["importance", "recent"],
                            "default": "importance",
                        },
                        "Order.",
                    ),
                ],
                "responses": {
                    "200": _ok("Articles", CARD_LIST, PAGINATION_META),
                    "400": BAD_REQUEST,
                },
            }
        },
        "/api/articles/top": {
            "get": {
                "summary": "Highest-ranked stories (one per story cluster)",
                "parameters": [
                    _query(
                        "limit",
                        {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                        "Count.",
                    ),
                    _query(
                        "hours",
                        {"type": "integer", "minimum": 1, "maximum": 168, "default": 24},
                        "Window.",
                    ),
                ],
                "responses": {"200": _ok("Top stories", CARD_LIST), "400": BAD_REQUEST},
            }
        },
        "/api/articles/search": {
            "get": {
                "summary": "Full-text search (headline, text, AI summary, entities, publisher)",
                "parameters": [
                    _query(
                        "q",
                        {"type": "string", "minLength": 2, "maxLength": 200},
                        'Query; supports "phrases", -exclusions and OR.',
                        required=True,
                    ),
                    *PAGE_PARAMS,
                    _query(
                        "sort",
                        {"type": "string", "enum": ["relevance", "recent"], "default": "relevance"},
                        "Order.",
                    ),
                ],
                "responses": {
                    "200": _ok("Matches", CARD_LIST, PAGINATION_META),
                    "400": BAD_REQUEST,
                },
            }
        },
        "/api/articles/{id}": {
            "get": {
                "summary": "Article with summary and related coverage",
                "parameters": [ID_PARAM],
                "responses": {
                    "200": _ok("Article", _ref(ArticleDetail)),
                    "400": BAD_REQUEST,
                    "404": _err("Not found"),
                },
            }
        },
        "/api/articles/{id}/summarize": {
            "post": {
                "summary": "Regenerate an article's AI summary (admin)",
                "security": [{"adminToken": []}],
                "parameters": [ID_PARAM],
                "responses": {
                    "200": _ok("Regenerated", _ref(ArticleDetail)),
                    "400": BAD_REQUEST,
                    "401": _err("Missing or invalid token"),
                    "403": _err("Admin API disabled (no ADMIN_API_TOKEN configured)"),
                    "404": _err("Not found"),
                    "409": _err("Regeneration already in progress"),
                    "429": _err("Rate limited; see Retry-After"),
                    "502": _err("Provider produced no valid summary; previous summary kept"),
                    "503": _err("AI not configured or provider unavailable"),
                },
            }
        },
        "/api/categories": {
            "get": {
                "summary": "Categories with recent article counts",
                "responses": {
                    "200": _ok("Categories", {"type": "array", "items": _ref(CategoryOut)})
                },
            }
        },
        "/api/sources": {
            "get": {
                "summary": "Configured news sources and fetch status",
                "responses": {"200": _ok("Sources", {"type": "array", "items": _ref(SourceOut)})},
            }
        },
        "/api/briefing/today": {
            "get": {
                "summary": "Today's briefing: top stories and best of each category",
                "responses": {"200": _ok("Briefing", _ref(Briefing))},
            }
        },
        "/api/openapi.json": {
            "get": {
                "summary": "This document (served without the data envelope)",
                "responses": {
                    "200": {
                        "description": "OpenAPI document",
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    }
                },
            }
        },
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Briefly API",
            "version": "1.0.0",
            "description": "AI-summarized news. Responses use a {data, meta} / {error} envelope.",
        },
        "paths": paths,
        "components": {
            "schemas": components,
            "securitySchemes": {"adminToken": {"type": "http", "scheme": "bearer"}},
        },
    }


@bp.get("/openapi.json")
def openapi() -> Response:
    # Served bare (no {data} envelope) so OpenAPI tooling can consume it directly.
    return jsonify(build_openapi())
