"""Consistent JSON response envelopes.

Success: ``{"data": ..., "meta": {...}}``
Error:   ``{"error": {"code": "...", "message": "...", "details": {...}}}``
"""

from typing import Any

from flask import Response, jsonify


def success(
    data: Any, *, meta: dict[str, Any] | None = None, status: int = 200
) -> tuple[Response, int]:
    body: dict[str, Any] = {"data": data}
    if meta is not None:
        body["meta"] = meta
    return jsonify(body), status


def error(
    code: str, message: str, *, status: int, details: dict[str, Any] | None = None
) -> tuple[Response, int]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if details:
        payload["details"] = details
    return jsonify({"error": payload}), status
