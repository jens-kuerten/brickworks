import urllib.parse
from contextvars import ContextVar
from types import TracebackType
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from brickworks.core.settings import settings

_auth_context_var: ContextVar[Optional["AuthContext"]] = ContextVar("auth_context", default=None)


def _get_context_var() -> "AuthContext":
    context = _auth_context_var.get()
    if context is None:
        raise RuntimeError("AuthContext not set")
    return context


class AuthContextMeta(type):
    @property
    def user_uuid(cls) -> str | None:
        return _get_context_var().user_uuid

    @property
    def tenant_schema(cls) -> str | None:
        return _get_context_var().tenant_schema


class AuthContext(metaclass=AuthContextMeta):
    def __init__(self, user_uuid: str | None = None, tenant_schema: str | None = None) -> None:
        self.user_uuid = user_uuid
        self.tenant_schema = tenant_schema or settings.MASTER_DB_SCHEMA
        self.token = _auth_context_var.set(self)

    async def __aenter__(self) -> type["AuthContext"]:
        return type(self)

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None
    ) -> None:
        _auth_context_var.reset(self.token)


class AuthContextMiddleware(BaseHTTPMiddleware):
    async def _extract_tenant_from_request(self, request: Request) -> str | None:
        """
        Extract tenant schema from the request.
        Get the host domain and map it to the tenant schema.
        If the request is not for a tenant, return the master schema.
        """
        host_header = request.headers.get("host", "")
        # Prepend '//' so urlparse treats host_header as a netloc (hostname:port)
        parsed = urllib.parse.urlparse(f"//{host_header}")
        domain = parsed.hostname or ""
        if not domain:
            return None

        from brickworks.core.models.tenant_model import get_domain_schema_mapping

        mapping = await get_domain_schema_mapping()
        return mapping.get(domain)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if settings.MULTI_TENANCY_ENABLED:
            tenant_schema = await self._extract_tenant_from_request(request)
        else:
            tenant_schema = settings.MASTER_DB_SCHEMA
        if not tenant_schema:
            return Response(
                "Tenant not found",
                status_code=404,
                headers={"Content-Type": "text/plain"},
            )
        async with auth_context(
            user_uuid=request.session.get("user_uuid"), tenant_schema=await self._extract_tenant_from_request(request)
        ):
            response = await call_next(request)
        return response


auth_context = AuthContext
