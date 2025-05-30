# Database Models

A database model is a Python class that defines the structure and behavior of a database table. It acts as an abstraction layer that maps class attributes to table columns, allowing you to interact with your database using Python objects instead of writing raw SQL queries.

## The Base Model

Brickworks uses the ORM (Object Relational Mapper) from SQLAlchemy. All your models should inherit from the `BaseDBModel` class, which is an SQLAlchemy model class. This base class provides common fields and functionality that are useful for most applications, such as access control, attaching files, creating views and more!

```python
from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column
from brickworks.core.models.base_dbmodel import BaseDBModel

class BookModel(BaseDBModel):
    __tablename__ = "mymodule_books"
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    author: Mapped[str] = mapped_column(String(255), nullable=False)
    year_published: Mapped[int] = mapped_column(Integer, nullable=True)
```

The `BaseDBModel` class provides some additional fields:

- `uuid`: A unique identifier for each record (filled automatically).
- `created_at`: The timestamp when the record was created (filled automatically).
- `updated_at`: The timestamp when the record was last updated.

By inheriting from `BaseDBModel`, your models automatically get these fields and can take advantage of built-in methods for querying and persisting data.

For more details on available column types and options, see the [SQLAlchemy documentation](https://docs.sqlalchemy.org/en/20/core/type_basics.html).

## Adding Data

To add data to the database, create an instance of the model class and then call `persist()` on the model class:

```python
book = BookModel(title="The Hobbit", author="J.R.R. Tolkien", year_published=1937)
await book.persist()

# or in one line
book = await BookModel(title="The Hobbit", author="J.R.R. Tolkien", year_published=1937).persist()
```

Note that `persist()` is an async method that needs to be awaited. It will add the model instance to the database session and cause the uuid to be generated. However it will NOT commit the database session! Commiting is done automatically when the database session is closed and no Exception has been raised. (e.g. when a request to an API endpoint finished successfully)

## Querying Data

The base model provides convenient methods for querying the database:

- `get_one_or_none(...)`: Retrieve a single record matching the given criteria, or `None` if not found.
- `get_list(...)`: Retrieve a list of records matching the given criteria.

Example usage:

```python
# Get a single book by title
book = await BookModel.get_one_or_none(title="The Hobbit")

# Get all books by a specific author
books = await BookModel.get_list(author="J.R.R. Tolkien")
```

By default these methods will apply access policies.

You can also pass additional filters, ordering, and pagination options to these methods.

## Pagination

Database models support efficient pagination out of the box. You can use the `get_paginated_list` method to retrieve a specific page of results along with the total number of matching records.

### Usage Example

```python
items, total = await BookModel.get_paginated_list(_per_page=10, _page=2)
print(f"Total books: {total}")
for book in items:
    print(book.title)
```

- `_per_page`: Number of items per page (required)
- `_page`: Page number (1-based, required)
- Returns a tuple: `(items, total)` where `items` is a list of model/view instances and `total` is the total number of matching records (ignoring pagination)

You can also filter and order results as with `get_list`:

```python
items, total = await BookModel.get_paginated_list(_per_page=5, _page=1, author="J.R.R. Tolkien")
```

!!! note
    Pagination is efficient: the total count is computed in the database using the same filters and policies as the data query.

## Relationships

Models can define relationships to other models, such as one-to-many or many-to-many associations. Use SQLAlchemy's `relationship` and `ForeignKey` to set these up.

Example: A book can have many reviews.

```python
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship, Mapped

class ReviewModel(BaseDBModel):
    __tablename__ = "reviews"
    book_id: Mapped[str] = mapped_column(ForeignKey("books.uuid"), nullable=False)
    content: Mapped[str] = mapped_column(String(1000), nullable=False)
    book = relationship("BookModel", back_populates="reviews")

class BookModel(BaseDBModel):
    __tablename__ = "books"
    # ...existing fields...
    reviews: Mapped[list["ReviewModel"]] = relationship("ReviewModel", back_populates="book")
```

Warning! By default relationships are not loaded and trying to access them will result in an exception (MissingGreenlet). This happens because SQLAlchemy will try to load the relationship synchronously. To access relationship use the [awaitable_attrs](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#sqlalchemy.ext.asyncio.AsyncAttrs.awaitable_attrs):

```python
review = await
book = await BookModel.get_one_or_none(title="The Hobbit")
reviews = await book.awaitable_attrs.reviews
```

Alternatively you can tell SQLAlchemy that the relationship should be loaded with the initial query, e.g. by setting a loading strategy like `lazy="joined"`. (see [SQLAlchemy Relationship Loading Techniques](https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html))

You should try to avoid this though, as this can lead to very large SQL statements and can have a significant performance impact. Depending on your use-case it might be better to either load the relationship with awaitable_attrs when you need it, or to use Views to join tables together.

```python
class BookModel(BaseDBModel):
    __tablename__ = "books"

    # load reviews in initial query with a join
    reviews: Mapped[list["ReviewModel"]] = relationship("ReviewModel",lazy="joined", back_populates="book")
```

## Database Migrations

Brickworks uses the built-in `mason` CLI tool to manage database migrations. Migrations allow you to evolve your database schema over time as your models change.

### How It Works

Under the hood, `mason` uses [Alembic](https://alembic.sqlalchemy.org/) to generate and apply migration files. Alembic is a widely used database migration tool for SQLAlchemy. You do not need to interact with Alembic directly—`mason` provides a streamlined interface for all common migration tasks.

!!! note
    Migration files should be treated as part of your application's source code and checked into version control. Avoid generating migrations dynamically in production or deployed environments. This ensures that all environments (development, staging, production) use the same, predictable database schema changes and makes collaboration and rollbacks safer and more reliable.

### Creating and Applying Migrations

- To automatically generate a new migration file based on your current models and apply it to the database, use:
  ```bash
  mason db upgrade
  ```
  This command will create a new migration file in the `migrations/` folder and apply it immediately.

- To apply existing migration files in the `migrations/` folder (without creating new ones), use:
  ```bash
  mason db migrate
  ```

### Downgrading and Squashing Migrations

- To revert (downgrade) the most recent migration and delete its file, use:
  ```bash
  mason db downgrade
  ```
  This is useful if you want to undo recent changes and then generate a new, consolidated migration.

- To squash all migrations of the current git branch into a single migration file, use:
  ```bash
  mason db squash
  ```
  This will downgrade all migrations on the current branch and then perform a single upgrade, resulting in one migration file that represents all changes.

### Model Discovery

For `mason` to detect your models and generate correct migrations, make sure your models are imported in each brick’s `__init__.py` or registered in the `brick.json`. If models are not loaded, they will not be found by mason and migrations may be incomplete.
