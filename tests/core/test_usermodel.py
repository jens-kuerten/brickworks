from brickworks.core.models.role_model import RoleModel
from brickworks.core.models.user_model import UserModel
from tests.conftest import TestApp


async def test_role_add_remove(app: TestApp) -> None:
    role1 = await RoleModel(role_name="role1").persist()
    user_alice = await UserModel(
        sub="alice", given_name="Alice", family_name="Smith", name="Alice Smith", email="alice@example.com"
    ).persist()

    # add role by name
    await user_alice.add_role("role1")

    # adding the same role again should not cause issues
    await user_alice.add_role("role1")

    assert await user_alice.has_role("role1")

    # remove role
    await user_alice.remove_role("role1")

    assert not await user_alice.has_role("role1")

    # add role by object
    await user_alice.add_role(role1)
    assert await user_alice.has_role(role1)

    # remove role by object
    await user_alice.remove_role(role1)
    assert not await user_alice.has_role(role1)


async def test_give_role_permission(app: TestApp) -> None:
    await RoleModel(role_name="role1").persist()
    user_bob = await UserModel(
        sub="bob", given_name="Bob", family_name="Smith", name="Bob Smith", email="bob@example.com"
    ).persist()

    await user_bob.give_role_permission("role1", "read")
    # adding the same permission again should not cause issues
    await user_bob.give_role_permission("role1", "read")

    assert await user_bob.has_role_permission("role1", "read")

    # remove role permission
    await user_bob.remove_role_permission("role1", "read")
    # removing the same permission again should not cause issues
    await user_bob.remove_role_permission("role1", "read")
    assert not await user_bob.has_role_permission("role1", "read")
