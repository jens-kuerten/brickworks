import urllib.parse
from contextvars import ContextVar
from types import TracebackType
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from brickworks.core.settings import settings

_execution_context_var: ContextVar[Optional["ExecutionContext"]] = ContextVar("execution_context", default=None)


def _get_context_var() -> "ExecutionContext":
    context = _execution_context_var.get()
    if context is None:
        raise RuntimeError("ExecutionContext not set")
    return context


class ExecutionContextMeta(type):
    @property
    def user_uuid(cls) -> str | None:
        return _get_context_var().user_uuid

    @user_uuid.setter
    def user_uuid(cls, value: str | None) -> None:
        # the user_uuid might be set later, when the session middleware has processed the request
        context = _get_context_var()
        context.user_uuid = value
        _execution_context_var.set(context)

    @property
    def tenant_schema(cls) -> str | None:
        return _get_context_var().tenant_schema

    @property
    def request(cls) -> Request | None:
        return _get_context_var().request


class ExecutionContext(metaclass=ExecutionContextMeta):
    def __init__(
        self, user_uuid: str | None = None, tenant_schema: str | None = None, request: Request | None = None
    ) -> None:
        self.user_uuid = user_uuid
        self.tenant_schema = tenant_schema or settings.MASTER_DB_SCHEMA
        self.token = _execution_context_var.set(self)
        self.request = request

    async def __aenter__(self) -> type["ExecutionContext"]:
        return type(self)

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None
    ) -> None:
        _execution_context_var.reset(self.token)


class ExecutionContextMiddleware(BaseHTTPMiddleware):
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
        async with execution_context(
            user_uuid=None, tenant_schema=await self._extract_tenant_from_request(request), request=request
        ):
            response = await call_next(request)
        return response


execution_context = ExecutionContext
