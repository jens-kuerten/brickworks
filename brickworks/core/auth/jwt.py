import logging
from datetime import timedelta

import jwt  # pyjwt
from fastapi import Request
from pydantic import BaseModel

from brickworks.core.exceptions import UnauthorizedException
from brickworks.core.settings import settings
from brickworks.core.utils.timeutils import now_utc

logger = logging.getLogger(__name__)


class JWTPayload(BaseModel):
    sub: str
    scope: list[str]
    iat: int
    exp: int


async def generate_jwt(scope: list[str], user_uuid: str, ttl: timedelta = timedelta(hours=1)) -> str:
    secret = settings.JWT_SECRET
    now = now_utc()
    exp = now + ttl
    payload = {
        "sub": user_uuid,
        "scope": scope,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    return token.decode("utf8")


def validate_jwt(token: str, required_scopes: list[str] | None = None) -> JWTPayload:
    """
    Validates and decodes a JWT. Raises jwt exceptions if invalid or expired.
    If required_scopes is provided, ensures all are present in the token's scope claim.
    Returns the decoded payload as a JWTPayload model.
    """
    secret = settings.JWT_SECRET
    payload = jwt.decode(token, secret, algorithms=["HS256"])
    jwt_payload = JWTPayload.model_validate(payload)
    if required_scopes:
        missing = [scope for scope in required_scopes if scope not in jwt_payload.scope]
        if missing:
            logger.error("Missing required scopes: %s", ",".join(missing))
            raise UnauthorizedException
    return jwt_payload


def get_jwt_payload(
    request: Request,
    required_scopes: list[str] | None = None,
) -> JWTPayload:
    """
    FastAPI dependency to extract and validate JWT from the Authorization header.
    Raises HTTPException if missing or invalid.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise UnauthorizedException("Missing token")
    token = auth_header.removeprefix("Bearer ").strip()
    try:
        return validate_jwt(token, required_scopes)
    except Exception as e:
        logger.error("Token auth failed", exc_info=e)
        raise UnauthorizedException("Token validation failed") from e
