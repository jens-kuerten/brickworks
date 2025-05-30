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

Brickworks provides a powerful mixin, `WithGetRouteMixin`, that can be added to any model or view class to automatically generate RESTful GET endpoints for listing and retrieving objects.

### How it works

Add `WithGetRouteMixin` to your model or view class and define the `__routing_path__` and (optionally) `__routing_get_key__` attributes. The mixin will automatically create:
- A paginated GET endpoint at `__routing_path__` (e.g. `/api/books`) returning a paginated response.
- A GET endpoint at `__routing_path__/{key}` for fetching a single object by its key (e.g. `/api/books/{uuid}`).

**All endpoints are automatically secured by the policies set for the model or view.** This means that any access control or filtering logic you define in your model's or view's `__policies__` will be enforced for all requests to these endpoints.

This works exactly the same for both models and views. For more details on defining models and views, see the [database models](database_models.md) and [view models](view_models.md) documentation.

### Example: Adding routes to a model or view

```python
from brickworks.core.models.base_dbmodel import BaseDBModel
from brickworks.core.models.mixins import WithGetRouteMixin

class BookModel(BaseDBModel, WithGetRouteMixin):
    __routing_path__ = "/books"
    __routing_get_key__ = "uuid"
    # ... define fields ...
```

This will automatically provide:
- `GET /api/books?page=1&page_size=100` (paginated list)
- `GET /api/books/{uuid}` (single object by key)

You can use the same pattern for views by inheriting from `BaseView` instead of `BaseDBModel`.

### Response Schema

Paginated list endpoints return a `PaginatedResponse` object:

```json
{
  "items": [ ... ],
  "total": 123,
  "page": 1,
  "page_size": 100
}
```

### Customization

- You can override the default page size and add additional query parameters by customizing the `_get_all` method in your class.
- The mixin respects all policies and filters defined on your model or view.

---

For more details on how to use routers and the route mixin, see the [database models](database_models.md) and [view models](view_models.md) documentation.
