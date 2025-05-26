# Brickworks

Brickworks is a modular, "batteries included" backend Framework, based on FastAPI and SQLAlchemy.

Key features:

- Fully async
- Modular
- Policy Based Access Control (PBAC)
- Role Based Access Control (RBAC)
- Build in CLI for db migrations and common tasks


!!! warning
    Brickworks is currently in a **very early development** stage - expect things to change a lot. You probably
    shouldn't use this yet.


## Basic usage

Brickworks requires your project to have a `pyproject.yaml`.

It is recommended to use a dependency management tool like [Poetry](https://python-poetry.org/) or [uv](https://docs.astral.sh/uv/), which will create the `pyproject.yaml` for you and help you manage your projects dependencies.

### Installation

```bash
uv init
uv add brickworks
uv pip install -e .
```

### Create your first brick

Brickworks allows you to build your application out of individual Python modules called bricks.
Each brick should encapsulate a specific functionality, making the codebase easier to understand, maintain and reuse.

To create a brick you can use the command line tool that comes with Brickworks: Mason.

```bash
mason brick create mybrick --namespace app
uv pip install -e
```

This will create the `app` package, containing the `mybrick` module and register your new brick in the `pyproject.toml`.

### Add your first route

Brickworks is based on FastAPI, so routes are working the same way they would in FastAPI. Add routes to the `app.mybrick.routes` module...

```python title="app/mybrick/routers/__init__.py"
from fastapi import APIRouter

r = APIRouter(prefix="/myroutes")

@r.get("/")
async def hello_world():
    return "Hello World"

```

... and register them in the `brick.json`

```json title="app/mybrick/brick.json"
{
  "routers": ["app.mybrick.routers.r"],
  "middlewares": [],
  "loadme": []
}
```

### Your first Database Model

Brickworks uses the ORM (Object Relational Mapper) from SQLAlchemy. All your models should inherit from the `BaseDBModel` class, which is an SQLAlchemy model class. This base class provides common fields and functionality that are useful for most applications, such as access control, attaching files, creating views and more!


```python title="app/mybrick/models/__init__.py"
from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column
from brickworks.core.models.base_dbmodel import BaseDBModel

class BookModel(BaseDBModel):
    __tablename__ = "mymodule_books"
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    author: Mapped[str] = mapped_column(String(255), nullable=False)
    year_published: Mapped[int] = mapped_column(Integer, nullable=True)

# create a new book
book = await BookModel(
    title="The Hobbit", author="J.R.R. Tolkien", year_published=1937
    ).persist()

# get books by author
books = await BookModel.get_list(author="J.R.R. Tolkien")
```

To run database migrations you can just use Mason:

```
mason db upgrade
```

Which will create migration files using alembic and executes the migration.

### Policy Based Access Control (PBAC)

Policies are classes that define rules for accessing or filtering resources. Policies are only applied if you access the models with the methods `get_one_or_none_with_policies()` or `get_list_with_policies()`.


```python
from brickworks.core.acl.base_policy import BasePolicy, PolicyTypeEnum
from apps.mybrick.models import BookModel

class NoTolkienBooksPolicy(BasePolicy):
    policy_type = PolicyTypeEnum.RESTRICTIVE

    async def filter(self, user_uuid: str | None, obj_class: type[BookModel]):
        # Prevent access to books authored by J.R.R. Tolkien
        return obj_class.author.notilike("J.R.R. Tolkien")


BookModel.__policies__.append(NoTolkienBooksPolicy())
```
