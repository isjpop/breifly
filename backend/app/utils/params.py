"""Turn query strings into validated Pydantic models (or a 400 with field-level details)."""

import uuid
from typing import Any

from pydantic import BaseModel, ValidationError
from werkzeug.datastructures import MultiDict

from app.utils.errors import ApiError


def parse_params[ParamsT: BaseModel](model: type[ParamsT], args: MultiDict[str, str]) -> ParamsT:
    raw: dict[str, Any] = {}
    for key in args:
        values = args.getlist(key)
        raw[key] = values[0] if len(values) == 1 else values
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        details = {
            ".".join(str(p) for p in err["loc"]) or "query": err["msg"] for err in exc.errors()
        }
        raise ApiError(
            "validation_error", "Invalid query parameters.", status=400, details=details
        ) from exc


def parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ApiError("invalid_id", "The identifier is not a valid UUID.", status=400) from exc
