# Access control

Access control in Brickworks is managed through a flexible policy system (PBAC) and role-based access control (RBAC). This allows you to define fine-grained permissions for users and resources in your application.


## Execution Context

The `ExecutionContext` is used to provide the current user's identity during a request or operation. It is used as an async context manager:

```python
from brickworks.core.auth.authcontext import ExecutionContext

async with ExecutionContext(user_uuid):
    # perform actions as this user
```

During requests to endpoints the `ExecutionContext` is set automatically by the `ExecutionContestMiddleware`.

You can access the current ExecutionContext like this:

```python
from brickworks.core import execution_context

execution_context.user_uuid
```
 **TODO: add roles to execution_context and remove user_uuid from filter method**

## Policy Based Access Control (PBAC)

Policies are classes that define rules for accessing or filtering resources. Policies are only applied if you access the models with the methods
`get_one_or_none_with_policies()` or `get_list_with_policies()`.

```python
book_list = await BookModel.get_list_with_policies()
book = await BookModel.get_one_or_none_with_policies(uuid="123")
```

There are two main types of policies:

- **Restrictive policies**: Prevent access to resources. These are used to explicitly deny access to resources, even if other policies would allow it. Restrictive policies take precedence and are useful for enforcing security boundaries or exceptions.
- **Permissive policies**: Add access to resources. These are used to allow access to resources. If no permissive policies are provided no resources can be accessed.

Most of the time you will probably use **permissive policies** to give access to resources.

Policies are attached to models via the `__policies__` attribute. You can simply append additional policies to models.

```
BookModel.__policies__.append(MyCustomPolicy())
```

!!! note
    You can add additional policies to models of other bricks. Just make sure that the module where you are adding the policies is loaded on startup, e.g. by adding it to the `loadme` section in the `brick.json`.

!!! tip
    If you want all resources to be accessible by default you can add the
    policies `brickworks.core.acl.policies.AllowPublicAccessPolicy` or `brickworks.core.acl.policies.AllowActiveUserAccessPolicy` to the model.

### Example: Restrictive Policy

```python
from brickworks.core.acl.base_policy import BasePolicy, PolicyTypeEnum
from apps.mybrick.models import BookModel

class NoTolkienBooksPolicy(BasePolicy):
    policy_type = PolicyTypeEnum.RESTRICTIVE

    async def filter(self, obj_class: type[BookModel]):
        # Prevent all access to books authored by J.R.R. Tolkien
        return obj_class.author.notilike("J.R.R. Tolkien")
```

### Example: Permissive Policy

```python
from brickworks.core.acl.base_policy import BasePolicy, PolicyTypeEnum
from apps.mybrick.models import BookModel

class AllowHobbitBookPolicy(BasePolicy):
    policy_type = PolicyTypeEnum.PERMISSIVE

    async def filter(self, obj_class: type[BookModel]):
        # Allow access to the book titled 'The Hobbit'
        return obj_class.title == "The Hobbit"
```

### Example: Change filter dynamically

The filter method is evaluated whenever a resource is about to be querried from the database, meaning you can change the behaviour of the filter dynamically.

```python
from brickworks.core import execution_context
from brickworks.core.models import UserModel
from brickworks.core.acl.base_policy import BasePolicy, PolicyTypeEnum
from apps.mybrick.models import BookModel

class AllowOwnBooksPolicy(BasePolicy):
    policy_type = PolicyTypeEnum.PERMISSIVE

    async def filter(self, obj_class: type[BookModel]):
        # Allow access to the books written by the current user
        user = await UserModel.get_one_or_none(uuid=execution_context.user_uuid)
        if not user:
            return AlwaysFalseWhereClause
        return obj_class.author == user.name
```


## Role-Based Access Control (RBAC)

You can define roles and assign them to users. Access to resources can be given or restricted to certain roles
by using the role policies:

- **RoleAllowPolicy**: Gives access to users with a specific role. (permissive)
- **RoleRequiredPolicy**: Requires a user to have a specific role to access a resource. (restrictive)

Most of the time you will use the **RoleAllowPolicy**, to give specific roles access to a model.

Create and add some roles to users...

```python
from brickworks.core.models import RoleModel, UserModel

role = await RoleModel(role_name="admin").persist()
user = await UserModel(sub="alice", ...).persist()
await user.add_role(role)
```


... and add a role policy to your model.

```python
from brickworks.core.acl.policies import RoleAllowPolicy
from apps.mybrick.models import BookModel

BookModel.__policies__.append(RoleAllowPolicy("admin"))
```
