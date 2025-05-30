import logging
from collections.abc import AsyncIterable
from typing import Any

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from brickworks.core import db
from brickworks.core.auth.executioncontext import ExecutionContext
from brickworks.core.module_loader import get_models_by_fqpn, get_views
from brickworks.core.server import create_app

logger = logging.getLogger(__name__)


TestApp = FastAPI


@pytest.fixture
async def app() -> AsyncIterable[FastAPI]:
    """
    Create a FastAPI instance.

    1. Populate database with test data only once
    2. Create a FastAPI instance
    3. Execute lifespan cycle
    4. Create a global transaction to wrap each test.

       * DBTransactionMiddleware only wraps each REST API endpoint,
         but not the test itself.
       * The global force_rollback provided by Encode/Databases doesn't play well
         with inner transactions and cause issues.
    """
    get_views.cache_clear()  # clear lru caches in case a test adds a new view or model
    get_models_by_fqpn.cache_clear()
    _app = create_app(for_testing=True)
    async with LifespanManager(_app), db(), ExecutionContext():
        yield _app
        await db.session.rollback()
    get_views.cache_clear()
    get_models_by_fqpn.cache_clear()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterable[AsyncClient]:
    async def clear_session(_: Any) -> None:  # noqa: ANN401
        # we need to make sure that subsequent requests don't have any data from the previous request
        await db.session.flush()
        db.session.expire_all()

        # call all post-commit callbacks that would have been called by the DBSessionMiddleware
        # since we are simulating a commit by flushing the session
        for callback in db.session_context.on_post_committed:
            await callback()
        db.session_context.on_post_committed.clear()

    async with AsyncClient(
        base_url="http://testserver/backend",
        event_hooks={"response": [clear_session]},
        transport=ASGITransport(app=app),
    ) as client:
        yield client
