# Database Session

Brickworks is build on SQLAlchemy and thus uses the [SQLAlchemy AsyncSession](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#sqlalchemy.ext.asyncio.AsyncSession) for database access.

Brickworks currently only support Postgres as a database backend. To set the connection parameters you can use the following environment variables:

```
DB_HOST= "127.0.0.1:5432"
DB_USER = "postgres"
DB_PASSWORD = ""
DB_NAME = "postgres"
```

## Database session in requests
Each request to an api endpoint is automatically wrapped in a database session context by the `DBSessionMiddleware`.
Inside the context you can access the database session like this:

```python
from brickworks.core import db

async def myfunc():
    await db.session.execute(...)
```

The session is automatically committed once the request is finished and no Exception was raised.

You can manually trigger a commit of the current session, however that will prevent a rollback of any changes that have been performed up to this point, so it is generally not advised to do so.

```python
await db.session.commit()  # not advised!
```

Instead consider if a flush would be sufficient for your use-case, as this can still be rolled back.

```python
await db.session.flush()
```


!!! warning
    The database session is not safe for use in concurrent tasks. If you want to access the database within concurrent tasks, each task needs to create its own database session context!

## Database session in scripts

If you need to access the database outside of a request context (e.g. in some CLI script, or inside of concurrent tasks) you need to create a database session context yourself.

```python
from brickworks.core import db
import asyncio

async def async_main():
    async with db(commit_on_exit=True):
        # now we have access to the database
        await db.session.execute(...)

if __name__ == "__main__":
    asyncio.run(async_main())
```


The session object is only valid within the context manager and should not be reused outside of it. Attempting to use the session outside of its context will raise an error.
The session is tied to the current async context and cannot be shared between threads or tasks.

Example of incorrect usage:

```python
async with db():
    session = db.session
# session is now invalid and will raise an error if used
await session.execute(...)  # This will fail!
```


## Rollback on exceptions

If an unhandled Exception is raised inside a database session or a request returns a status code >=400, the session is rolled back. If you catch and handle the exception in your code, the session will not be rolled back automatically.

## Post-commit Callbacks

Sometimes you need to perform actions that should only happen if the database transaction is successful. For example, if you update a cache or trigger an external process, you want to make sure these side effects only occur after the database changes are committed. Otherwise, if the transaction is rolled back, your cache or external system could become inconsistent with the database.

Brickworks provides a mechanism for registering async post-commit callbacks. These callbacks are executed only after the session is successfully committed. This is especially useful for cache invalidation or updates that depend on the database state.

**Example:**

```python
from brickworks.core import db

async def update_cache():
    # ... update your cache here ...
    pass

# Register the callback to run after commit
# (inside a session context)
db.add_post_commit_callback(update_cache)
```

This ensures that `update_cache` is only called if the transaction is committed, keeping your cache in sync with the database.
