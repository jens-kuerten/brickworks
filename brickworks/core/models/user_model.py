from enum import Enum

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from brickworks.core.exceptions import NotFoundException
from brickworks.core.models.base_dbmodel import BaseDBModel
from brickworks.core.models.role_model import RoleModel


class UserStatusEnum(str, Enum):
    """
    Enum for user status.
    """

    ACTIVE = "active"
    INACTIVE = "inactive"
    BANNED = "banned"
    DELETED = "deleted"


class UserModel(BaseDBModel):
    """
    User model representing a user in the system.

    To access the users roles use: await awaitable_attrs.roles
    """

    __tablename__ = "core_users"

    sub: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)  # OpenID Connect subject identifier
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # full name e.g. "John Doe"
    given_name: Mapped[str] = mapped_column(String(255), nullable=False)
    family_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email_verified: Mapped[bool] = mapped_column(nullable=False, default=False)
    phone_number: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    phone_number_verified: Mapped[bool] = mapped_column(nullable=False, default=False)
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    status: Mapped[UserStatusEnum] = mapped_column(String(32), nullable=False, default=UserStatusEnum.ACTIVE)

    roles: Mapped[list["RoleModel"]] = relationship(
        "RoleModel", back_populates="users", secondary="user_role_table", lazy="noload", init=False
    )

    async def add_role(self, role: str | RoleModel) -> None:
        """
        Add a role to the user. Accepts a role name (str) or RoleModel instance.
        Persists the change to the database.
        Raises NotFoundException if the role name does not exist.
        """
        if isinstance(role, str):
            # assume its a role name and fetch it
            role_ = await RoleModel.get_one_or_none(role_name=role)
            if not role_:
                raise NotFoundException(f"Could not find role {role}")
        else:
            role_ = role

        if role_ not in await self.awaitable_attrs.roles:
            self.roles.append(role_)

        await self.persist()

    async def remove_role(self, role: str | RoleModel) -> None:
        """
        Remove a role from the user. Accepts a role name (str) or RoleModel instance.
        Persists the change to the database.
        """
        if isinstance(role, str):
            role_: RoleModel | None = next((r for r in await self.awaitable_attrs.roles if r.role_name == role), None)
            if role_:
                self.roles.remove(role_)
        else:
            if role in await self.awaitable_attrs.roles:
                self.roles.remove(role)
        await self.persist()

    async def has_role(self, role: str | RoleModel) -> bool:
        """
        Check if the user has a given role. Accepts a role name (str) or RoleModel instance.
        Returns True if the user has the role, False otherwise.
        """
        if isinstance(role, str):
            role_ = next((r for r in await self.awaitable_attrs.roles if r.role_name == role), None)
            return role_ is not None
        else:
            return role in await self.awaitable_attrs.roles
