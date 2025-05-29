import json
from base64 import b64decode, b64encode
from typing import Any
from uuid import uuid4

import itsdangerous
from fastapi import Request
from itsdangerous.exc import BadTimeSignature, SignatureExpired
from starlette.datastructures import MutableHeaders
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from brickworks.core.auth.executioncontext import execution_context
from brickworks.core.cache import cache
from brickworks.core.settings import settings


async def get_session(request: Request) -> dict[str, Any]:
    """
    Can be used as a dependency to get the session data.
    """
    return request.session


class SessionMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        cookie_name: str,
        max_age: int = 14 * 24 * 60 * 60,  # 14 days, in seconds
        same_site: str = "lax",
        https_only: bool = False,
        domain: str | None = None,
    ) -> None:
        """Session Middleware, that stores the session data in the cache.
        This allows us to invalidate sessions by deleting the session data from the cache.
        The session id is stored in a cookie, which is signed with a secret key, to prevent tampering.

        Args:
            app: The ASGIApp
            cookie_name: The name of the cookie used to store the session id.
            max_age: The Max-Age of the cookie (Default to 14 days).
            same_site: The SameSite attribute of the cookie (Defaults to lax).
            https_only: Whether to make the cookie https only (Defaults to False).
            domain: The domain associated to the cookie (Default to None).
        """
        self.app = app
        self.cache_namespace = "session"
        self.signer = itsdangerous.TimestampSigner(settings.SESSION_SECRET)
        self.cookie_name = cookie_name
        self.max_age = max_age
        self.domain = domain

        self._cookie_session_id_field = "_cssid"

        self.security_flags = f"httponly; samesite={same_site}"
        if https_only:  # Secure flag can be used with HTTPS only
            self.security_flags += "; secure"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):  # pragma: no cover
            await self.app(scope, receive, send)
            return

        connection = HTTPConnection(scope)
        initial_session_was_empty = True

        # Always use the same session id if present, otherwise generate a new one
        if self.cookie_name in connection.cookies:
            data = connection.cookies[self.cookie_name].encode("utf-8")
            try:
                data = self.signer.unsign(data, max_age=self.max_age)
                session_key = json.loads(b64decode(data)).get(self._cookie_session_id_field)
                if not isinstance(session_key, str) or not session_key:
                    session_key = str(uuid4())
                scope["session"] = json.loads(await cache.get_key(session_key, self.cache_namespace) or "{}")
                scope["__session_key"] = session_key
                if scope["session"] is None:
                    scope["session"] = {}

                # Update execution_context.user_uuid after loading session
                user_uuid = scope["session"].get("user_uuid")
                execution_context.user_uuid = user_uuid

                initial_session_was_empty = False
            except (BadTimeSignature, SignatureExpired, json.JSONDecodeError):
                session_key = str(uuid4())
                scope["session"] = {}
                scope["__session_key"] = session_key
        else:
            session_key = str(uuid4())
            scope["session"] = {}
            scope["__session_key"] = session_key

        async def send_wrapper(message: Message, **_: Any) -> None:  # noqa: ANN401
            if message["type"] == "http.response.start":
                session_key = scope.get("__session_key")
                if not isinstance(session_key, str) or not session_key:
                    session_key = str(uuid4())

                if scope["session"]:
                    await cache.set_key(
                        session_key, json.dumps(scope["session"]), namespace=self.cache_namespace, expire=self.max_age
                    )
                    cookie_data = {self._cookie_session_id_field: session_key}

                    data = b64encode(json.dumps(cookie_data).encode("utf-8"))
                    data = self.signer.sign(data)

                    headers = MutableHeaders(scope=message)
                    header_value = self._construct_cookie(data=data)
                    headers.append("Set-Cookie", header_value)

                elif not initial_session_was_empty:
                    await cache.delete_key(session_key, namespace=self.cache_namespace)

                    headers = MutableHeaders(scope=message)
                    header_value = self._construct_cookie(data=None)
                    headers.append("Set-Cookie", header_value)

                else:
                    # Always refresh the cookie expiry even if session is empty
                    cookie_data = {self._cookie_session_id_field: session_key}
                    data = b64encode(json.dumps(cookie_data).encode("utf-8"))
                    data = self.signer.sign(data)
                    headers = MutableHeaders(scope=message)
                    header_value = self._construct_cookie(data=data)
                    headers.append("Set-Cookie", header_value)

            await send(message)

        await self.app(scope, receive, send_wrapper)

    def _construct_cookie(self, data: bytes | None = None) -> str:
        if data is None:
            # If the session is empty, we need to delete the cookie
            cookie = (
                f"{self.cookie_name}=null; Path=/; Expires="
                f"Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; {self.security_flags}"
            )
        else:
            cookie = f"{self.cookie_name}={data.decode('utf-8')}; Path=/; Max-Age={self.max_age}; {self.security_flags}"
        if self.domain:
            cookie = f"{cookie}; Domain={self.domain}"
        return cookie
