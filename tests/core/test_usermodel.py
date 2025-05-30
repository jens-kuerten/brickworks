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


async def test_get_paginated_list(app: TestApp) -> None:
    # Use a unique family_name for test isolation
    test_family = "PaginateTestFamily"
    for i in range(25):
        await UserModel(
            sub=f"user{i}",
            given_name=f"User{i}",
            family_name=test_family,
            name=f"User{i} Test",
            email=f"user{i}@example.com",
        ).persist()

    # Page 1, page size 10
    items, total = await UserModel.get_paginated_list(_per_page=10, _page=1, family_name=test_family)
    assert len(items) == 10
    assert total == 25
    assert items[0].sub == "user0"

    # Page 2, page size 10
    items, total = await UserModel.get_paginated_list(_per_page=10, _page=2, family_name=test_family)
    assert len(items) == 10
    assert total == 25
    assert items[0].sub == "user10"

    # Page 3, page size 10 (should have 5 users)
    items, total = await UserModel.get_paginated_list(_per_page=10, _page=3, family_name=test_family)
    assert len(items) == 5
    assert total == 25
    assert items[0].sub == "user20"

    # Page 4, page size 10 (should be empty)
    items, total = await UserModel.get_paginated_list(_per_page=10, _page=4, family_name=test_family)
    assert len(items) == 0
    assert total == 25
