"""Mocks"""

from django.contrib.auth import get_user_model
from opaque_keys.edx.django.models import CourseKeyField
from opaque_keys.edx.locator import CourseLocator


def get_course_blocks_completion_summary(course_key, user):  # pylint: disable=unused-argument, useless-return
    """get_course_blocks_completion_summary Mock"""
    if not isinstance(user, get_user_model()):
        raise TypeError(f'Expects a user object but got "{user}" of type "{type(user)}"')
    return None


def get_block_structure_manager(course_key):
    """get_block_structure_manager Mock"""
    if not isinstance(course_key, (CourseLocator, CourseKeyField)):
        raise TypeError(f'Expects a CourseKeyField but got "{course_key}" of type "{type(course_key)}"')

    class Dummy:  # pylint: disable=too-few-public-methods
        """dummy class"""
        def get_collected(self):  # pylint: disable=no-self-use
            """get_collected"""
            return []

    return Dummy()


def get_certificates_for_user_by_course_keys(user, course_keys):  # pylint: disable=unused-argument
    """get_certificates_for_user_by_course_keys Mock"""
    if not isinstance(user, get_user_model()):
        raise TypeError(f'Expects a user object but got "{user}" of type "{type(user)}"')
    return {}


def get_user_by_username_or_email(username_or_email):
    """get_user_by_username_or_email Mock"""
    raise get_user_model().DoesNotExist('Dummy function always returns DoesNotExist, mock it you need it')
