import pytest
from sqlalchemy.exc import ProgrammingError

from brickworks.core import db
from brickworks.core.models.tenant_model import TenantModel
from tests.conftest import TestApp


async def test_create_delete_tenant(app: TestApp) -> None:
    """
    Test that will create a tenant and delete it again.
    """

    tenant = await TenantModel.create(
        domain="test.example.com",
        schema="test_schema",
        label="Test Tenant",
    )
    assert tenant.domain == "test.example.com"
    assert tenant.schema == "test_schema"
    assert tenant.label == "Test Tenant"

    # verify that we can fetch data from the tenant schema
    async with db(schema=tenant.schema):
        result = await TenantModel.get_list()
        assert len(result) == 0
        # if the fetch would access the master schema, it would return the tenant model itself
        # in the tenant this should be empty

    # delete the tenant
    await tenant.delete()

    # the deletion of the tenant schema is done in post commit callbacks,
    # which aren't executed in tests (because we rollback the session)
    # so we need to manually call the post commit callbacks
    for callback in db.session_context.on_post_committed:
        await callback()
    db.session_context.on_post_committed.clear()

    async with db(schema=tenant.schema):
        # verify that the tenant schema is dropped
        with pytest.raises(ProgrammingError):
            result = await TenantModel.get_list()
