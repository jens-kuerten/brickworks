import asyncio
import functools
import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable, Set
from dataclasses import dataclass
from typing import ParamSpec, Protocol, TypeVar, cast, runtime_checkable

from redis.asyncio import Redis

from brickworks.core.settings import settings

logger = logging.getLogger(__name__)


P = ParamSpec("P")  # parameters of cached function
R = TypeVar("R")  # return type of cached function
R_co = TypeVar("R_co", covariant=True)

NAMESPACE_LRU_CACHE = "LRU_CACHE"


@dataclass
class _CacheEntry:
    expiration_time: int
    value: str


@runtime_checkable
class LruCacheWrapper(Protocol[P, R_co]):
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Awaitable[R_co]: ...
    async def cache_clear(self) -> None: ...


class BrickworksCache:
    """Caches keys either in memory or in redis"""

    _redis_client: Redis
    _memory_cache: dict[str, _CacheEntry] = {}
    _memory_queue: dict[str, list[str]] = {}
    _memory_sets: dict[str, set[str]] = {}
    _memory_cache_lock: asyncio.Lock = asyncio.Lock()
    PREFIX = "brickworks"

    def __init__(self) -> None:
        if settings.USE_REDIS:
            self._redis_client = Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD,
            )
        else:
            logger.warning("Using memory cache. This is not recommended for production use.")

    def _generate_key(self, key: str, namespace: str, master_tenant: bool) -> str:
        tenant: str = settings.MASTER_DB_SCHEMA
        if not master_tenant:
            from brickworks.core.auth.executioncontext import execution_context

            tenant_schema = execution_context.tenant_schema
            if not tenant_schema:
                raise ValueError("Tried to access current tenant before auth context has a tenant set")
            tenant = tenant_schema

        # Validate that PREFIX, tenant, and namespace do not contain ':'
        if ":" in self.PREFIX:
            raise ValueError("PREFIX should not contain ':'")
        if ":" in tenant:
            raise ValueError("Tenant should not contain ':'")
        if ":" in namespace:
            raise ValueError("Namespace should not contain ':'")
        if ":" in key:
            raise ValueError("Key should not contain ':'")
        return f"{self.PREFIX}:{tenant}:{namespace}:{key}"

    def _parse_key(self, key: str) -> tuple[str, str, str]:
        # separate the key into its components to retrieve tenant namespace and key
        split = key.split(":")
        if len(split) != 4:
            raise ValueError(f"key {key} does not follow the schema prefix:tenant:namespace:key")
        return (split[1], split[2], split[3])

    async def push_to_queue(
        self, queue: str, value: str, namespace: str = "default", master_tenant: bool = False
    ) -> None:
        """Pushes a value to a queue. If no namespace is given, the default namespace is used."""
        cache_key = self._generate_key(queue, namespace=namespace, master_tenant=master_tenant)
        if settings.USE_REDIS:
            # need to use cast here to help out pylance
            await cast(
                Awaitable[int],
                self._redis_client.rpush(cache_key, value),
            )
        else:
            if cache_key not in self._memory_queue:
                self._memory_queue[cache_key] = []
            self._memory_queue[cache_key].append(value)

    async def pop_from_queue(self, queue: str, namespace: str = "default", master_tenant: bool = False) -> str | None:
        """Pops a value from a queue. If no namespace is given, the default namespace is used."""
        cache_key = self._generate_key(queue, namespace=namespace, master_tenant=master_tenant)
        if settings.USE_REDIS:
            # need to use cast here to help out pylance
            res: bytes = await cast(Awaitable[bytes], self._redis_client.lpop(cache_key))
            return res.decode("utf-8") if res else None
        if cache_key not in self._memory_queue:
            return None
        if not self._memory_queue[cache_key]:
            return None
        return self._memory_queue[cache_key].pop(0)

    async def get_key(self, key: str, namespace: str = "default", master_tenant: bool = False) -> str | None:
        """Retrieves a key from the cache. If no namespace is given, the default namespace is used."""
        cache_key = self._generate_key(key, namespace=namespace, master_tenant=master_tenant)
        if settings.USE_REDIS:
            res = await self._redis_client.get(cache_key)
            return res.decode("utf-8") if res else None

        cache_entry = self._memory_cache.get(cache_key)
        if cache_entry is None:
            return None
        if cache_entry.expiration_time < int(time.time()):
            del self._memory_cache[cache_key]
            return None
        return cache_entry.value

    async def set_key(
        self,
        key: str,
        value: str,
        namespace: str = "default",
        expire: int = 3600 * 24 * 7,
        master_tenant: bool = False,
        indices: list[str] | None = None,
        nx: bool = False,
    ) -> bool:
        """Sets a key in the cache. If no namespace is given, the default namespace is used.
        Cache expiration time is 7 days by default.
        If nx is True, only set if key does not exist (like Redis SETNX).
        Returns True if the key was set, False otherwise.
        """
        if not isinstance(value, str):
            raise ValueError(f"Cached value must be a string. Got {type(value)}")

        cache_key = self._generate_key(key, namespace=namespace, master_tenant=master_tenant)
        if settings.USE_REDIS:
            result = await self._redis_client.set(cache_key, value, ex=expire, nx=nx)
            if not result:
                return False
        else:
            now = int(time.time())
            async with self._memory_cache_lock:
                entry = self._memory_cache.get(cache_key)
                if nx and entry is not None and entry.expiration_time > now:
                    return False
                self._memory_cache[cache_key] = _CacheEntry(now + expire, value)
        for index in indices or []:
            await self.add_to_index(index, key, namespace, master_tenant=master_tenant)
        return True

    async def delete_key(self, key: str, namespace: str = "default", master_tenant: bool = False) -> None:
        """Deletes a key from the cache. If no namespace is given, the default namespace is used."""
        cache_key = self._generate_key(key, namespace=namespace, master_tenant=master_tenant)
        if await self.get_key(key, namespace, master_tenant=master_tenant) is None:
            return
        if settings.USE_REDIS:
            await self._redis_client.delete(cache_key)
        else:
            del self._memory_cache[cache_key]

    async def refresh_key(
        self,
        key: str,
        namespace: str = "default",
        expire: int = 3600 * 24 * 7,
        master_tenant: bool = False,
    ) -> None:
        """Refreshes the expiration time of a key in the cache."""
        cache_key = self._generate_key(key, namespace=namespace, master_tenant=master_tenant)
        if settings.USE_REDIS:
            await self._redis_client.expireat(cache_key, int(time.time()) + expire)
        else:
            cache_entry = self._memory_cache.get(cache_key)
            if cache_entry is None:
                return
            cache_entry.expiration_time = int(time.time()) + expire

    def delete_expired_entries(self) -> None:
        """Deletes all expired entries from the memory cache.
        Doesn't do anyting if redis is used.
        """
        if settings.USE_REDIS:
            return
        for key, cache_entry in self._memory_cache.items():
            if cache_entry.expiration_time < int(time.time()):
                del self._memory_cache[key]

    async def attempt_distributed_lock(self, lock_name: str, ttl: int = 10, master_tenant: bool = False) -> bool:
        """Attempts to acquire a distributed lock using Redis or in-memory cache.
        Returns True if the lock was acquired, False otherwise.
        ttl: The time-to-live (expiration) for the lock in seconds.
        """
        return await self.set_key(
            lock_name, "1", namespace="__locks__", expire=ttl, nx=True, master_tenant=master_tenant
        )

    async def release_distributed_lock(self, lock_name: str, master_tenant: bool = False) -> None:
        """Releases a distributed lock."""
        await self.delete_key(lock_name, namespace="__locks__", master_tenant=master_tenant)

    async def add_to_set(
        self,
        key: str,
        *values: str,
        namespace: str = "default",
        master_tenant: bool = False,
    ) -> int:
        """Add one or more members to a set. Returns the number of elements added."""
        cache_key = self._generate_key(key, namespace=namespace, master_tenant=master_tenant)
        if settings.USE_REDIS:
            return await cast(Awaitable[int], self._redis_client.sadd(cache_key, *values))
        s = self._memory_sets.setdefault(cache_key, set())
        before = len(s)
        s.update(values)
        return len(s) - before

    async def remove_from_set(
        self,
        key: str,
        *values: str,
        namespace: str = "default",
        master_tenant: bool = False,
    ) -> int:
        """Remove one or more members from a set. Returns the number of elements removed."""
        cache_key = self._generate_key(key, namespace=namespace, master_tenant=master_tenant)
        if settings.USE_REDIS:
            return await cast(Awaitable[int], self._redis_client.srem(cache_key, *values))
        s = self._memory_sets.get(cache_key, set())
        before = len(s)
        for v in values:
            s.discard(v)
        removed = before - len(s)
        if not s:
            self._memory_sets.pop(cache_key, None)
        return removed

    async def get_set_members(
        self,
        key: str,
        namespace: str = "default",
        master_tenant: bool = False,
    ) -> Set[str]:
        """Get all members of a set. Returns a set of strings."""
        cache_key = self._generate_key(key, namespace=namespace, master_tenant=master_tenant)
        if settings.USE_REDIS:
            members = await cast(Awaitable[set[str]], self._redis_client.smembers(cache_key))
            return {m.decode("utf-8") if isinstance(m, bytes) else str(m) for m in members}
        return set(self._memory_sets.get(cache_key, set()))

    async def is_set_member(
        self,
        key: str,
        value: str,
        namespace: str = "default",
        master_tenant: bool = False,
    ) -> bool:
        """Check if a value is a member of a set."""
        cache_key = self._generate_key(key, namespace=namespace, master_tenant=master_tenant)
        if settings.USE_REDIS:
            result = await cast(Awaitable[int], self._redis_client.sismember(cache_key, value))
            return bool(result)
        return value in self._memory_sets.get(cache_key, set())

    async def add_to_index(
        self,
        index: str,
        key: str,
        namespace: str = "default",
        master_tenant: bool = False,
    ) -> None:
        """Adds a key to an index and registers the index in the central index set."""
        index_key = f"__index__.{index}"
        # Central set of all indexes (per namespace/tenant)
        central_index_set = "__indexes__"
        await self.add_to_set(
            central_index_set,
            self._generate_key(index_key, namespace=namespace, master_tenant=master_tenant),
            namespace="default",
            master_tenant=master_tenant,
        )
        # Add the key to the index set
        await self.add_to_set(
            index_key,
            self._generate_key(key, namespace=namespace, master_tenant=master_tenant),
            namespace=namespace,
            master_tenant=master_tenant,
        )

    async def _clean_index(self, cache_key: str) -> None:
        """Removes keys from the index that don't exist anymore"""
        if settings.USE_REDIS:
            # get all keys in the index
            keys = await cast(Awaitable[set[str]], self._redis_client.smembers(cache_key))
            for key in keys:
                # check if the key exists, if not delete from the index
                if not await self._redis_client.exists(key):
                    await cast(Awaitable[int], self._redis_client.srem(cache_key, key))
        else:
            # get all keys in the index
            keys = self._memory_sets.get(cache_key, set()).copy()
            for key in keys:
                if key not in self._memory_cache:
                    self._memory_sets[cache_key].discard(key)
            if not self._memory_sets[cache_key]:
                self._memory_sets.pop(cache_key, None)

    async def clean_all_indices(self) -> None:
        index_cache_keys = await self.get_set_members("__indexes__", namespace="default")
        for cache_key in index_cache_keys:
            await self._clean_index(cache_key)

    async def list_keys_by_index(
        self, index: str, namespace: str = "default", master_tenant: bool = False
    ) -> list[str]:
        index_key = f"__index__.{index}"
        await self._clean_index(self._generate_key(index_key, namespace, master_tenant))
        cache_keys = await self.get_set_members(index_key, namespace, master_tenant)
        return [self._parse_key(cache_key)[2] for cache_key in cache_keys]

    def lru_cache(
        self, expire: int = 3600 * 24 * 7, master_tenant: bool = False
    ) -> Callable[[Callable[P, Awaitable[R]]], LruCacheWrapper[P, R]]:
        """Decorator to cache async function results using BrickworksCache.
        Only works with JSON-serializable arguments and return values.
        """

        def decorator(func: Callable[P, Awaitable[R]]) -> LruCacheWrapper[P, R]:
            fqpn = f"{func.__module__}.{func.__qualname__}"

            @functools.wraps(func)
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                # Serialize args and kwargs to a stable string
                try:
                    key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True)
                except Exception as e:
                    raise ValueError(f"Arguments to {fqpn} are not JSON serializable: {e}") from e
                key_hash = hashlib.sha256(key_data.encode()).hexdigest()
                cache_key = f"{fqpn}-{key_hash}"
                cached = await self.get_key(cache_key, namespace=NAMESPACE_LRU_CACHE, master_tenant=master_tenant)
                if cached is not None:
                    return cast(R, json.loads(cached))
                result = await func(*args, **kwargs)
                try:
                    result_json = json.dumps(result, sort_keys=True)
                except Exception as e:
                    raise ValueError(f"Return value of {fqpn} is not JSON serializable: {e}") from e
                await self.set_key(
                    cache_key,
                    result_json,
                    namespace=NAMESPACE_LRU_CACHE,
                    expire=expire,
                    master_tenant=master_tenant,
                    indices=[fqpn],
                )
                return result

            async def cache_clear(master_tenant: bool = False) -> None:
                keys = await self.list_keys_by_index(fqpn, namespace=NAMESPACE_LRU_CACHE, master_tenant=master_tenant)
                for key in keys:
                    await self.delete_key(key, namespace=NAMESPACE_LRU_CACHE, master_tenant=master_tenant)

            wrapper.__setattr__("cache_clear", cache_clear)
            return wrapper  # type: ignore[return-value]

        return decorator


cache = BrickworksCache()
