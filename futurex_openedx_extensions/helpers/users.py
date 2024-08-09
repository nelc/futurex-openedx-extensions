"""Helper functions for user operations."""
from __future__ import annotations

from typing import Any, Dict

from common.djangoapps.student.models import get_user_by_username_or_email
from django.contrib.auth import get_user_model

from futurex_openedx_extensions.helpers import constants as cs


def get_user_from_key(user_key: int | str) -> Dict[str, Any]:
    """
    Get list of users from user keys.

    :param user_key: List of user keys (user IDs, usernames, or emails).
    """
    if not isinstance(user_key, (int, str)):
        raise ValueError(f'Invalid user key type, expected int or str, but got {type(user_key).__name__}')

    if isinstance(user_key, str) and not user_key:
        raise ValueError('User key cannot be an empty string!')

    key_type = 'ID' if isinstance(user_key, int) else 'username/email'
    result = {
        'user': None,
        'key_type': key_type,
        'error_code': None,
        'error_message': None,
    }

    try:
        if isinstance(user_key, int):
            user = get_user_model().objects.get(id=user_key)
        else:
            user = get_user_by_username_or_email(user_key)

        if not user.is_active:
            raise ValueError()

    except get_user_model().DoesNotExist:
        result['error_code'] = cs.FX_ERROR_CODE_USER_NOT_FOUND
        result['error_message'] = f'User with {key_type} ({user_key}) does not exist.'

    except get_user_model().MultipleObjectsReturned:
        result['error_code'] = cs.FX_ERROR_CODE_USER_EMAIL_CONFLICT
        result['error_message'] = f'Multiple users found for key ({user_key}).'

    except ValueError:
        result['error_code'] = cs.FX_ERROR_CODE_USER_IS_NOT_ACTIVE
        result['error_message'] = f'User with {key_type} ({user_key}) is not active.'

    else:
        result['user'] = user
        if key_type != 'ID':
            if user_key == user.username:
                result['key_type'] = 'username'
            else:
                result['key_type'] = 'email'

    return result
