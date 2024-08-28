"""Custom exceptions for the FutureX Open edX Extensions app."""
from __future__ import annotations

from enum import Enum


class FXExceptionCodes(Enum):
    """Role types."""
    UNKNOWN_ERROR = 0

    USER_NOT_FOUND = 1001
    USER_IS_NOT_ACTIVE = 1002
    USER_EMAIL_CONFLICT = 1003

    ROLE_DELETE = 2001
    ROLE_CREATE = 2002
    ROLE_USELESS_ENTRY = 2003
    ROLE_UNSUPPORTED = 2004
    ROLE_INVALID_ENTRY = 2005
    ROLE_INACTIVE = 2006

    BAD_HASH_CODE = 3001

    INVALID_INPUT = 4001


class FXCodedException(Exception):
    """Exception with a code."""
    def __init__(self, code: FXExceptionCodes | int, message: str) -> None:
        """Initialize the exception."""
        super().__init__(message)
        if isinstance(code, FXExceptionCodes):
            self.code = code.value
        # check if integer that is part of the FXExceptionCodes enum
        elif isinstance(code, int):
            if code in [e.value for e in FXExceptionCodes]:
                self.code = code
            else:
                self.code = FXExceptionCodes.UNKNOWN_ERROR.value
        else:
            self.code = FXExceptionCodes.UNKNOWN_ERROR.value
