# Caching

The `BrickworksCache` class provides a unified interface for caching in memory or Redis, supporting both key-value and queue-based operations, as well as distributed locking and an async LRU cache decorator.
The cache is fully async, meaning you can NOT use it from within syncronous functions!

!!! warning
    For production it is strongly advised to use Redis, because otherwise the cache is not shared between multiple replicas of your application!

The Redis connection can be configured with the following environment variables:

```
USE_REDIS = "1"
REDIS_HOST = "localhost"
REDIS_PORT = "6379"
REDIS_DB = "0"
REDIS_PASSWORD = ""
```

## Initialization

The cache is available as a singleton:

```python
from brickworks.core.cache import cache
```
## Tenancy

All cache operations are tenant-aware. By default, operations are scoped to the current tenant.
If you want to cache something "globaly" accross tenants, pass the parameter `master_tenant=True` to the get or set methods.

## Key-Value Caching

### Set a Value
```python
await cache.set_key("mykey", "myvalue", namespace="default", expire=3600)
```

- `key`: The cache key (string)
- `value`: The value to store (string)
- `namespace`: Optional, default is "default" - set a namespace to prevent key collisions
- `expire`: Expiration in seconds (default: 7 days)


!!! warning
    Keys and namespaces must not contain a colon (:)!

### Get a Value
```python
value = await cache.get_key("mykey", namespace="default")
```
Returns the string value or `None` if not found or expired.

### Delete a Value
```python
await cache.delete_key("mykey", namespace="default")
```

!!! note
    You can only cache string values! If you need to store other data types, either convert them to string, or serialize them with e.g. json.

### Refresh Expiration

```python
await cache.refresh_key("mykey", namespace="default", expire=3600)
```

## Queue Operations

### Push to Queue
```python
await cache.push_to_queue("queue_name", "item", namespace="default")
```

### Pop from Queue
```python
item = await cache.pop_from_queue("queue_name", namespace="default")
```
Returns the next item (string) or `None` if the queue is empty.

## Distributed Locking

Distributed locks are mainly intended for coordinating background services in environments with multiple app replicas. For example, if you deploy several instances of your app, a background service (such as one sending email notifications) might run in every replica. Without coordination, this could result in duplicate work (e.g., multiple emails sent for the same event).

To prevent this, a service can attempt to acquire a distributed lock before performing an operation. If the lock is acquired, the service proceeds; if not, it skips the operation, knowing another replica is already handling it. The `ttl` parameter ensures that if a service or replica crashes and doesn't release the lock, the lock will eventually expire and allow another replica to take over.

!!! warning
    Using distributed locks for coordinating between processes or replicas only works if you use Redis as a backend!

### Acquire a Lock
```python
acquired = await cache.attempt_distributed_lock("lock_name", ttl=10)
```
Returns `True` if the lock was acquired.

- `ttl`: The time-to-live (expiration) for the lock in seconds.

### Release a Lock
```python
await cache.release_distributed_lock("lock_name")
```

## LRU Cache Decorator

You can cache the results of async functions with JSON-serializable arguments and return values:

```python
@cache.lru_cache(expire=60)
async def compute(a: int, b: int) -> int:
    ...
```

And clear the cache with:

```python
await compute.cache_clear()
```

Note: the cache is only cleared for the currently active tenant!

There are a few key differences between `functools.lru_cache` and Brickworks `cache.lru_cache`

- **Tenant Awareness:** The Brickworks cache is tenant-aware, so results are isolated per tenant by default.
- **Distributed Cache:** If enabled, the Brickworks cache is stored in Redis. This enables multiple replicas of the application to share the same cache.
- **Time based expire:** Cached results expire automatically after a certain time. (default 1 week)
- **Async only:** Brickworks lru_cache only works with async functions, because otherwise the async redis connection could not be used

## Indexing and Listing Keys

The Brickworks cache supports indexing, which allows you to group related cache keys under a named index. This is useful when you want to efficiently list or manage all keys associated with a particular group (for example, all cache entries related to a specific resource type).

When you set a key, you can specify one or more indices:

```python
await cache.set_key("user-123", "userdata 123", indices=["users"])
await cache.set_key("user-456", "userdata 456", indices=["users"])
```

You can then list all keys associated with an index:

```python
user_keys = await cache.list_keys_by_index("users")
# user_keys will be ["user-123", "user-456"]
```

If you delete a key, it is automatically removed from the index. Indices are tenant-aware, so each tenant has its own set of indices and indexed keys.

This feature is especially useful for cache invalidation or performing bulk operations on related cache entries, where you would otherwise need to use the Redis `SCAN` command to find related keys.

## Cache Consistency and Post-commit Callbacks

When your cache depends on the state of the database (for example, when caching the results of a query or storing metadata about database objects), you should only update or invalidate the cache after the database transaction has been successfully committed. Otherwise, if the transaction is rolled back, your cache could become inconsistent with the actual database state.

Brickworks supports post-commit callbacks for this purpose. You can register a cache update or invalidation function to be called after a successful commit:

```python
from brickworks.core import db, cache

async def invalidate_cache():
    await cache.delete_key("mykey")

# Register the callback inside a session context
db.add_post_commit_callback(invalidate_cache)
```

This ensures that the cache is only updated if the database changes are actually persisted. See the [Database Session documentation](database_session.md#post-commit-callbacks) for more details.

## Example

```python
# Set and get a value
await cache.set_key("foo", "bar")
val = await cache.get_key("foo")

# Use as a queue
await cache.push_to_queue("myqueue", "item1")
item = await cache.pop_from_queue("myqueue")

# Use the LRU cache decorator
@cache.lru_cache(expire=120)
async def add(a: int, b: int) -> int:
    return a + b
result = await add(1, 2)
await add.cache_clear()
```
