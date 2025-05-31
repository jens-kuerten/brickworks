from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from brickworks.core.acl.policies import AllowPublicAccessPolicy
from brickworks.core.models.base_view import BaseView
from brickworks.core.models.mixins import WithGetRoute, WithListRoute
from brickworks.core.models.role_model import RoleModel, user_role_table
from brickworks.core.models.user_model import UserModel
from tests.core.utils import create_test_user

user_alias = aliased(UserModel)
user_role_table_alias = aliased(user_role_table)


class RolesPerUserView(BaseView, WithGetRoute, WithListRoute):
    # define the fields of your query result
    # the field names need to match the (labeled) column names returned by the select statement
    user_name: str
    role_count: int

    __routing_path__ = "/test/roles_per_user"
    __routing_get_key__ = "user_name"
    __policies__ = [AllowPublicAccessPolicy()]  # policies to apply to this view, can be empty
    __policy_model_class__ = UserModel  # the model class to apply policies to
    # define the select statement
    __select__ = (
        select(
            user_alias.name.label("user_name"),
            func.count(user_role_table_alias.c.role_uuid).label("role_count"),
        )
        .select_from(user_alias)
        .outerjoin(user_role_table_alias, user_alias.uuid == user_role_table_alias.c.user_uuid)
        .group_by(user_alias.name)
    )


class TestUserModel(UserModel, WithGetRoute, WithListRoute):
    """
    Test UserModel with WithGetRouteMixin for testing purposes.
    """

    __routing_path__ = "/test/user"
    __routing_get_key__ = "name"
    __policies__ = [AllowPublicAccessPolicy()]
    __policy_model_class__ = UserModel


async def test_with_get_route_mixin(client: AsyncClient) -> None:
    """
    Test the WithGetRouteMixin functionality, by using the RolesPerUserView.
    """
    # Create a test user with role
    user = await create_test_user("Alice", "Smith")
    role = await RoleModel(role_name="test_role").persist()
    await user.add_role(role)

    # fetch the roles per user (paginated response)
    response = await client.get("/api/test/roles_per_user?page=1&page_size=300")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "items" in data and "total" in data and "page" in data and "page_size" in data
    assert isinstance(data["items"], list)
    assert data["total"] >= 1
    assert data["page"] == 1
    assert data["page_size"] == 300

    # check if the user is in the response and has the correct role count
    user_data = next((item for item in data["items"] if item["user_name"] == "Alice Smith"), None)
    assert user_data is not None
    assert user_data["role_count"] == 1

    # fetch the user by name (single object response)
    response = await client.get("/api/test/roles_per_user/Alice Smith")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data["user_name"] == "Alice Smith"
    assert data["role_count"] == 1


async def test_with_get_route_mixin_model(client: AsyncClient) -> None:
    """
    Test the WithGetRouteMixin functionality with a model class (TestUserModel).
    """
    # Create a test user
    await create_test_user("Bob", "Johnson")

    # fetch the users (paginated response)
    response = await client.get("/api/test/user?page=1&page_size=100")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "items" in data and "total" in data and "page" in data and "page_size" in data
    assert isinstance(data["items"], list)
    assert data["total"] >= 1
    assert data["page"] == 1
    assert data["page_size"] == 100

    # check if the user is in the response
    user_data = next((item for item in data["items"] if item["name"] == "Bob Johnson"), None)
    assert user_data is not None
    assert user_data["family_name"] == "Johnson"

    # fetch the user by name (single object response)
    response = await client.get("/api/test/user/Bob Johnson")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data["name"] == "Bob Johnson"
    assert data["family_name"] == "Johnson"
