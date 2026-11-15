"""Security headers for API responses. (The web server adds CSP for the frontend.)"""

from flask import Flask, Response, abort, request

API_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    # The API serves JSON only; forbid it from ever being rendered as an active document.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


def register_security_headers(app: Flask) -> None:
    @app.before_request
    def reject_oversized_bodies() -> None:
        # Flask only enforces MAX_CONTENT_LENGTH when a view reads the body, and no endpoint
        # does, so check the declared length up front.
        limit = app.config.get("MAX_CONTENT_LENGTH")
        if limit and request.content_length and request.content_length > limit:
            abort(413)

    @app.after_request
    def add_headers(response: Response) -> Response:
        for name, value in API_HEADERS.items():
            response.headers.setdefault(name, value)
        if request.method != "GET":
            response.headers["Cache-Control"] = "no-store"
        return response
