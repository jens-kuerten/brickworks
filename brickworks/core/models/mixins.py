from typing import Any

from fastapi import APIRouter

from brickworks.core.exceptions import NotFoundException
from brickworks.core.models.base_dbmodel import BaseDBModel
from brickworks.core.models.base_view import BaseView
from brickworks.core.schemas.base_schema import PaginatedResponse


class WithGetRouteMixin:
    """
    Mixin to add a get route to any class with a get_list_with_policies classmethod.
    """

    __routing_path__: str  # The path for the GET route, must be defined in the subclass.
    __routing_get_key__: str | None = None  # Optional key to use for the GET route, defaults to None.

    def __init_subclass__(cls, **kwargs: Any) -> None:  # noqa: ANN401
        super().__init_subclass__(**kwargs)
        if not issubclass(cls, BaseView) and not issubclass(cls, BaseDBModel):
            raise TypeError(f"{cls.__name__} must be a subclass of BaseView or BaseDBModel to use WithGetRouteMixin.")
        if not hasattr(cls, "__routing_path__"):
            raise ValueError(f"{cls.__name__} must define a __routing_path__ attribute to use WithGetRouteMixin.")
        if not cls.__routing_path__:
            raise ValueError(f"{cls.__name__} must define a __routing_path__ attribute to use WithGetRouteMixin.")

    @classmethod
    def get_router(cls) -> APIRouter:
        if not issubclass(cls, BaseView) and not issubclass(cls, BaseDBModel):
            raise TypeError(f"{cls.__name__} must be a subclass of BaseView or BaseDBModel to use WithGetRouteMixin.")

        router = APIRouter()

        async def _get_all(page: int = 1, page_size: int = 500) -> PaginatedResponse[BaseDBModel | BaseView]:
            items, total = await cls.get_paginated_list_with_policies(_per_page=page_size, _page=page)
            return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)

        router.add_api_route(
            cls.__routing_path__,
            _get_all,
            response_model=PaginatedResponse[cls],  # type: ignore
            summary=f"Get all {cls.__name__} objects (paginated)",
            description=f"Get all {cls.__name__} objects with pagination.",
        )

        routing_get_key = cls.__routing_get_key__
        if routing_get_key:

            async def _get_by_key(key: str) -> BaseView | BaseDBModel | None:
                result = await cls.get_one_or_none_with_policies(_filter_clause=None, **{routing_get_key: key})
                if not result:
                    raise NotFoundException(f"{cls.__name__} with {routing_get_key} '{key}' not found.")
                return result

            router.add_api_route(
                f"{cls.__routing_path__}/{{key}}",
                _get_by_key,
                response_model=cls | None,
                summary=f"Get a {cls.__name__} object by {cls.__routing_get_key__}",
                description=f"Get a {cls.__name__} object by {cls.__routing_get_key__}.",
            )

        return router
