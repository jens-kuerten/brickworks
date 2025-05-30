from collections.abc import Sequence
from typing import Any, TypeVar

from sqlalchemy import Select, and_, func, select

from brickworks.core import db
from brickworks.core.acl.base_policy import BasePolicy
from brickworks.core.models.base_dbmodel import BaseDBModel
from brickworks.core.schemas.base_schema import BaseSchema
from brickworks.core.utils.sqlalchemy import TypeOrderBy, TypeWhereClause

BaseViewType = TypeVar("BaseViewType", bound="BaseView")  # pylint: disable=invalid-name


class BaseView(BaseSchema):
    """
    Base class for creating SQLAlchemy-based read-only views.

    To define a custom view, subclass BaseView and specify:
      - `__select__`: a SQLAlchemy Select statement that defines the columns and joins for the view.
      - `__policy_model_class__`: The model that should be used to apply policies.
      - `__policies__`: A list of policies to apply to the view. If not provided the models policies are used.

    If you are using joins, make sure to use the `aliased` function from SQLAlchemy to avoid name conflicts!

    Example:
        class MyCustomView(BaseView):
            field1: str
            field2: int

            __select__ = select(
                SomeModel.field1.label("field1"),
                SomeModel.field2.label("field2"),
            )
            __policy_model_class__ = SomeModel

    Usage:
        - Use `await MyCustomView.get_list(...)` to fetch multiple rows as Pydantic objects.
        - Use `await MyCustomView.get_one_or_none(...)` to fetch a single row or None.

    Filtering, ordering, and pagination are supported via method arguments.
    (same as for the database models)
    """

    __select__: Select[Any]
    __policy_model_class__: type[BaseDBModel] | None = None  # nodel class used for policies
    __policies__: list["BasePolicy"] = []  # policies to apply to the view

    @classmethod
    async def get_one_or_none_with_policies(
        cls: type[BaseViewType],
        _filter_clause: TypeWhereClause | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> BaseViewType | None:
        """
        Retrieve a single database row matching all provided key-value pairs, with custom filtering.
        This method applies all restrictive (AND) and permissive (OR) policies defined in
        __policies__ of the __model_class__.

        Filtering options:
        - Additional key-value filters can be passed as kwargs (combined with AND).
        - If _filter_clause is provided, it is added as an extra SQLAlchemy filter.

        Returns None if no match is found.
        """
        return await cls.get_one_or_none(_apply_policies=True, _filter_clause=_filter_clause, **kwargs)

    @classmethod
    async def get_one_or_none(
        cls: type[BaseViewType],
        _apply_policies: bool = False,
        _filter_clause: TypeWhereClause | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> BaseViewType | None:
        """
        Retrieve a single database row matching all provided key-value pairs, with optional policy and custom filtering.

        Filtering options:
        - _apply_policies: applies all restrictive (AND) and permissive (OR) policies defined in __policies__
        - Additional key-value filters can be passed as kwargs (combined with AND).
        - If _filter_clause is provided, it is added as an extra SQLAlchemy filter.

        Returns None if no match is found.
        """
        query = cls.__select__
        if _apply_policies:
            if not cls.__policy_model_class__:
                raise ValueError("Cannot apply policies without a model class")
            query = await cls.__policy_model_class__.apply_policies_to_query(query, policies=cls.__policies__ or None)

        # Map kwargs to columns in __select__ using their labels
        label_to_column = {col._label: col for col in query.selected_columns}
        if kwargs:
            filters = []
            for key, value in kwargs.items():
                col = label_to_column.get(key)
                if col is None:
                    raise AttributeError(f"Column '{key}' not found in view select statement")
                filters.append(col == value)
            query = query.where(and_(*filters))

        if _filter_clause is not None:
            query = query.where(_filter_clause)
        result = await db.session.execute(query)
        row = result.unique().one_or_none()
        return cls(**dict(zip(row._fields, row._t, strict=True))) if row else None

    @classmethod
    async def get_list_with_policies(
        cls: type[BaseViewType],
        _filter_clause: TypeWhereClause | None = None,
        _order_by: TypeOrderBy | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> Sequence[BaseViewType]:
        """
        Retrieve a list of database rows with flexible filtering, ordering, and pagination.
        This method applies all restrictive (AND) and permissive (OR) policies defined in
        __policies__ of the __model_class__.

        Filtering options:
        - Additional key-value filters can be passed as kwargs (combined with AND).
        - If _filter_clause is provided, it is added as an extra SQLAlchemy filter.

        Ordering and pagination:
        - _order_by: SQLAlchemy column or list of columns to order by.
        - _per_page: If > 0, limits the number of results per page.
        - _page: Page number for paginated results (1-based).

        Returns a sequence of matching rows.
        """
        return await cls.get_list(
            _apply_policies=True,
            _filter_clause=_filter_clause,
            _order_by=_order_by,
            **kwargs,
        )

    @classmethod
    async def get_paginated_list_with_policies(
        cls: type[BaseViewType],
        _per_page: int,
        _page: int,
        _filter_clause: TypeWhereClause | None = None,
        _order_by: TypeOrderBy | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> tuple[Sequence[BaseViewType], int]:
        """
        Retrieve a paginated list of database rows and the total count.
        This method applies all restrictive (AND) and permissive (OR) policies defined in
        __policies__ of the __model_class__.

        Requires _per_page and _page parameters.
        Returns a tuple: (items, total_count)
        """
        return await cls.get_paginated_list(
            _per_page=_per_page,
            _page=_page,
            _apply_policies=True,
            _filter_clause=_filter_clause,
            _order_by=_order_by,
            **kwargs,
        )

    @classmethod
    async def get_list(
        cls: type[BaseViewType],
        _apply_policies: bool = False,
        _filter_clause: TypeWhereClause | None = None,
        _order_by: TypeOrderBy | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> Sequence[BaseViewType]:
        """
        Retrieve a list of database rows with flexible filtering, ordering, and pagination.

        Filtering options:
        - _apply_policies: applies all restrictive (AND) and permissive (OR) policies defined in __policies__
        - Additional key-value filters can be passed as kwargs (combined with AND).
        - If _filter_clause is provided, it is added as an extra SQLAlchemy filter.

        Ordering and pagination:
        - _order_by: SQLAlchemy column or list of columns to order by.
        - _per_page: If > 0, limits the number of results per page.
        - _page: Page number for paginated results (1-based).

        Returns a sequence of matching rows.
        """
        return (
            await cls._get_list_common(
                _apply_policies=_apply_policies,
                _filter_clause=_filter_clause,
                _order_by=_order_by,
                _per_page=-1,
                _page=1,
                **kwargs,
            )
        )[0]

    @classmethod
    async def get_paginated_list(
        cls: type[BaseViewType],
        _per_page: int,
        _page: int,
        _apply_policies: bool = False,
        _filter_clause: TypeWhereClause | None = None,
        _order_by: TypeOrderBy | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> tuple[Sequence[BaseViewType], int]:
        """
        Retrieve a paginated list of database rows and the total count.
        Requires _per_page and _page parameters.
        Returns a tuple: (items, total_count)
        """
        return await cls._get_list_common(
            _apply_policies=_apply_policies,
            _filter_clause=_filter_clause,
            _order_by=_order_by,
            _per_page=_per_page,
            _page=_page,
            **kwargs,
        )

    @classmethod
    async def _get_list_common(
        cls: type[BaseViewType],
        _apply_policies: bool = False,
        _filter_clause: TypeWhereClause | None = None,
        _order_by: TypeOrderBy | None = None,
        _per_page: int = -1,
        _page: int = 1,
        **kwargs: Any,  # noqa: ANN401
    ) -> tuple[Sequence[BaseViewType], int]:
        """
        Retrieve a paginated list of database rows and the total count.
        Returns a tuple: (items, total_count)
        """
        query = cls.__select__
        if _apply_policies:
            if not cls.__policy_model_class__:
                raise ValueError("Cannot apply policies without a model class")
            query = await cls.__policy_model_class__.apply_policies_to_query(query, policies=cls.__policies__ or None)

        label_to_column = {col._label: col for col in query.selected_columns}
        if kwargs:
            filters = []
            for key, value in kwargs.items():
                col = label_to_column.get(key)
                if col is None:
                    raise AttributeError(f"Column '{key}' not found in view select statement")
                filters.append(col == value)
            query = query.where(and_(*filters))

        if _filter_clause is not None:
            query = query.where(_filter_clause)

        if _per_page > 0:
            # Count query
            count_query = select(func.count()).select_from(query.subquery())
            total = (await db.session.execute(count_query)).scalar_one()
        else:
            total = -1

        # Pagination and ordering
        if _order_by is not None:
            query = query.order_by(*_order_by if isinstance(_order_by, list) else [_order_by])
        if _per_page > 0:
            query = query.limit(_per_page).offset((_page - 1) * _per_page)

        result = await db.session.execute(query)
        rows = result.unique()
        items = [cls(**dict(zip(row._fields, row._t, strict=True))) for row in rows]
        return items, total
