from typing import Any

from fastapi import HTTPException


class CustomException(HTTPException):
    headers: dict[str, str] | None = None
    msg: str
    type: str = "custom_error"
    loc: list[str] | None = []

    def __init__(self, msg: str | None = None) -> None:
        self.msg = msg or self.msg  # can override the default message
        self.detail: Any = [
            {
                "loc": self.loc,
                "msg": self.msg,
                "type": self.type,
            }
        ]
        super().__init__(status_code=self.status_code, detail=self.detail, headers=self.headers)


class NotFoundException(CustomException):
    type: str = "not_found"
    status_code: int = 404


class UnauthorizedException(CustomException):
    type: str = "unauthorized"
    status_code: int = 401


class ForbiddenException(CustomException):
    type: str = "forbidden"
    status_code: int = 403


class DuplicateException(CustomException):
    status_code: int = 409
    type: str = "duplicate"
    msg: str = "Duplicate entry found"
