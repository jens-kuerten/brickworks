# pylint: disable=no-member
import asyncio
import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool, schema, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from brickworks.core import db
from brickworks.core.db import get_db_url, reset_sessionmaker
from brickworks.core.models.base_dbmodel import Base
from brickworks.core.settings import settings

config = context.config


config.set_main_option("sqlalchemy.url", get_db_url())

logger = logging.getLogger("env_py")

# Interpret the config file for Python logging.
# This line sets up loggers basically.
# only set up logging if it isn't already configured
if config.config_file_name is not None and not logging.getLogger().handlers:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

target_metadata.naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


async def get_schema_list() -> list[str]:
    """
    Fetch a list of all tenant schemas from the database.
    This requires that the master schema is already created, or this will crash!
    """
    from brickworks.core.models.tenant_model import TenantModel

    async with db(schema=settings.MASTER_DB_SCHEMA):
        query = select(TenantModel.schema)
        result = await db.session.execute(query)
        return [row[0] for row in result]


def do_run_migrations(connection: Connection | None) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)

    with context.begin_transaction():
        context.run_migrations()


async def create_schema(schema_name: str, conntactable: AsyncEngine) -> None:
    try:
        async with conntactable.connect() as connection:
            await connection.execute(schema.CreateSchema(schema_name))
            await connection.commit()
        logger.info(f"Created schema {schema_name}")
    except ProgrammingError:
        pass  # schema already exists, ignore the error


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode.
    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    reset_sessionmaker()  # reset sessionmaker to ensure the engine is running in the correct event loop

    # check which operation we are performing
    # we pass them as x-arguments
    try:
        is_migration = context.get_x_argument(as_dictionary=True).get("mode") == "migrate"
        schema = context.get_x_argument(as_dictionary=True).get("schema", "")
    except AttributeError:
        # if no x-arguments are provided an AttributeError is raised
        # so we assume the defaults
        is_migration = False
        schema = ""
    # get the database connection...
    url: str = config.get_main_option("sqlalchemy.url") or ""
    if not url or not url.startswith("postgresql+asyncpg://"):
        raise ValueError("Invalid database URL. It must start with 'postgresql+asyncpg://'.")
    connectable = create_async_engine(url, poolclass=pool.NullPool)

    if is_migration:
        if schema:
            # if a schema is provided, we run migrations for that schema only
            # this would be the case after a new tenant is created
            await run_migrations_with_schema(connectable, schema)
            return
        # if no schema is provided, we run migrations for all schemas

        # run migration for master first, because we need to exist, otherwise
        # attempting to fetch the list of schemas will crash
        await run_migrations_with_schema(connectable, settings.MASTER_DB_SCHEMA)

        # now we can fetch the list of schemas
        schema_names = await get_schema_list()
        if settings.MASTER_DB_SCHEMA in schema_names:
            # remove the master schema from the list of schemas to migrate
            # because we already ran migrations for it
            schema_names.remove(settings.MASTER_DB_SCHEMA)

        # migrate all other schemas
        for schema_name in schema_names:
            await run_migrations_with_schema(connectable, schema_name)
    else:
        # might be creating a new revision or checking for changes
        # so we only run migrations for the master schema
        await run_migrations_with_schema(connectable, settings.MASTER_DB_SCHEMA)

    await connectable.dispose()


async def run_migrations_with_schema(connectable: AsyncEngine, schema_name: str) -> None:
    await create_schema(schema_name, connectable)
    logger.info(f"Running migrations for schema {schema_name}")
    async with connectable.connect() as connection:
        await connection.execution_options(schema_translate_map={None: schema_name})
        await connection.execute(text(f'set search_path to "{schema_name}"'))
        await connection.commit()
        # make use of non-supported SQLAlchemy attribute to ensure
        # the dialect reflects tables in terms of the current tenant name
        connection.dialect.default_schema_name = schema_name
        await connection.run_sync(do_run_migrations)


asyncio.run(run_migrations_online())
