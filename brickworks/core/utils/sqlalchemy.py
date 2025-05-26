from typing import Any, cast

from sqlalchemy.sql._typing import (
    _ColumnExpressionArgument,
    _ColumnExpressionOrStrLabelArgument,
)

TypeOrderBy = _ColumnExpressionOrStrLabelArgument[Any] | list[_ColumnExpressionOrStrLabelArgument[Any]]
TypeWhereClause = _ColumnExpressionArgument[bool]

AlwaysTrueWhereClause = cast(TypeWhereClause, 1 == 1)
AlwaysFalseWhereClause = cast(TypeWhereClause, 1 == 2)  # type: ignore[comparison-overlap]
