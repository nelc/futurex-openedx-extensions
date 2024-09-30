"""Tests for the users helper functions."""
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model

from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers.exceptions import FXExceptionCodes
from futurex_openedx_extensions.helpers.users import get_user_by_key, is_system_staff_user


@pytest.mark.parametrize('user_key, expected_error_message', [
    (None, 'Invalid user key type, expected int or str, but got NoneType'),
    ('', 'User key cannot be an empty string!'),
    (1.5, 'Invalid user key type, expected int or str, but got float'),
    ([], 'Invalid user key type, expected int or str, but got list'),
    (
        get_user_model()(username='new_user', email='new_user@example.com'),
        'User object must be saved before calling get_user_by_key!'
    ),
])
def test_get_user_by_key_invalid_key(user_key, expected_error_message):
    """Verify that get_user_by_key raises an error for invalid user key."""
    result = get_user_by_key(user_key)
    assert result['user'] is None
    assert result['key_type'] == cs.USER_KEY_TYPE_NOT_ID
    assert result['error_code'] == FXExceptionCodes.USER_NOT_FOUND.value
    assert result['error_message'] == expected_error_message


def test_get_user_by_key_user_call_get_for_id():
    """Verify that get_user_by_key calls get_user_model().objects.get when user key is an ID."""
    user_id = 1
    with patch('futurex_openedx_extensions.helpers.users.get_user_model') as mock_get_user_model:
        with patch('futurex_openedx_extensions.helpers.users.get_user_by_username_or_email') as mock_get_by_email:
            mock_get_user_model().objects.get.return_value = Mock(is_active=True)
            result = get_user_by_key(user_id)

    assert result['user'].is_active
    assert result['key_type'] == cs.USER_KEY_TYPE_ID
    assert result['error_code'] is None
    assert result['error_message'] is None
    mock_get_user_model().objects.get.assert_called_once_with(id=user_id)
    mock_get_by_email.assert_not_called()


@pytest.mark.parametrize('user_key', [cs.USER_KEY_TYPE_USERNAME, cs.USER_KEY_TYPE_EMAIL])
def test_get_user_by_key_user_call_get_for_username_email(user_key):
    """Verify that get_user_by_key calls get_user_by_username_or_email when user key is not an ID."""
    with patch('futurex_openedx_extensions.helpers.users.get_user_model') as mock_get_user_model:
        with patch('futurex_openedx_extensions.helpers.users.get_user_by_username_or_email') as mock_get_by_email:
            username = user_key if user_key == cs.USER_KEY_TYPE_USERNAME else 'other_value'
            email = user_key if user_key == cs.USER_KEY_TYPE_EMAIL else 'other_value'
            mock_get_by_email.return_value = Mock(is_active=True, username=username, email=email)
            result = get_user_by_key(user_key)

    assert result['user'].is_active
    assert result['key_type'] == user_key
    assert result['error_code'] is None
    assert result['error_message'] is None
    mock_get_by_email.assert_called_once_with(user_key)
    mock_get_user_model().objects.get.assert_not_called()


@pytest.mark.django_db
def test_get_user_by_key_user_not_found_by_id(db):  # pylint: disable=unused-argument
    """Verify that get_user_by_key returns an error when user is not found."""
    user_key = 999
    result = get_user_by_key(user_key)

    assert result['user'] is None
    assert result['key_type'] == cs.USER_KEY_TYPE_ID
    assert result['error_code'] == FXExceptionCodes.USER_NOT_FOUND.value
    assert result['error_message'] == f'User with ID ({user_key}) does not exist!'


@pytest.mark.django_db
@pytest.mark.parametrize('error, error_code, error_message', [
    (
        get_user_model().DoesNotExist,
        FXExceptionCodes.USER_NOT_FOUND.value,
        'User with username/email (username_or_email) does not exist!'
    ),
    (
        get_user_model().MultipleObjectsReturned,
        FXExceptionCodes.USER_EMAIL_CONFLICT.value,
        'Multiple users found for key (username_or_email).'
    ),
])
def test_get_user_by_key_user_not_found_not_id(db, error, error_code, error_message):  # pylint: disable=unused-argument
    """Verify that get_user_by_key returns an error when user is not found or duplicated."""
    user_key = 'username_or_email'
    with patch('futurex_openedx_extensions.helpers.users.get_user_by_username_or_email') as mock_get_by_email:
        mock_get_by_email.side_effect = error
        result = get_user_by_key(user_key)

    assert result['user'] is None
    assert result['key_type'] == cs.USER_KEY_TYPE_NOT_ID
    assert result['error_code'] == error_code
    assert result['error_message'] == error_message


@pytest.mark.django_db
def test_get_user_by_key_user_inactive_user(base_data):  # pylint: disable=unused-argument
    """Verify that get_user_by_key returns an error when user is inactive and fail_if_inactive flag is used."""
    user = get_user_model().objects.get(id=62)
    assert not user.is_active

    result = get_user_by_key(user.id)

    assert result['user'] == user
    assert result['key_type'] == cs.USER_KEY_TYPE_ID
    assert result['error_code'] is None
    assert result['error_message'] is None

    result = get_user_by_key(user.id, fail_if_inactive=True)

    assert result['user'] is None
    assert result['key_type'] == cs.USER_KEY_TYPE_ID
    assert result['error_code'] == FXExceptionCodes.USER_IS_NOT_ACTIVE.value
    assert result['error_message'] == f'User with (ID={user.id}) is not active!'


@pytest.mark.django_db
def test_get_user_by_key_user_by_instance(base_data):  # pylint: disable=unused-argument
    """Verify that get_user_by_key returns a user instance when user is passed as an instance."""
    user = get_user_model().objects.get(username='user1')
    result = get_user_by_key(user)

    assert result['user'] == user
    assert result['key_type'] == cs.USER_KEY_TYPE_ID
    assert result['error_code'] is None
    assert result['error_message'] is None


@pytest.mark.parametrize('is_staff, is_superuser, expected_result', [
    (False, False, False),
    (True, False, True),
    (False, True, True),
    (True, True, True),
])
def test_is_system_staff_user(is_staff, is_superuser, expected_result):
    """Verify that is_system_staff_user returns True for system staff users."""
    user = Mock(is_staff=is_staff, is_superuser=is_superuser, is_active=True)

    assert is_system_staff_user(user) is expected_result

    user.is_active = False
    assert is_system_staff_user(user) is False
    assert is_system_staff_user(user, ignore_active=True) is expected_result
