from unittest.mock import patch

from brickworks.core.acl.policies import (
    AllowActiveUserAccessPolicy,
    AllowPublicAccessPolicy,
    RoleAllowPolicy,
    RoleBasedAccessPolicy,
)
from brickworks.core.auth.executioncontext import ExecutionContext
from brickworks.core.models.role_model import RoleModel
from brickworks.core.models.user_model import UserModel, UserStatusEnum
from tests.conftest import TestApp
from tests.core.utils import create_test_user


async def test_get_list(app: TestApp) -> None:
    # Add test users
    user_alice = await create_test_user("Alice", "Smith")
    user_bob = await create_test_user("Bob", "Smith")
    result = await UserModel.get_list()

    assert len(result) >= 2
    assert user_alice in result
    assert user_bob in result


async def test_no_policy_set(app: TestApp) -> None:
    user_alice = await create_test_user("Alice", "Smith")
    await create_test_user("Bob", "Smith")

    async with ExecutionContext(user_alice.uuid):
        result = await UserModel.get_list_with_policies()
        # No policies are applied so we should see nobody
        assert len(result) == 0


async def test_allow_public_access_policy(app: TestApp) -> None:
    await create_test_user("Alice", "Smith")
    await create_test_user("Bob", "Smith")

    async with ExecutionContext(None):
        # no logged in user
        result = await UserModel.get_list_with_policies()
        # No policies are applied so we should see nobody
        assert len(result) >= 0

    # add AllowPublicAccessPolicy to the UserModel
    with patch.object(UserModel, "__policies__", [AllowPublicAccessPolicy()]):
        async with ExecutionContext(None):
            # no logged in user
            result = await UserModel.get_list_with_policies()
            # all users should be visible
            assert len(result) >= 2


async def test_allow_active_user_access_policy(app: TestApp) -> None:
    user_alice = await create_test_user("Alice", "Smith")
    user_bob = await create_test_user("Bob", "Smith")
    user_bob.status = UserStatusEnum.INACTIVE
    await user_bob.persist()

    # add AllowActiveUserAccessPolicy to the UserModel
    with patch.object(UserModel, "__policies__", [AllowActiveUserAccessPolicy()]):
        async with ExecutionContext(user_alice.uuid):
            result = await UserModel.get_list_with_policies()
            # Alice is active, so she should see Bob
            assert len(result) >= 2

        async with ExecutionContext(user_bob.uuid):
            result = await UserModel.get_list_with_policies()
            # Bob is inactive, so he should not see anyone
            assert len(result) == 0

        async with ExecutionContext(None):
            result = await UserModel.get_list_with_policies()
            # no logged in user
            assert len(result) == 0


async def test_role_allow_policy(app: TestApp) -> None:
    role1 = await RoleModel(role_name="role1").persist()
    user_alice = await create_test_user("Alice", "Smith")
    user_bob = await create_test_user("Bob", "Smith")

    await user_bob.give_role_permission("role1", "read")

    # add RoleAllowPolicy to the UserModel
    with patch.object(UserModel, "__policies__", [RoleAllowPolicy(role1.role_name, "read")]):
        # query as Alice
        async with ExecutionContext(user_alice.uuid):
            result = await UserModel.get_list_with_policies()
            # Alice does not have the role, so she should not see Bob
            assert len(result) == 0

            # give Alice the role
            await user_alice.add_role(role1)
            result = await UserModel.get_list_with_policies()
            # Alice has the role, so she should see Bob
            assert len(result) == 1


async def test_role_based_access_policy_permissive(app: TestApp) -> None:
    role1 = await RoleModel(role_name="role1").persist()
    user_alice = await create_test_user("Alice", "Smith")
    await create_test_user("Bob", "Smith")

    # add RoleBasedAccessPolicy to the UserModel
    with patch.object(UserModel, "__policies__", [RoleBasedAccessPolicy(role1.role_name)]):
        # query as Alice
        async with ExecutionContext(user_alice.uuid):
            result = await UserModel.get_list_with_policies()

            # Alice does not have the role, so she should not see Bob
            assert len(result) == 0

            # give Alice the role
            await user_alice.add_role(role1)
            result = await UserModel.get_list_with_policies()
            # Alice has the role, so she should see all users
            assert len(result) >= 2


async def test_role_based_access_policy_restrictive(app: TestApp) -> None:
    role1 = await RoleModel(role_name="role1").persist()
    user_alice = await create_test_user("Alice", "Smith")
    await create_test_user("Bob", "Smith")

    # add RoleBasedAccessPolicy to the UserModel set to retrictive
    with patch.object(UserModel, "__policies__", [RoleBasedAccessPolicy(role1.role_name, restrictive=True)]):
        # query as Alice
        async with ExecutionContext(user_alice.uuid):
            result = await UserModel.get_list_with_policies()

            # Alice does not have the role, so she should not see Bob
            assert len(result) == 0

            # give Alice the role
            await user_alice.add_role(role1)
            result = await UserModel.get_list_with_policies()

            # Alice still can't see anyone because the policy is restrictive
            assert len(result) == 0

    # also add AllowActiveUserAccessPolicy to the UserModel
    with patch.object(
        UserModel,
        "__policies__",
        [RoleBasedAccessPolicy(role1.role_name, restrictive=True), AllowActiveUserAccessPolicy()],
    ):
        # query as Alice
        async with ExecutionContext(user_alice.uuid):
            # remove role from Alice
            await user_alice.remove_role(role1)

            # Alice does not have the role, so she should not see Bob, dispite the AllowActiveUserAccessPolicy
            result = await UserModel.get_list_with_policies()
            assert len(result) == 0

            # give Alice the role
            await user_alice.add_role(role1)
            result = await UserModel.get_list_with_policies()
            # Alice has the role, so she should see all users
            assert len(result) >= 2
