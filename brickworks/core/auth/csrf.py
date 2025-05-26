from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    CSRF Middleware to protect against Cross-Site Request Forgery attacks.
    On unsafe methods (POST, PUT, DELETE) it checks if the CSRF token in the request header matches the CSRF token
    in the session.

    Needs to be added BEFORE the SessionMiddleware, because it needs the session to be available.
    (middleware is executed in the reverse order it is added to the app)
    """

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.method in SAFE_METHODS:
            # no CSRF token is required for safe methods
            return await call_next(request)

        session_csrf_token = request.session.get("csrf_token")
        request_csrf_token = request.headers.get("X-CSRF-Token")

        if not request_csrf_token:
            return JSONResponse(
                content={
                    "detail": [
                        {
                            "loc": ["header", "X-CSRF-Token"],
                            "msg": "CSRF token is missing.",
                            "type": "csrf_token_missing",
                        }
                    ]
                },
                status_code=403,
            )
        elif request_csrf_token != session_csrf_token:
            return JSONResponse(
                content={
                    "detail": [
                        {
                            "loc": ["header", "X-CSRF-Token"],
                            "msg": "CSRF token mismatch.",
                            "type": "csrf_token_mismatch",
                        }
                    ]
                },
                status_code=403,
            )
        else:
            # CSRF token is valid, proceed with the request
            return await call_next(request)
