"""Helper functions for user operations."""
from __future__ import annotations

from typing import Any, Dict

from django.contrib.auth import get_user_model

from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.upgrade.models_switch import get_user_by_username_or_email


def is_user_instance(user: Any) -> bool:
    """
    Check if the given object is an instance of the User model.

    :param user: Object to check.
    :type user: Any
    :return: True if the object is an instance of the User model, False otherwise.
    :rtype: bool
    """
    # pylint: disable=import-outside-toplevel, redefined-outer-name, reimported
    from django.contrib.auth import get_user_model
    return isinstance(user, get_user_model())


def get_user_by_key(  # pylint: disable=too-many-branches
    user_key: get_user_model | int | str, fail_if_inactive: bool = False
) -> Dict[str, Any | None]:
    """
    Get list of users from user keys.

    :param user_key: List of user keys (user object, user IDs, usernames, or emails).
    :type user_key: Union[get_user_model, int, str]
    :param fail_if_inactive: If True, raise an error if the user is not active.
    :type fail_if_inactive: bool
    :return: Dictionary containing user information.
    :rtype: Dict[str, Any | None]
    """
    key_type = cs.USER_KEY_TYPE_ID if isinstance(user_key, int) else cs.USER_KEY_TYPE_NOT_ID
    result: Dict[str, Any | None] = {
        'user': None,
        'key_type': key_type,
        'error_code': None,
        'error_message': None,
    }

    try:
        if is_user_instance(user_key):
            user: get_user_model = user_key
            if not user.pk:
                raise ValueError('User object must be saved before calling get_user_by_key!')
            key_type = cs.USER_KEY_TYPE_ID
            result['key_type'] = key_type
            user_key = user.pk

        if not isinstance(user_key, (int, str)):
            raise ValueError(f'Invalid user key type, expected int or str, but got {type(user_key).__name__}')

        if isinstance(user_key, str) and not user_key:
            raise ValueError('User key cannot be an empty string!')

        if isinstance(user_key, int):
            user = get_user_model().objects.get(id=user_key)
        else:
            user = get_user_by_username_or_email(user_key)

        if fail_if_inactive and not user.is_active:
            raise FXCodedException(
                FXExceptionCodes.USER_IS_NOT_ACTIVE,
                f'User with ({key_type}={user_key}) is not active!'
            )

    except ValueError as exc:
        result['error_code'] = FXExceptionCodes.USER_NOT_FOUND.value
        result['error_message'] = str(exc)

    except get_user_model().DoesNotExist:
        result['error_code'] = FXExceptionCodes.USER_NOT_FOUND.value
        result['error_message'] = f'User with {key_type} ({user_key}) does not exist!'

    except get_user_model().MultipleObjectsReturned:
        result['error_code'] = FXExceptionCodes.USER_EMAIL_CONFLICT.value
        result['error_message'] = f'Multiple users found for key ({user_key}).'

    except FXCodedException as exc:
        result['error_code'] = exc.code
        result['error_message'] = str(exc)

    else:
        result['user'] = user
        if key_type != cs.USER_KEY_TYPE_ID:
            result['key_type'] = cs.USER_KEY_TYPE_USERNAME if user_key == user.username else cs.USER_KEY_TYPE_EMAIL

    return result


def is_system_staff_user(user: get_user_model, ignore_active: bool = False) -> bool:
    """
    Check if the given user is a system staff user.

    :param user: User object.
    :type user: get_user_model
    :param ignore_active: If True, ignore the active status of the user.
    :type ignore_active: bool
    :return: True if the user is a system staff user, False otherwise.
    :rtype: bool
    """
    return (user.is_active or ignore_active) and (user.is_staff or user.is_superuser)
