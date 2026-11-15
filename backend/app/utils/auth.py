"""Bearer-token protection for administrative endpoints."""

import hmac
from collections.abc import Callable
from functools import wraps
from typing import Any, cast

from flask import current_app, request

from app.config import Settings
from app.utils.errors import ApiError


def require_admin_token[F: Callable[..., Any]](view: F) -> F:
    """Require ``Authorization: Bearer <ADMIN_API_TOKEN>``.

    If no token is configured the endpoint is disabled entirely (fail closed). The comparison
    is constant-time so the token cannot be recovered by timing responses.
    """

    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        settings: Settings = current_app.config["BRIEFLY_SETTINGS"]
        expected = settings.admin_api_token.get_secret_value() if settings.admin_api_token else ""
        if not expected:
            raise ApiError(
                "admin_api_disabled",
                "This endpoint is disabled: ADMIN_API_TOKEN is not configured.",
                status=403,
            )
        header = request.headers.get("Authorization", "")
        scheme, _, supplied = header.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(
            supplied.strip().encode(), expected.encode()
        ):
            raise ApiError(
                "unauthorized",
                "A valid admin bearer token is required.",
                status=401,
                headers={"WWW-Authenticate": 'Bearer realm="briefly-admin"'},
            )
        return view(*args, **kwargs)

    return cast(F, wrapper)
