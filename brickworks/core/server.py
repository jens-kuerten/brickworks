import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from brickworks.core.auth.csrf import CSRFMiddleware
from brickworks.core.auth.executioncontext import ExecutionContextMiddleware
from brickworks.core.auth.session import SessionMiddleware
from brickworks.core.db import DBSessionMiddleware
from brickworks.core.models.mixins import WithGetRouteMixin
from brickworks.core.module_loader import get_models_by_fqpn, get_views, load_modules
from brickworks.core.utils.importer import import_object_from_path

logging.basicConfig(level=logging.INFO)


def create_app(for_testing: bool = False) -> FastAPI:
    app_base = FastAPI()
    app_api = FastAPI()

    # Middleware is executed in reverse order, so we first add the middleware that should be executed last
    # Middleware loaded from bricks should be executed last, so we add it first
    # (to ensure it has access to sessions and the database)
    for brick in load_modules():
        _add_routers(app_api, brick.routers)
        _add_middlewares(app_api, brick.middlewares)

    _add_auto_routes(app_api)

    if not for_testing:
        # if we run the app with testclient we will create database sessions ourselves, so we can roll back
        app_api.add_middleware(DBSessionMiddleware)

    app_api.add_middleware(CSRFMiddleware)  # needs to be before session middleware
    app_api.add_middleware(
        SessionMiddleware,
        cookie_name="session",
        max_age=14 * 24 * 60 * 60,
        same_site="lax",
        https_only=False,
        domain=None,
    )
    app_api.add_middleware(ExecutionContextMiddleware)
    app_api.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:8000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # app_base.add_event_handler("startup", start_services)

    app_base.mount("/backend/api", app_api)
    return app_base


def _add_routers(app: FastAPI, routers: list[str]) -> None:
    for router_path in routers:
        router = import_object_from_path(router_path)
        app.include_router(router)


def _add_auto_routes(app: FastAPI) -> None:
    views = get_views()
    views_with_routes = [view for view in views if issubclass(view, WithGetRouteMixin)]
    for view in views_with_routes:
        router = view.get_router()
        app.include_router(router)
    models = get_models_by_fqpn()
    models_with_routes = [model for model in models.values() if issubclass(model, WithGetRouteMixin)]
    for model in models_with_routes:
        router = model.get_router()
        app.include_router(router)


def _add_middlewares(app: FastAPI, middlewares: list[str]) -> None:
    for middleware_path in middlewares:
        middleware = import_object_from_path(middleware_path)
        app.add_middleware(middleware)


if __name__ == "__main__":
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)  # nosec
