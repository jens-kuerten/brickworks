from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, String, Table, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from brickworks.core.models.base_dbmodel import UUID_LENGTH, Base, BaseDBModel

if TYPE_CHECKING:
    from brickworks.core.models.user_model import UserModel

user_role_table = Table(
    "user_role_table",
    Base.metadata,
    Column("user_uuid", ForeignKey("core_users.uuid"), index=True),
    Column("role_uuid", ForeignKey("core_roles.uuid")),
)

role_acl_table = Table(
    "role_acl_table",
    Base.metadata,
    Column("role_name", ForeignKey("core_roles.role_name"), index=True),
    Column("object_uuid", String(UUID_LENGTH), index=True),
    Column("object_fqpn", String(255)),
    Column("permission", String(64)),
    UniqueConstraint("role_name", "object_uuid", "permission", name="uq_role_acl_all"),
)


class RoleModel(BaseDBModel):
    __tablename__ = "core_roles"
    role_name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    users: Mapped[list["UserModel"]] = relationship(
        secondary="user_role_table", back_populates="roles", lazy="noload", init=False
    )
