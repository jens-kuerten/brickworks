from sqlalchemy import and_, select

from brickworks.core import execution_context
from brickworks.core.acl.base_policy import BasePolicy, PolicyTypeEnum
from brickworks.core.models import BaseDBModel
from brickworks.core.models.base_view import BaseView
from brickworks.core.models.role_model import role_acl_table
from brickworks.core.utils.sqlalchemy import AlwaysFalseWhereClause, AlwaysTrueWhereClause, TypeWhereClause


class AllowPublicAccessPolicy(BasePolicy):
    """
    Policy that allows public access to all records of the class.
    PERMISSIVE
    """

    policy_type = PolicyTypeEnum.PERMISSIVE

    async def filter(self, obj_class: type["BaseDBModel"] | type["BaseView"]) -> TypeWhereClause:
        # evaluates to True for all records
        return AlwaysTrueWhereClause


class AllowActiveUserAccessPolicy(BasePolicy):
    """
    Policy that allows active users access to all records of the class.
    PERMISSIVE
    """

    policy_type = PolicyTypeEnum.PERMISSIVE

    async def filter(self, obj_class: type["BaseDBModel"] | type["BaseView"]) -> TypeWhereClause:
        from brickworks.core.models.user_model import UserModel, UserStatusEnum

        if execution_context.user_uuid is None:
            return AlwaysFalseWhereClause
        user = await UserModel.get_one_or_none(uuid=execution_context.user_uuid)
        if user and user.status == UserStatusEnum.ACTIVE:
            # if the user is active we allow access to all records
            return AlwaysTrueWhereClause

        # if user does not exist or is not active, we don't give access
        return AlwaysFalseWhereClause


class RoleAllowPolicy(BasePolicy):
    """
    Policy to give roles access to specific objects with specific permissions.
    """

    policy_type = PolicyTypeEnum.PERMISSIVE

    def __init__(self, role_name: str, permission: str) -> None:
        self.role_name = role_name
        self.permission = permission

    async def filter(self, obj_class: type["BaseDBModel"]) -> TypeWhereClause:
        from brickworks.core.models.user_model import UserModel

        if execution_context.user_uuid is None:
            # if no user is provided, we assume public access (which has no roles)
            return AlwaysFalseWhereClause

        # first we need to check if the user has the role
        user = await UserModel.get_one_or_none(uuid=execution_context.user_uuid, _apply_policies=False)
        if not user or not await user.has_role(self.role_name):
            return AlwaysFalseWhereClause

        return (
            select(1)
            .where(
                and_(
                    role_acl_table.c.role_name == self.role_name,
                    role_acl_table.c.object_uuid == obj_class.uuid,
                    role_acl_table.c.permission == self.permission,
                )
            )
            .exists()
        )


class RoleBasedAccessPolicy(BasePolicy):
    """
    Policy that gives a specific role access to all records of the class.
    By default the policy is permissive, meaning that it does not restrict access to records granted by other policies.
    If restrictive is set to True, the policy requires prevents access to all records unless the user has the
    given role.
    """

    policy_type = PolicyTypeEnum.PERMISSIVE

    def __init__(self, role_name: str, restrictive: bool = False) -> None:
        self.role_name = role_name
        if restrictive:
            self.policy_type = PolicyTypeEnum.RESTRICTIVE

    async def filter(self, obj_class: type["BaseDBModel"] | type["BaseView"]) -> TypeWhereClause:
        from brickworks.core.models.user_model import UserModel

        if execution_context.user_uuid is None:
            # if no user is provided, we assume public access (which has no roles)
            return AlwaysFalseWhereClause
        # first we need to check if the user has the role
        user = await UserModel.get_one_or_none(uuid=execution_context.user_uuid, _apply_policies=False)
        if not user or not await user.has_role(self.role_name):
            return AlwaysFalseWhereClause

        return AlwaysTrueWhereClause
