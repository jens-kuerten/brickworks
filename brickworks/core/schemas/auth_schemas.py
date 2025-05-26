from brickworks.core.schemas.base_schema import BaseSchema


class CSRFTokenResponse(BaseSchema):
    """
    CSRF token response schema.
    """

    csrf_token: str
