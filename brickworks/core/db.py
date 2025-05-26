import os
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from brickworks.core.settings import settings

_SESSION: async_sessionmaker[AsyncSession] | None = None


@dataclass
class DBSessionContext:
    session: AsyncSession
    on_post_committed: list[Callable[[], Awaitable[Any]]] = field(
        default_factory=list
    )  # list of async functions called after committing the session


_session_context_var: ContextVar[DBSessionContext | None] = ContextVar("_session_context", default=None)

CURRENT_FILE_PATH = os.path.abspath(__file__)


def get_db_url() -> str:
    return f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}/{settings.DB_NAME}"


class MissingSessionError(Exception):
    """Exception raised for when the user tries to access a database session before it is created."""

    def __init__(self) -> None:
        msg = """
        No session found! Either you are not currently in a request context,
        or you need to manually create a session context by using a `db` instance as
        a context manager e.g.:
        async with db():
            await db.session.execute(foo.select()).fetchall()
        """

        super().__init__(msg)


class SessionNotInitialisedError(Exception):
    """Exception raised when the user creates a new DB session without first initialising it."""

    def __init__(self) -> None:
        msg = """
        Session not initialised! Ensure that DBSessionMiddleware has been initialised before
        attempting database access.
        """

        super().__init__(msg)


def set_sessionmaker() -> None:
    engine_args = {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
    }

    session_args: dict[str, Any] = {}
    engine = create_async_engine(get_db_url(), **engine_args)

    global _SESSION  # pylint: disable=global-statement
    _SESSION = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, **session_args)


def reset_sessionmaker() -> None:
    """
    Needed if you start a new event loop and want to ensure that the sessionmaker is re-initialised.
    Otherwise you might see errors like "Future attached to a different loop."
    """
    global _SESSION  # pylint: disable=global-statement
    _SESSION = None
    _session_context_var.set(None)  # reset the context variable as well


class DBSessionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        set_sessionmaker()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # TODO: get schema from request
        async with db(commit_on_exit=True):
            response = await call_next(request)
            if response.status_code >= 400:
                await db.session.rollback()
            return response


class DBSessionMeta(type):
    # using this metaclass means that we can access db.session as a property at a class level,
    # rather than db().session
    @property
    def session(cls) -> AsyncSession:
        """Return an instance of Session local to the current async context."""
        if _SESSION is None:
            raise SessionNotInitialisedError

        return cls.session_context.session

    def add_post_commit_callback(cls, callback: Callable[[], Awaitable[Any]]) -> None:
        """
        Add an async function that should be called after the session has been committed.

        Post-commit callbacks are useful for actions that should only happen if the transaction is successful.
        For example, if you have a cache that depends on database objects, updating the cache before commit
        could lead to inconsistencies if the transaction is rolled back. By registering a post-commit callback,
        you ensure that cache updates (or other side effects) only occur after the database changes are committed
        and guaranteed to persist.
        """
        cls.session_context.on_post_committed.append(callback)

    @property
    def session_context(cls) -> DBSessionContext:
        """Return the current session context."""
        context = _session_context_var.get()
        if context is None:
            raise MissingSessionError
        return context


class DBSession(metaclass=DBSessionMeta):
    def __init__(
        self,
        schema: str = settings.MASTER_DB_SCHEMA,
        session_args: dict[str, Any] | None = None,
        commit_on_exit: bool = False,
    ) -> None:
        self.token: Token[DBSessionContext | None] | None = None
        self.schema = schema
        self.session_args = session_args or {}
        self.commit_on_exit = commit_on_exit

    async def _init_session(self) -> None:
        assert _SESSION is not None  # nosec  we just do the assert to help out VSCode
        session: AsyncSession = _SESSION(**self.session_args)
        execution_options = {"schema_translate_map": {None: self.schema}}

        await session.connection(execution_options=execution_options)
        context = DBSessionContext(session=session)
        self.token = _session_context_var.set(context)

    async def __aenter__(self) -> type["DBSession"]:
        if not isinstance(_SESSION, async_sessionmaker):
            set_sessionmaker()

        await self._init_session()
        return type(self)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        context = _session_context_var.get()
        if not context:
            raise MissingSessionError
        session = context.session
        if exc_type is not None:
            await session.rollback()

        if self.commit_on_exit:
            await session.commit()
            for callback in context.on_post_committed:
                await callback()

        await session.close()
        _session_context_var.reset(self.token)  # type: ignore


db: DBSessionMeta = DBSession
