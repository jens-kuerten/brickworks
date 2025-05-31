# Routing

Brickworks is based on FastAPI, so you can define routes just as you would in any FastAPI project. Bricks can register their own routers, and you can organize your API by splitting routes into different modules and bricks.

## Registering Routes

To add routes, define them in your brick's routers module and register them in the `brick.json` file:

```python title="app/mybrick/routers/__init__.py"
from fastapi import APIRouter

r = APIRouter(prefix="/myroutes")

@r.get("/")
async def hello_world():
    return "Hello World"
```

```json title="app/mybrick/brick.json"
{
  "routers": ["app.mybrick.routers.r"],
  "middlewares": [],
  "loadme": []
}
```

## Automatic Routes for models and views

Brickworks provides two powerful mixins, `WithListRoute` and `WithGetRoute`, that can be added to any model or view class to automatically generate RESTful GET endpoints for listing and retrieving objects.

### How it works

- Add `WithListRoute` to your model or view class and define the `__routing_path__` attribute to automatically create a paginated GET endpoint at `__routing_path__` (e.g. `/api/books`).
- Add `WithGetRoute` and define both `__routing_path__` and `__routing_get_key__` to create a GET endpoint at `__routing_path__/{key}` for fetching a single object by its key (e.g. `/api/books/{uuid}`).
- You can use either mixin independently, or both together if you want both endpoints.

**All endpoints are automatically secured by the policies set for the model or view.** This means that any access control or filtering logic you define in your model's or view's `__policies__` will be enforced for all requests to these endpoints.

### Example: Adding routes to a model or view

```python
from brickworks.core.models.base_dbmodel import BaseDBModel
from brickworks.core.models.mixins import WithListRoute, WithGetRoute

class BookModel(BaseDBModel, WithListRoute, WithGetRoute):
    __routing_path__ = "/books"
    __routing_get_key__ = "uuid"
    # ... define fields ...
```

This will automatically provide:

- `GET /api/books?page=1&page_size=100` (paginated list)
- `GET /api/books/{uuid}` (single object by key)

You can also use only one of the mixins if you only want a list or a get-by-key endpoint:

```python
class BookListOnlyModel(BaseDBModel, WithListRoute):
    __routing_path__ = "/books"

class BookGetOnlyModel(BaseDBModel, WithGetRoute):
    __routing_path__ = "/books"
    __routing_get_key__ = "uuid"
```

You can use the same pattern for views by inheriting from `BaseView` instead of `BaseDBModel`.

### Response Schema

The list endpoints return a `PaginatedResponse` object:

```json
{
  "items": [ ... ],
  "total": 123,
  "page": 1,
  "page_size": 100
}
```

---

For more details on how to create models and views see the [database models](database_models.md) and [view models](view_models.md) documentation.
