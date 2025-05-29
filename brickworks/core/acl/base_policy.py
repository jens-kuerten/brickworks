import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING

from brickworks.core.utils.sqlalchemy import TypeWhereClause

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from brickworks.core.models.base_dbmodel import BaseDBModel


class PolicyTypeEnum(Enum):
    """
    Enum to distinguish between restrictive and permissive policies.

    - RESTRICTIVE: All restrictive policies must be satisfied (AND logic).
    - PERMISSIVE: At least one permissive policy must be satisfied (OR logic).
    """

    RESTRICTIVE = "restrictive"
    PERMISSIVE = "permissive"


class BasePolicy(ABC):
    """
    Abstract base class for access control policies.

    Policies are used to restrict or permit access to database rows at the query level.
    Each policy must define its type (restrictive or permissive) and implement the __call__ method,
    which returns a SQLAlchemy filter clause to be applied to a query.

    - Restrictive policies are combined with AND: they prevent access to any row
    that doesn't fulfill their condition.
    - Permissive policies are combined with OR: they add access to rows that fulfill their condition.

    The __call__ method receives the user UUID and the model class, and should return a FilterClause
    suitable for use in a WHERE clause.
    """

    policy_type: PolicyTypeEnum

    @abstractmethod
    async def filter(self, obj_class: type["BaseDBModel"]) -> TypeWhereClause:
        """
        Return a SQLAlchemy filter clause for this policy.

        Args:
            obj_class: The SQLAlchemy model class being queried.

        Returns:
            ClauseElement: A SQLAlchemy expression to be used in a WHERE clause.
        """
        raise NotImplementedError("Policy must implement filter method")
