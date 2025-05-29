from collections.abc import Generator
from unittest.mock import patch

import pytest

from brickworks.core.auth.executioncontext import ExecutionContext
from brickworks.core.cache import cache
from brickworks.core.settings import settings
from tests.conftest import TestApp

TCacheBackendFixture = Generator[None, None, None]


@pytest.fixture(params=[False, True], ids=["memory", "redis"])
def cache_backend(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    with patch.object(settings, "USE_REDIS", request.param):
        yield


@pytest.mark.asyncio
async def test_set_and_get(app: TestApp, cache_backend: TCacheBackendFixture) -> None:
    await cache.set_key("foo", "bar")
    value = await cache.get_key("foo")
    assert value == "bar"


async def test_set_and_get_with_tenant(app: TestApp, cache_backend: TCacheBackendFixture) -> None:
    # set everything with expire=2, to automatically clean up after the test

    # set in master tenant (tests run in master tenant by default)
    await cache.set_key("foo", "bar", namespace="test", expire=2)
    async with ExecutionContext(tenant_schema="test_schema"):
        assert await cache.get_key("foo", namespace="test") is None  # key doesn't exist in test tenant
        await cache.set_key("foo", "bar_test", namespace="test", expire=2)  # set in test tenant

        assert await cache.get_key("foo", namespace="test", master_tenant=True) == "bar"  # from master tenant
        assert await cache.get_key("foo", namespace="test") == "bar_test"  # from test tenant


@pytest.mark.asyncio
async def test_delete(app: TestApp, cache_backend: TCacheBackendFixture) -> None:
    await cache.set_key("delkey", "todelete")
    await cache.delete_key("delkey")
    value = await cache.get_key("delkey")
    assert value is None


@pytest.mark.asyncio
async def test_delete_with_tenant(app: TestApp, cache_backend: TCacheBackendFixture) -> None:
    # Set in master tenant
    await cache.set_key("delkey", "master_value", namespace="test", expire=2)
    async with ExecutionContext(tenant_schema="test_schema"):
        # Should not see master tenant's key
        assert await cache.get_key("delkey", namespace="test") is None
        # Set in tenant
        await cache.set_key("delkey", "tenant_value", namespace="test", expire=2)
        # Delete in tenant
        await cache.delete_key("delkey", namespace="test")
        assert await cache.get_key("delkey", namespace="test") is None
        # Master tenant's value should still exist
        assert await cache.get_key("delkey", namespace="test", master_tenant=True) == "master_value"
    # Delete in master
    await cache.delete_key("delkey", namespace="test")
    assert await cache.get_key("delkey", namespace="test") is None


@pytest.mark.asyncio
async def test_push_and_pop_queue(app: TestApp, cache_backend: TCacheBackendFixture) -> None:
    await cache.push_to_queue("q", "a")
    await cache.push_to_queue("q", "b")
    v1 = await cache.pop_from_queue("q")
    v2 = await cache.pop_from_queue("q")
    v3 = await cache.pop_from_queue("q")
    assert v1 == "a"
    assert v2 == "b"
    assert v3 is None


@pytest.mark.asyncio
async def test_queue_with_tenant(app: TestApp, cache_backend: TCacheBackendFixture) -> None:
    # Push to queue in master tenant
    await cache.push_to_queue("q", "master_a", namespace="test")
    async with ExecutionContext(tenant_schema="test_schema"):
        # Queue should be empty in tenant
        assert await cache.pop_from_queue("q", namespace="test") is None
        # Push to queue in tenant
        await cache.push_to_queue("q", "tenant_a", namespace="test")
        await cache.push_to_queue("q", "tenant_b", namespace="test")
        v1 = await cache.pop_from_queue("q", namespace="test")
        v2 = await cache.pop_from_queue("q", namespace="test")
        v3 = await cache.pop_from_queue("q", namespace="test")
        assert v1 == "tenant_a"
        assert v2 == "tenant_b"
        assert v3 is None
    # Master queue should still have its value
    v_master = await cache.pop_from_queue("q", namespace="test")
    assert v_master == "master_a"
    assert await cache.pop_from_queue("q", namespace="test") is None


@pytest.mark.asyncio
async def test_acquire_and_release_lock(app: TestApp, cache_backend: TCacheBackendFixture) -> None:
    acquired = await cache.attempt_distributed_lock("lock1")
    assert acquired is True
    # In memory mode, always returns True
    await cache.release_distributed_lock("lock1")


@pytest.mark.asyncio
async def test_lru_cache_simple(app: TestApp, cache_backend: TCacheBackendFixture) -> None:
    call_counter = {"count": 0}

    @cache.lru_cache(expire=2)
    async def add(a: int, b: int) -> int:
        call_counter["count"] += 1
        return a + b

    # First call, should compute and cache
    result1 = await add(1, 2)
    assert result1 == 3
    assert call_counter["count"] == 1

    # Second call, same args, should hit cache
    result2 = await add(1, 2)
    assert result2 == 3
    assert call_counter["count"] == 1  # No increment, cache hit

    # Different args, should compute again
    result3 = await add(2, 3)
    assert result3 == 5
    assert call_counter["count"] == 2


@pytest.mark.asyncio
async def test_lru_cache_with_kwargs(app: TestApp, cache_backend: TCacheBackendFixture) -> None:
    call_counter = {"count": 0}

    @cache.lru_cache(expire=2)
    async def concat(a: int, b: int = 0) -> str:
        call_counter["count"] += 1
        return f"{a}-{b}"

    r1 = await concat(1, b=2)
    r2 = await concat(1, b=2)
    r3 = await concat(1, b=3)
    assert r1 == "1-2"
    assert r2 == "1-2"
    assert r3 == "1-3"
    assert call_counter["count"] == 2  # Only two unique calls


@pytest.mark.asyncio
async def test_lru_cache_json_serialization_error(app: TestApp, cache_backend: TCacheBackendFixture) -> None:
    @cache.lru_cache(expire=2)
    async def unserializable(arg: int) -> object:
        class NotSerializable:
            pass

        return NotSerializable()  # not JSON serializable

    with pytest.raises(ValueError):
        await unserializable(1)


@pytest.mark.asyncio
async def test_lru_cache_tenant_isolation(app: TestApp, cache_backend: TCacheBackendFixture) -> None:
    call_counter = {"count": 0}

    @cache.lru_cache(expire=2)
    async def add(a: int, b: int) -> int:
        call_counter["count"] += 1
        return a + b

    # Set in master tenant (default)
    result_master = await add(1, 2)
    assert result_master == 3
    assert call_counter["count"] == 1

    # Should hit cache in master tenant
    result_master2 = await add(1, 2)
    assert result_master2 == 3
    assert call_counter["count"] == 1

    # Switch to another tenant
    from brickworks.core.auth.executioncontext import ExecutionContext

    async with ExecutionContext(tenant_schema="test_schema"):
        # Should NOT hit cache, should call function again
        result_tenant = await add(1, 2)
        assert result_tenant == 3
        assert call_counter["count"] == 2
        # Should hit cache in tenant
        result_tenant2 = await add(1, 2)
        assert result_tenant2 == 3
        assert call_counter["count"] == 2

    # Back to master tenant, should still hit master cache
    result_master3 = await add(1, 2)
    assert result_master3 == 3
    assert call_counter["count"] == 2


@pytest.mark.asyncio
async def test_set_add_and_members(app: TestApp, cache_backend: TCacheBackendFixture) -> None:
    # Add to set
    added = await cache.add_to_set("myset", "a", "b", "c")
    assert added == 3
    # Add duplicate and new
    added2 = await cache.add_to_set("myset", "b", "d")
    assert added2 == 1  # Only 'd' is new
    # Get members
    members = await cache.get_set_members("myset")
    assert members == {"a", "b", "c", "d"}
    # clean up
    await cache.remove_from_set("myset", "a", "b", "c", "d")


@pytest.mark.asyncio
async def test_set_remove_and_membership(app: TestApp, cache_backend: TCacheBackendFixture) -> None:
    await cache.add_to_set("myset2", "x", "y", "z")
    # Remove one
    removed = await cache.remove_from_set("myset2", "y")
    assert removed == 1
    # Remove non-existent
    removed2 = await cache.remove_from_set("myset2", "not_in_set")
    assert removed2 == 0
    # Membership
    assert await cache.is_set_member("myset2", "x") is True
    assert await cache.is_set_member("myset2", "y") is False
    # Remove all
    await cache.remove_from_set("myset2", "x", "z")
    members = await cache.get_set_members("myset2")
    assert members == set()


@pytest.mark.asyncio
async def test_set_tenant_isolation(app: TestApp, cache_backend: TCacheBackendFixture) -> None:
    await cache.add_to_set("tenants", "foo", namespace="test", master_tenant=True)
    async with ExecutionContext(tenant_schema="test_schema"):
        # Should not see master tenant's set
        assert await cache.get_set_members("tenants", namespace="test") == set()
        await cache.add_to_set("tenants", "bar", namespace="test")
        assert await cache.is_set_member("tenants", "bar", namespace="test") is True
        assert await cache.is_set_member("tenants", "foo", namespace="test") is False
        # Master tenant's set should be unchanged
        assert await cache.get_set_members("tenants", namespace="test", master_tenant=True) == {"foo"}
    # Back to master tenant
    assert await cache.get_set_members("tenants", namespace="test") == {"foo"}

    # clean up
    await cache.remove_from_set("tenants", "foo", namespace="test")
    async with ExecutionContext(tenant_schema="test_schema"):
        await cache.remove_from_set("tenants", "bar", namespace="test")


@pytest.mark.asyncio
async def test_index_add_and_cleanup(app: TestApp, cache_backend: TCacheBackendFixture) -> None:
    # Add two keys with the same index
    await cache.set_key("k1", "v1", namespace="test", indices=["myindex"])
    await cache.set_key("k2", "v2", namespace="test", indices=["myindex"])
    # Both keys should be listed by index
    keys = await cache.list_keys_by_index("myindex", namespace="test")
    assert set(keys) == {"k1", "k2"}

    # Delete one key
    await cache.delete_key("k1", namespace="test")
    # The index should be cleaned up, only k2 remains
    keys_after = await cache.list_keys_by_index("myindex", namespace="test")
    assert set(keys_after) == {"k2"}

    # Delete the other key
    await cache.delete_key("k2", namespace="test")
    # Now the index should be empty
    keys_final = await cache.list_keys_by_index("myindex", namespace="test")
    assert keys_final == []


@pytest.mark.asyncio
async def test_index_tenant_isolation(app: TestApp, cache_backend: TCacheBackendFixture) -> None:
    # Add key in master tenant
    await cache.set_key("k1", "v1", namespace="test", indices=["myindex"])
    # Switch to tenant and add another key with the same index
    async with ExecutionContext(tenant_schema="test_schema"):
        await cache.set_key("k2", "v2", namespace="test", indices=["myindex"])
        # Only k2 should be visible in tenant
        keys_tenant = await cache.list_keys_by_index("myindex", namespace="test")
        assert set(keys_tenant) == {"k2"}
        # Master tenant's key should not be visible
        assert "k1" not in keys_tenant
    # Back to master tenant, only k1 should be visible
    keys_master = await cache.list_keys_by_index("myindex", namespace="test")
    assert set(keys_master) == {"k1"}
    # Clean up
    await cache.delete_key("k1", namespace="test")
    async with ExecutionContext(tenant_schema="test_schema"):
        await cache.delete_key("k2", namespace="test")


@pytest.mark.asyncio
async def test_lru_cache_clear(app: TestApp, cache_backend: TCacheBackendFixture) -> None:
    call_counter = {"count": 0}

    @cache.lru_cache(expire=10)
    async def add(a: int, b: int) -> int:
        call_counter["count"] += 1
        return a + b

    # Call and cache a value
    result1 = await add(1, 2)
    assert result1 == 3
    assert call_counter["count"] == 1

    # Should hit cache
    result2 = await add(1, 2)
    assert result2 == 3
    assert call_counter["count"] == 1

    # Clear the cache
    await add.cache_clear()

    # Should call function again (cache miss)
    result3 = await add(1, 2)
    assert result3 == 3
    assert call_counter["count"] == 2


@pytest.mark.asyncio
async def test_lru_cache_clear_tenant_isolation(app: TestApp, cache_backend: TCacheBackendFixture) -> None:
    call_counter = {"count": 0}

    @cache.lru_cache(expire=2)
    async def add(a: int, b: int) -> int:
        call_counter["count"] += 1
        return a + b

    # Call and cache in master tenant
    result_master = await add(1, 2)
    assert result_master == 3
    assert call_counter["count"] == 1

    # Should hit cache in master tenant
    result_master2 = await add(1, 2)
    assert result_master2 == 3
    assert call_counter["count"] == 1

    # Switch to tenant and call (should miss cache)
    async with ExecutionContext(tenant_schema="test_schema"):
        result_tenant = await add(1, 2)
        assert result_tenant == 3
        assert call_counter["count"] == 2
        # Should hit cache in tenant
        result_tenant2 = await add(1, 2)
        assert result_tenant2 == 3
        assert call_counter["count"] == 2
        # Clear cache in tenant
        await add.cache_clear()
        # Should call function again (cache miss in tenant)
        result_tenant3 = await add(1, 2)
        assert result_tenant3 == 3
        assert call_counter["count"] == 3
        # Should hit cache in tenant again
        result_tenant4 = await add(1, 2)
        assert result_tenant4 == 3
        assert call_counter["count"] == 3

    # Back to master tenant, should still hit master cache (not affected by tenant clear)
    result_master3 = await add(1, 2)
    assert result_master3 == 3
    assert call_counter["count"] == 3

    # Now clear cache in master tenant
    await add.cache_clear()
    result_master4 = await add(1, 2)
    assert result_master4 == 3
    assert call_counter["count"] == 4


@pytest.mark.asyncio
async def test_lock_exclusive(app: TestApp, cache_backend: TCacheBackendFixture) -> None:
    acquired1 = await cache.attempt_distributed_lock("locktest", ttl=2)
    assert acquired1 is True
    acquired2 = await cache.attempt_distributed_lock("locktest", ttl=2)
    assert acquired2 is False
    await cache.release_distributed_lock("locktest")
    acquired3 = await cache.attempt_distributed_lock("locktest", ttl=2)
    assert acquired3 is True
    await cache.release_distributed_lock("locktest")


@pytest.mark.asyncio
async def test_lock_expiry(app: TestApp, cache_backend: TCacheBackendFixture) -> None:
    import asyncio

    acquired1 = await cache.attempt_distributed_lock("lockexpire", ttl=1)
    assert acquired1 is True
    acquired2 = await cache.attempt_distributed_lock("lockexpire", ttl=1)
    assert acquired2 is False

    await asyncio.sleep(1.1)
    acquired3 = await cache.attempt_distributed_lock("lockexpire", ttl=1)
    assert acquired3 is True
    await cache.release_distributed_lock("lockexpire")
