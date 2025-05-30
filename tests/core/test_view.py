from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from brickworks.core.acl.policies import RoleBasedAccessPolicy
from brickworks.core.auth.executioncontext import ExecutionContext
from brickworks.core.models.base_view import BaseView
from brickworks.core.models.role_model import RoleModel, user_role_table
from brickworks.core.models.user_model import UserModel
from tests.conftest import TestApp
from tests.core.utils import create_test_user

user_alias = aliased(UserModel)
role_alias = aliased(RoleModel)


class UserRoleViewTest(BaseView):
    """
    View displaying user roles.
    """

    role_name: str
    user_name: str

    __select__ = (
        select(
            role_alias.role_name.label("role_name"),
            user_alias.name.label("user_name"),
        )
        .join(role_alias.users)
        .join(user_alias)
    )
    __policy_model_class__ = UserModel
    __policies__ = [RoleBasedAccessPolicy("admin")]


class RolesPerUserViewTest(BaseView):
    """
    View displaying each user and counts the number of roles they have.
    """

    user_name: str
    role_count: int

    __select__ = (
        select(
            user_alias.name.label("user_name"),
            func.count(user_role_table.c.role_uuid).label("role_count"),
        )
        .select_from(user_alias)
        .join(user_role_table, user_alias.uuid == user_role_table.c.user_uuid)
        .group_by(user_alias.name)
    )
    __policy_model_class__ = UserModel
    __policies__ = [RoleBasedAccessPolicy("admin")]


async def test_user_role_view(app: TestApp) -> None:
    """
    Test the UserRoleView class.
    """
    # Create some test users
    alice = await create_test_user("Alice", "Smith")
    bob = await create_test_user("Bob", "Johnson")
    charlie = await create_test_user("Charlie", "Brown")

    # Create some test roles
    role_admin = await RoleModel(role_name="admin").persist()
    role_user = await RoleModel(role_name="user").persist()

    # Assign roles to users
    await alice.add_role(role_admin)
    await alice.add_role(role_user)
    await bob.add_role(role_user)
    await charlie.add_role(role_user)

    # Query the user role view
    user_roles = await UserRoleViewTest.get_list()
    assert len(user_roles) >= 4
    alice_roles = [role for role in user_roles if role.user_name == "Alice Smith"]
    assert len(alice_roles) == 2

    # Query the user count view
    user_count = await RolesPerUserViewTest.get_list()
    assert len(user_count) >= 3
    alice_count = next((user for user in user_count if user.user_name == "Alice Smith"), None)
    assert alice_count is not None
    assert alice_count.role_count == 2

    # test get one or none
    alice_role = await UserRoleViewTest.get_one_or_none(role_name="admin", user_name="Alice Smith")
    assert alice_role is not None
    assert alice_role.role_name == "admin"

    # test get list with filtering by key
    user_roles_filtered = await UserRoleViewTest.get_list(role_name="user")
    assert len(user_roles_filtered) >= 3
    assert all(role.role_name == "user" for role in user_roles_filtered)


async def test_user_role_view_with_policies(app: TestApp) -> None:
    """
    Test the UserRoleView class with policies.
    """
    # Create some test users
    alice = await create_test_user("Alice", "Smith")
    bob = await create_test_user("Bob", "Johnson")
    charlie = await create_test_user("Charlie", "Brown")
    # Create some test roles
    role_admin = await RoleModel(role_name="admin").persist()
    role_user = await RoleModel(role_name="user").persist()
    # Assign roles to users
    await alice.add_role(role_user)
    await bob.add_role(role_user)
    await charlie.add_role(role_user)

    async with ExecutionContext(alice.uuid):
        # Alice does not have the admin role, so she should not see any results
        user_roles = await UserRoleViewTest.get_list_with_policies()
        assert len(user_roles) == 0
        user_count = await RolesPerUserViewTest.get_list_with_policies()
        assert len(user_count) == 0

        await alice.add_role(role_admin)

        # Now Alice has the admin role, so she should see all users
        user_roles = await UserRoleViewTest.get_list_with_policies()
        assert len(user_roles) >= 4

        user_count = await RolesPerUserViewTest.get_list_with_policies()
        assert len(user_count) >= 3
        alice_count = next((user for user in user_count if user.user_name == "Alice Smith"), None)
        assert alice_count is not None
        assert alice_count.role_count == 2
