"""edx-platform classes mocks for testing purposes."""
from datetime import datetime
from unittest.mock import Mock

from pytz import utc


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


class DiscussionsConfiguration:  # pylint: disable=too-few-public-methods
    """Mock"""
    def __init__(self, provider_type):
        """Mock"""
        self.provider_type = provider_type

    @classmethod
    def get(cls, context_key):  # pylint: disable=unused-argument
        """Mock"""
        return cls(provider_type='fake_openedx_provider')


class CourseFields:  # pylint: disable=too-few-public-methods
    """Mock"""
    start = Mock(default=datetime(2030, 1, 1, tzinfo=utc))
    end = Mock(default=None)
    enrollment_start = Mock(default=datetime.now(tz=utc))
    enrollment_end = Mock(default=None)
    self_paced = Mock(default=None)
    invitation_only = Mock(default=None)


REGISTERED_ACCESS_ROLES = {}


class BearerAuthentication:  # pylint: disable=too-few-public-methods
    """Mock"""
    def authenticate(self, request):  # pylint: disable=no-self-use
        """Mock"""
        return None
