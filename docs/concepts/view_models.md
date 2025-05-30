# View Models

Views are essentially "virtual" tables. Instead of having an actual table in the database, they are defined by an SQL query (or SQLAlchemy select statement) that fetches and composes data from other tables. Views are always read-only and do not store data themselves—they always reflect the current state of the underlying tables.

For example, you might want a list of all users and the number of roles they have. Without views, you would need to fetch a list of all UserModels and a list of all RoleModels and then assemble the result in Python, which can be quite slow if you have many users and roles.

Doing the processing directly in the database would be a lot more performant:

```sql
SELECT users.id AS user_id, users.name, COUNT(roles.id) AS role_count
FROM users
LEFT JOIN roles ON roles.user_id = users.id
GROUP BY users.id, users.name;
```

## Create View Models

View models allow you to define the select statement using SQLAlchemy and query the results fully type safe.

Your View classes should inherit the `BaseView` class like this:

```python
from sqlalchemy import func, select
from sqlalchemy.orm import aliased
from brickworks.core.models.base_view import BaseView
from brickworks.core.models.role_model import RoleModel, user_role_table
from brickworks.core.models.user_model import UserModel

user_alias = aliased(UserModel)
user_role_table_alias = aliased(user_role_table)

class RolesPerUserView(BaseView):
    # define the fields of your query result
    # the field names need to match the (labeled) column names returned by the select statement
    user_name: str
    role_count: int

    # define the select statement
    __select__ = (
        select(
            user_alias.name.label("user_name"),
            func.count(user_role_table_alias.c.role_uuid).label("role_count"),
        )
        .select_from(user_alias)
        .outerjoin(user_role_table_alias, user_alias.uuid == user_role_table_alias.c.user_uuid)
        .group_by(user_alias.name)
    )
```

The field names of the view need to match the column names returned by the select statement. You can use labels to make sure the column names match their fields name.

Now you can simply query the `RolesPerUserView` to get each user and their number of roles, without extra processing in Python:

```python
user_counts = await RolesPerUserView.get_list()
for user in user_counts:
    print(user.user_name, user.role_count)
```


!!! warning

    In views, every model or table used in a join should be aliased with `sqlalchemy.orm.aliased` to prevent name conflicts with additional filters that are added dynamically.


## Use View Models as response schema

View models are Pydantic models and thus can be directly used in your response schemas! Note: For endpoints returning a list, use `List[RolesPerUserView]` as the response model.

```python
from typing import List

@r.get("/", response_model=List[RolesPerUserView])
async def get_roles_per_user_list():
    return await RolesPerUserView.get_list()
```

---

!!! note
    View models are read-only and cannot be used to insert or update data. They are intended for querying and presenting data only.

## Pagination

View models support efficient pagination using the `get_paginated_list` method, which returns a specific page of results and the total number of matching records.

### Usage Example

```python
items, total = await RolesPerUserView.get_paginated_list(_per_page=10, _page=1)
print(f"Total users: {total}")
for user in items:
    print(user.user_name, user.role_count)
```

- `_per_page`: Number of items per page (required)
- `_page`: Page number (1-based, required)
- Returns a tuple: `(items, total)` where `items` is a list of view instances and `total` is the total number of matching records (ignoring pagination)

You can also filter and order results as with `get_list`:

```python
items, total = await RolesPerUserView.get_paginated_list(_per_page=5, _page=1, family_name="Smith")
```

!!! note
    Pagination is efficient: the total count is computed in the database using the same filters and policies as the data query.
