from collections.abc import Sequence
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from brickworks.core.utils.timeutils import convert_datetime_to_iso_8601_with_z_suffix


class BaseSchema(BaseModel):
    """
    Base schema for all schemas in the project.
    It converts datetime objects to ISO 8601 format with Z suffix.
    Make sure that your datetime objects are timezone unaware!
    """

    model_config = ConfigDict(
        json_encoders={datetime: convert_datetime_to_iso_8601_with_z_suffix}, from_attributes=True
    )


T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: Sequence[T] = Field(..., description="List of items on this page.")
    total: int = Field(..., description="Total number of items available.")
    page: int = Field(..., description="Current page number (1-based).")
    page_size: int = Field(..., description="Number of items per page.")
