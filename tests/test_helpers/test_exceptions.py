"""Tests for exceptions module."""
import pytest

from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes


@pytest.mark.parametrize('error_code', [FXExceptionCodes.USER_NOT_FOUND, FXExceptionCodes.USER_NOT_FOUND.value])
def test_fx_coded_exception(error_code):
    """Verify that FXCodedException sets the error code and message correctly."""
    error_message = 'Invalid user!'

    exc = FXCodedException(error_code, error_message)

    assert exc.code == FXExceptionCodes.USER_NOT_FOUND.value
    assert str(exc) == error_message


def test_fx_coded_exception_unknown_error():
    """Verify that FXCodedException sets the error code to UNKNOWN_ERROR for an unknown error code."""
    not_in_fx_exception_codes = max(FXExceptionCodes, key=lambda x: x.value).value + 1
    error_message = 'whatever!'

    exc = FXCodedException(not_in_fx_exception_codes, error_message)

    assert exc.code == FXExceptionCodes.UNKNOWN_ERROR.value
    assert str(exc) == error_message


@pytest.mark.parametrize('error_code', ['invalid code', 3.14, None, True, False])
def test_fx_coded_exception_invalid_code(error_code):
    """Verify that FXCodedException sets the error code to UNKNOWN_ERROR for an invalid error code."""
    error_message = 'whatever!'

    exc = FXCodedException(error_code, error_message)

    assert exc.code == FXExceptionCodes.UNKNOWN_ERROR.value
    assert str(exc) == error_message
