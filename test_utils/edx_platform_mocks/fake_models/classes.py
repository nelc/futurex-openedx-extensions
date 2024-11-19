"""edx-platform classes mocks for testing purposes."""


class RoleBase:  # pylint: disable=too-few-public-methods
    """Mock"""
    def __init__(self, role, *args, **kwargs):
        """Mock"""


class CourseRole(RoleBase):  # pylint: disable=too-few-public-methods
    """Mock"""


class OrgRole(RoleBase):  # pylint: disable=too-few-public-methods
    """Mock"""


REGISTERED_ACCESS_ROLES = {}
