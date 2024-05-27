"""Mocks"""

from django.contrib.auth import get_user_model


def get_course_blocks_completion_summary(course_key, user):  # pylint: disable=unused-argument
    """get_course_blocks_completion_summary Mock"""
    if not isinstance(user, get_user_model()):
        raise Exception(f'Expects a user object but got "{user}" of type "{type(user)}"')
    return None


def get_block_structure_manager(course_key):  # pylint: disable=unused-argument
    """get_block_structure_manager Mock"""
    class Dummy:  # pylint: disable=too-few-public-methods
        """dummy class"""
        def get_collected(self):  # pylint: disable=no-self-use
            """get_collected"""
            return []

    return Dummy()


def get_certificates_for_user_by_course_keys(user, course_keys):  # pylint: disable=unused-argument
    """get_certificates_for_user_by_course_keys Mock"""
    if not isinstance(user, get_user_model()):
        raise Exception(f'Expects a user object but got "{user}" of type "{type(user)}"')
    return {}
