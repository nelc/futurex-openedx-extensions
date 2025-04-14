"""edx-platform classes mocks for testing purposes."""


class RoleBase:  # pylint: disable=too-few-public-methods
    """Mock"""
    def __init__(self, role, *args, **kwargs):
        """Mock"""


class CourseRole(RoleBase):  # pylint: disable=too-few-public-methods
    """Mock"""

    def add_users(self, user):  # pylint: disable=no-self-use, unused-argument
        """Mock"""
        return None


class OrgRole(RoleBase):  # pylint: disable=too-few-public-methods
    """Mock"""


class CourseInstructorRole(CourseRole):  # pylint: disable=too-few-public-methods
    """Mock"""


class CourseStaffRole(CourseRole):  # pylint: disable=too-few-public-methods
    """Mock"""


class ModuleStoreEnum:  # pylint: disable=too-few-public-methods
    """Mock"""

    class Type:
        """
        Fake Type
        """
        split = 'split'


class DuplicateCourseError(Exception):
    """Mock"""


REGISTERED_ACCESS_ROLES = {}


class BearerAuthentication:  # pylint: disable=too-few-public-methods
    """Mock"""
    def authenticate(self, request):  # pylint: disable=no-self-use
        """Mock"""
        return None
