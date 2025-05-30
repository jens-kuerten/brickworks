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


class UserRoleTestView(BaseView):
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
    __policies__ = [RoleBasedAccessPolicy("test_admin")]


class RolesPerUserTestView(BaseView):
    """
    View displaying each user and counts the number of roles they have.
    """

    user_name: str
    role_count: int
    family_name: str

    __select__ = (
        select(
            user_alias.name.label("user_name"),
            func.count(user_role_table.c.role_uuid).label("role_count"),
            user_alias.family_name.label("family_name"),
        )
        .select_from(user_alias)
        .join(user_role_table, user_alias.uuid == user_role_table.c.user_uuid)
        .group_by(user_alias.name, user_alias.family_name)
    )
    __policy_model_class__ = UserModel
    __policies__ = [RoleBasedAccessPolicy("test_admin")]


async def test_user_role_view(app: TestApp) -> None:
    """
    Test the UserRoleView class.
    """
    # Create some test users
    alice = await create_test_user("Alice", "Smith")
    bob = await create_test_user("Bob", "Johnson")
    charlie = await create_test_user("Charlie", "Brown")

    # Create some test roles
    role_test_admin = await RoleModel(role_name="test_admin").persist()
    role_user = await RoleModel(role_name="user").persist()

    # Assign roles to users
    await alice.add_role(role_test_admin)
    await alice.add_role(role_user)
    await bob.add_role(role_user)
    await charlie.add_role(role_user)

    # Query the user role view
    user_roles = await UserRoleTestView.get_list()
    assert len(user_roles) >= 4
    alice_roles = [role for role in user_roles if role.user_name == "Alice Smith"]
    assert len(alice_roles) == 2

    # Query the user count view
    user_count = await RolesPerUserTestView.get_list()
    assert len(user_count) >= 3
    alice_count = next((user for user in user_count if user.user_name == "Alice Smith"), None)
    assert alice_count is not None
    assert alice_count.role_count == 2

    # test get one or none
    alice_role = await UserRoleTestView.get_one_or_none(role_name="test_admin", user_name="Alice Smith")
    assert alice_role is not None
    assert alice_role.role_name == "test_admin"

    # test get list with filtering by key
    user_roles_filtered = await UserRoleTestView.get_list(role_name="user")
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
    role_test_admin = await RoleModel(role_name="test_admin").persist()
    role_user = await RoleModel(role_name="user").persist()
    # Assign roles to users
    await alice.add_role(role_user)
    await bob.add_role(role_user)
    await charlie.add_role(role_user)

    async with ExecutionContext(alice.uuid):
        # Alice does not have the test_admin role, so she should not see any results
        user_roles = await UserRoleTestView.get_list_with_policies()
        assert len(user_roles) == 0
        user_count = await RolesPerUserTestView.get_list_with_policies()
        assert len(user_count) == 0

        await alice.add_role(role_test_admin)

        # Now Alice has the test_admin role, so she should see all users
        user_roles = await UserRoleTestView.get_list_with_policies()
        assert len(user_roles) >= 4

        user_count = await RolesPerUserTestView.get_list_with_policies()
        assert len(user_count) >= 3
        alice_count = next((user for user in user_count if user.user_name == "Alice Smith"), None)
        assert alice_count is not None
        assert alice_count.role_count == 2


async def test_roles_per_user_view_pagination(app: TestApp) -> None:
    # Use a unique family_name for test isolation
    family_name = "PaginateViewTestFamily"
    # Create 25 users, each with a role
    role = await RoleModel(role_name="paginated_role").persist()
    for i in range(25):
        user = await create_test_user(f"PaginateViewTestUser{i}", family_name)
        await user.add_role(role)

    # Page 1, page size 10
    items, total = await RolesPerUserTestView.get_paginated_list(_per_page=10, _page=1, family_name=family_name)
    assert len(items) == 10
    assert total == 25
    assert all(item.family_name == family_name for item in items)

    # Page 2, page size 10
    items, total = await RolesPerUserTestView.get_paginated_list(_per_page=10, _page=2, family_name=family_name)
    assert len(items) == 10
    assert total == 25
    assert all(item.family_name == family_name for item in items)

    # Page 3, page size 10 (should have 5 users)
    items, total = await RolesPerUserTestView.get_paginated_list(_per_page=10, _page=3, family_name=family_name)
    assert len(items) == 5
    assert total == 25
    assert all(item.family_name == family_name for item in items)

    # Page 4, page size 10 (should be empty)
    items, total = await RolesPerUserTestView.get_paginated_list(_per_page=10, _page=4, family_name=family_name)
    assert len(items) == 0
    assert total == 25
