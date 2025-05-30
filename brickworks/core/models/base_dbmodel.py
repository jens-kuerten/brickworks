import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any, ClassVar, Literal, Self, TypeVar, final
from uuid import uuid4

from sqlalchemy import DateTime, Select, String, and_, delete, func, insert, or_, select
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, mapped_column
from sqlalchemy.sql._typing import _ColumnExpressionOrStrLabelArgument

from brickworks.core.acl.base_policy import BasePolicy
from brickworks.core.db import db
from brickworks.core.signals import BaseSignal, signals
from brickworks.core.utils.sqlalchemy import TypeWhereClause
from brickworks.core.utils.timeutils import now_utc

logger = logging.getLogger(__name__)
UUID_LENGTH = 36  # UUID length for string representation

BaseDBModelType = TypeVar("BaseDBModelType", bound="BaseDBModel")  # pylint: disable=invalid-name


class Base(AsyncAttrs, DeclarativeBase):
    """
    Base class for all SQLAlchemy declarative models in the project.
    """

    pass


class BaseDBModel(MappedAsDataclass, Base, kw_only=True):
    """
    Abstract base class for all database models.

    Provides common fields (uuid, created_at, updated_at) and policy-based access control.
    Subclasses can define __policies__ as a list of BasePolicy instances to control row-level access.
    """

    __abstract__ = True
    __policies__: ClassVar[list["BasePolicy"]] = []

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default_factory=now_utc, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default_factory=now_utc, onupdate=now_utc)

    uuid: Mapped[str] = mapped_column(
        String(UUID_LENGTH),
        primary_key=True,
        default_factory=lambda: str(uuid4()),
        index=True,
    )

    @classmethod
    def fqpn(cls) -> str:
        """
        Fully Qualified Path Name (FQPN) for the object.
        """
        return f"{cls.__module__}.{cls.__name__}"

    @classmethod
    async def apply_policies_to_query(
        cls: type[BaseDBModelType], query: Select[Any], policies: list[BasePolicy] | None = None
    ) -> Select[Any]:
        """
        Returns the filter statement for use in a where clause.
        Returns None if no policy filters exist.
        """

        permissive_filters = [
            await p.filter(cls) for p in (policies or cls.__policies__) if p.policy_type.value == "permissive"
        ]
        if not permissive_filters:
            # if no permissive filters exist we don't give any access
            # we also don't need to evaluate restrictive filters, because nobody has access anyway
            # we log a warning, because this is probably not intended
            logger.warning(
                "No permissive filters found for %s. No access granted. Returning empty result set.", cls.__name__
            )
            return query.where(cls.uuid == None)  # noqa: E711

        restrictive_filters = [
            await p.filter(cls) for p in (policies or cls.__policies__) if p.policy_type.value == "restrictive"
        ]

        if restrictive_filters:
            where_clause = and_(and_(*restrictive_filters), or_(*permissive_filters))  # noqa: E711
        else:
            where_clause = or_(*permissive_filters)

        return query.where(where_clause)

    @classmethod
    async def get_one_or_none_with_policies(
        cls: type[BaseDBModelType],
        _filter_clause: TypeWhereClause | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> BaseDBModelType | None:
        """
        Retrieve a single database row matching all provided key-value pairs, with custom filtering.
        This method applies all restrictive (AND) and permissive (OR) policies defined in __policies__ of the model.

        Filtering options:
        - Additional key-value filters can be passed as kwargs (combined with AND).
        - If _filter_clause is provided, it is added as an extra SQLAlchemy filter.

        Returns None if no match is found.
        """
        return await cls.get_one_or_none(
            _apply_policies=True,
            _filter_clause=_filter_clause,
            **kwargs,
        )

    @classmethod
    async def get_one_or_none(
        cls: type[BaseDBModelType],
        _apply_policies: bool = False,
        _filter_clause: TypeWhereClause | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> BaseDBModelType | None:
        """
        Retrieve a single database row matching all provided key-value pairs, with optional policy and custom filtering.

        Filtering options:
        - _apply_policies: applies all restrictive (AND) and permissive (OR) policies defined in __policies__
        - Additional key-value filters can be passed as kwargs (combined with AND).
        - If _filter_clause is provided, it is added as an extra SQLAlchemy filter.

        Returns None if no match is found.
        """
        query = select(cls)
        if _apply_policies:
            query = await cls.apply_policies_to_query(query)
        if kwargs:
            query = query.where(and_(*(getattr(cls, key) == value for key, value in kwargs.items())))
        if _filter_clause is not None:
            query = query.where(_filter_clause)
        result = await db.session.execute(query)
        return result.unique().scalars().one_or_none()

    @classmethod
    async def get_list_with_policies(
        cls: type[BaseDBModelType],
        _filter_clause: TypeWhereClause | None = None,
        _order_by: Literal[None]
        | _ColumnExpressionOrStrLabelArgument[Any]
        | list[_ColumnExpressionOrStrLabelArgument[Any]] = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> Sequence[BaseDBModelType]:
        """
        Retrieve a list of database rows with flexible filtering, ordering, and pagination.
        This method applies all restrictive (AND) and permissive (OR) policies defined in __policies__ of the model.

        Filtering options:
        - _filter_clause: custom SQLAlchemy filter clause.
        - Additional key-value filters can be passed as kwargs (combined with AND).

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
    async def get_list(
        cls: type[BaseDBModelType],
        _apply_policies: bool = False,
        _filter_clause: TypeWhereClause | None = None,
        _order_by: Literal[None]
        | _ColumnExpressionOrStrLabelArgument[Any]
        | list[_ColumnExpressionOrStrLabelArgument[Any]] = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> Sequence[BaseDBModelType]:
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
                _per_page=-1,  # No pagination by default
                _page=1,  # Default to first page
                **kwargs,
            )
        )[0]

    @classmethod
    async def get_paginated_list_with_policies(
        cls: type[BaseDBModelType],
        _per_page: int,
        _page: int,
        _filter_clause: TypeWhereClause | None = None,
        _order_by: Literal[None]
        | _ColumnExpressionOrStrLabelArgument[Any]
        | list[_ColumnExpressionOrStrLabelArgument[Any]] = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> tuple[Sequence[BaseDBModelType], int]:
        """
        Retrieve a paginated list of database rows and the total count, applying policies.
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
    async def get_paginated_list(
        cls: type[BaseDBModelType],
        _per_page: int,
        _page: int,
        _apply_policies: bool = False,
        _filter_clause: TypeWhereClause | None = None,
        _order_by: Literal[None]
        | _ColumnExpressionOrStrLabelArgument[Any]
        | list[_ColumnExpressionOrStrLabelArgument[Any]] = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> tuple[Sequence[BaseDBModelType], int]:
        """
        Retrieve a paginated list of database rows and the total count.
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
        cls: type[BaseDBModelType],
        _apply_policies: bool = False,
        _filter_clause: TypeWhereClause | None = None,
        _order_by: Literal[None]
        | _ColumnExpressionOrStrLabelArgument[Any]
        | list[_ColumnExpressionOrStrLabelArgument[Any]] = None,
        _per_page: int = -1,
        _page: int = 1,
        **kwargs: Any,  # noqa: ANN401
    ) -> tuple[Sequence[BaseDBModelType], int]:
        """
        Shared logic for paginated and non-paginated list queries.
        Returns a tuple: (items, total_count)
        """
        query = select(cls)
        if _apply_policies:
            query = await cls.apply_policies_to_query(query)
        if kwargs:
            query = query.where(and_(*(getattr(cls, key) == value for key, value in kwargs.items())))
        if _filter_clause is not None:
            query = query.where(_filter_clause)
        # Count query
        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.session.execute(count_query)).scalar_one()
        # Pagination and ordering
        if _order_by is not None:
            query = query.order_by(*_order_by if isinstance(_order_by, list) else [_order_by])
        if _per_page > 0:
            query = query.limit(_per_page).offset((_page - 1) * _per_page)
        result = await db.session.execute(query)
        items = result.unique().scalars().all()
        return items, total

    async def on_persist_pre(self) -> None:
        """
        Hook method called before persisting the instance to the database.
        Can be overridden in subclasses for custom behavior.
        """
        pass

    async def on_persist_post(self) -> None:
        """
        Hook method called after persisting the instance to the database.
        Can be overridden in subclasses for custom behavior.
        """
        pass

    @final
    async def persist(self) -> Self:
        """
        Persist the current instance to the database and flush the session.

        Order of operations:
        1. on_persist_pre
        2. ModelPersistPreSignal
        3. persist
        4. on_persist_post
        5. ModelPersistPostSignal
        """
        await self.on_persist_pre()
        await signals.emit(ModelPersistPreSignal(obj=self))
        db.session.add(self)
        await db.session.flush()
        await self.on_persist_post()
        await signals.emit(ModelPersistPostSignal(obj=self))

        return self

    async def on_delete_pre(self) -> None:
        """
        Hook method called before deleting the instance from the database.
        Can be overridden in subclasses for custom behavior.
        """
        pass

    async def on_delete_post(self) -> None:
        """
        Hook method called after deleting the instance from the database.
        Can be overridden in subclasses for custom behavior.
        """
        pass

    @final
    async def delete(self) -> None:
        """
        Delete the current instance from the database and flush the session.

        Order of operation is:
        1. on_delete_pre
        2. ModelDeletePreSignal
        3. delete
        4. on_delete_post
        5. ModelDeletePostSignal
        """
        await self.on_delete_pre()
        await signals.emit(ModelDeletePreSignal(obj=self))
        await db.session.delete(self)
        await db.session.flush()
        await self.on_delete_post()
        await signals.emit(ModelDeletePostSignal(obj=self))

    async def give_role_permission(self, role_name: str, permission: str) -> None:
        from brickworks.core.models.role_model import role_acl_table

        dialect_name = db.session.bind.dialect.name
        if dialect_name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt_pg = (
                pg_insert(role_acl_table)
                .values(role_name=role_name, object_uuid=self.uuid, object_fqpn=self.fqpn(), permission=permission)
                .on_conflict_do_nothing(index_elements=["role_name", "object_uuid", "permission"])
            )
            await db.session.execute(stmt_pg)
        elif dialect_name == "sqlite":
            stmt_sqlite = (
                insert(role_acl_table)
                .values(role_name=role_name, object_uuid=self.uuid, object_fqpn=self.fqpn(), permission=permission)
                .prefix_with("OR IGNORE")
            )
            await db.session.execute(stmt_sqlite)
        else:
            NotImplementedError(f"Dialect {dialect_name} is not supported for role ACL insertion.")

    async def remove_role_permission(self, role_name: str, permission: str) -> None:
        from brickworks.core.models.role_model import role_acl_table

        stmt = (
            delete(role_acl_table)
            .where(
                and_(
                    role_acl_table.c.role_name == role_name,
                    role_acl_table.c.object_uuid == self.uuid,
                    role_acl_table.c.permission == permission,
                )
            )
            .execution_options(synchronize_session="fetch")
        )
        await db.session.execute(stmt)
        await db.session.flush()

    async def role_permissions(self, role_name: str) -> list[str]:
        from brickworks.core.models.role_model import role_acl_table

        stmt = select(role_acl_table.c.permission).where(role_acl_table.c.role_name == role_name)
        result = await db.session.execute(stmt)
        return [row[0] for row in result.all()]

    async def has_role_permission(self, role_name: str, permission: str) -> bool:
        from brickworks.core.models.role_model import role_acl_table

        stmt = select(role_acl_table.c.permission).where(
            and_(role_acl_table.c.role_name == role_name, role_acl_table.c.object_uuid == self.uuid)
        )
        result = await db.session.execute(stmt)
        return any(row[0] == permission for row in result.all())


class ModelDeletePreSignal(BaseSignal):
    """
    Signal emitted before a database row is deleted.
    """

    obj: BaseDBModel


class ModelDeletePostSignal(ModelDeletePreSignal):
    """
    Signal emitted after a database row is deleted.
    """

    pass


class ModelPersistPreSignal(BaseSignal):
    """
    Signal emitted before a database row is persisted.
    """

    obj: BaseDBModel


class ModelPersistPostSignal(ModelPersistPreSignal):
    """
    Signal emitted after a database row is persisted.
    """

    pass
