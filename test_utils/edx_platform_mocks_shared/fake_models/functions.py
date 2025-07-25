"""Mocks"""

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from opaque_keys.edx.django.models import CourseKeyField
from opaque_keys.edx.locator import CourseLocator
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview


def get_course_blocks_completion_summary(course_key, user):  # pylint: disable=unused-argument
    """get_course_blocks_completion_summary Mock"""
    if not isinstance(user, get_user_model()):
        raise TypeError(f'Expects a user object but got "{user}" of type "{type(user)}"')
    return {}


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


def grading_context_for_course(course):  # pylint: disable=unused-argument
    """grading_context_for_course Mock"""
    return {}


def get_course_by_id(course_key, depth=0):
    """get_course_by_id Mock"""
    if not isinstance(course_key, (CourseLocator, CourseKeyField)):
        raise TypeError(f'Expects a CourseKeyField but got "{course_key}" of type "{type(course_key)}"')
    if depth != 0:
        raise ValueError(f'Mock error: depth argument supports zero value only, got "{depth}"')
    # return a CourseOverview object for testing
    return CourseOverview.objects.get(id=course_key)


def add_users(caller, role, *users):  # pylint: disable=unused-argument
    """add_user Mock"""
    return None


def assign_default_role(course_id, user):  # pylint: disable=unused-argument
    """assign_default_role Mock"""
    return None


def seed_permissions_roles(course_id):  # pylint: disable=unused-argument
    """seed_permissions_roles Mock"""
    return None


def ensure_organization(org):
    """ensure_organization Mock"""
    return {
        'id': org,
        'name': org,
        'short_name': org
    }


def add_organization_course(org_data, course_id):  # pylint: disable=unused-argument
    """add_organization_course, Mock"""
    return None


def render(request, template):  # pylint: disable=unused-argument
    """render Mock"""
    return HttpResponse()


def get_openedx_site_theme_model():
    """get_openedx_site_theme_model Mock"""
    class SiteThemeMock:  # pylint: disable=too-few-public-methods
        """Mock class for SiteTheme"""
        def __init__(self, site_id: int, theme_dir_name: str) -> None:
            """Initialize the mock with site_id and theme_dir_name."""
            self.site_id = site_id
            self.theme_dir_name = theme_dir_name
            self.id = -1  # pylint: disable=invalid-name

    return SiteThemeMock
