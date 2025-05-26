import asyncio
import logging

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from brickworks.core.cache import cache
from brickworks.core.db import db
from brickworks.core.exceptions import DuplicateException
from brickworks.core.models.base_dbmodel import BaseDBModel
from brickworks.core.settings import settings

logger = logging.getLogger(__name__)


@cache.lru_cache(master_tenant=True, expire=60)
async def get_domain_schema_mapping() -> dict[str, str]:
    return await _get_domain_schema_mapping()


async def create_schema(schema_name: str) -> None:
    """
    Runs the mason CLI to migrate the database for the given schema name asynchronously.
    """

    process = await asyncio.create_subprocess_exec(
        "mason",
        "db",
        "migrate",
        "--schema",
        schema_name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"mason db migrate failed: {stderr.decode().strip()}")
    logger.info(f"Created schema {schema_name} with mason db migrate")


async def drop_schema(schema_name: str) -> None:
    """
    Runs the mason CLI to drop the database schema for the given schema name asynchronously.
    """

    process = await asyncio.create_subprocess_exec(
        "mason",
        "db",
        "drop",
        schema_name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"mason db drop failed: {stderr.decode().strip()}")
    logger.info(f"Dropped schema {schema_name} with mason db drop")


async def _get_domain_schema_mapping() -> dict[str, str]:
    """
    Returns a dict of domain->schema mappings.
    """
    async with db(schema=settings.MASTER_DB_SCHEMA):
        tenant_models = await TenantModel.get_list()
        domain_map = {tenant_model.domain: tenant_model.schema for tenant_model in tenant_models}
        domain_map[settings.MASTER_DOMAIN] = settings.MASTER_DB_SCHEMA
    return domain_map


class TenantModel(BaseDBModel):
    __tablename__ = "core_tenants"
    schema: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)  # public name

    @classmethod
    async def create(cls, schema: str, domain: str, label: str) -> "TenantModel":
        if schema == settings.MASTER_DB_SCHEMA or domain == settings.MASTER_DOMAIN:
            raise DuplicateException("Tenant already exists")
        new_tenant = await TenantModel(schema=schema, domain=domain, label=label).persist()

        # clear the cache after creating a new tenant, but only after the session is committed
        db.add_post_commit_callback(get_domain_schema_mapping.cache_clear)
        await create_schema(schema)
        return new_tenant

    async def on_delete_post(self) -> None:
        # clear the cache after deleting a tenant, but only after the session is committed
        db.add_post_commit_callback(get_domain_schema_mapping.cache_clear)

        # also drop the schema associated with this tenant
        async def drop_tenant_schema() -> None:
            await drop_schema(self.schema)

        db.add_post_commit_callback(drop_tenant_schema)
