from datetime import datetime

from pydantic import BaseModel, ConfigDict

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
