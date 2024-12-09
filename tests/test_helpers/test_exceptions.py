"""Tests for exceptions module."""
import pytest
from rest_framework import status

from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes, fx_exception_handler


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


@pytest.mark.parametrize(
    'exception, expected_result', [
        (FXCodedException(message='This is an FX coded exception', code=11), {
            'reason': 'This is an FX coded exception',
            'details': {}
        }),
        (Exception('Generic Exception'), None),
        (ValueError('A value error occurred'), None),
    ]
)
def test_fx_exception_handler(exception, expected_result):
    """
    Test fx_exception_handler with different types of exceptions.
    """
    response = fx_exception_handler(exception)

    if expected_result is None:
        assert response is None
    else:
        assert response.data == expected_result
        assert response.status_code == status.HTTP_400_BAD_REQUEST
