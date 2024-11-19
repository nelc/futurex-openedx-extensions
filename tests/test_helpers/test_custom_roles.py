"""Test for custom roles module."""
from common.djangoapps.student.admin import CourseAccessRoleForm
from common.djangoapps.student.roles import REGISTERED_ACCESS_ROLES, CourseRole, OrgRole, RoleBase

from futurex_openedx_extensions.helpers.custom_roles import (
    FXAPIAccessRoleCourse,
    FXAPIAccessRoleGlobal,
    FXAPIAccessRoleOrg,
    register_custom_access_role,
)


def test_new_roles():
    """Test that the role names are unique."""
    assert FXAPIAccessRoleOrg().ROLE == 'fx_api_access'
    assert FXAPIAccessRoleCourse().ROLE == 'fx_api_access'
    assert FXAPIAccessRoleGlobal().ROLE == 'fx_api_access_global'

    assert issubclass(FXAPIAccessRoleOrg, OrgRole)
    assert issubclass(FXAPIAccessRoleCourse, CourseRole)
    assert issubclass(FXAPIAccessRoleGlobal, RoleBase)


def test_register_custom_access_role_no_role(caplog):
    """Test that the decorator raises an exception if the role attribute is not present."""
    registered = REGISTERED_ACCESS_ROLES.copy()

    result = register_custom_access_role(object)
    assert result == object
    assert 'Role class object does not have a ROLE attribute' in caplog.text
    assert registered == REGISTERED_ACCESS_ROLES


def test_register_custom_access_role_already_registered(caplog):
    """Test that the decorator raises an exception if the role is already registered."""
    registered = REGISTERED_ACCESS_ROLES.copy()

    result = register_custom_access_role(FXAPIAccessRoleOrg)
    assert result == FXAPIAccessRoleOrg
    assert 'Trying to register a custom role fx_api_access that is already registered!' in caplog.text
    assert registered == REGISTERED_ACCESS_ROLES


def test_register_custom_access_role_register_new():
    """Test that the decorator raises an exception if the role is already registered."""
    class DummyRole:  # pylint: disable=too-few-public-methods
        """Dummy custom role"""
        ROLE = 'fake-role'

    expected_registered = REGISTERED_ACCESS_ROLES.copy()
    expected_registered['fake-role'] = DummyRole
    expected_choices = [(role.ROLE, role.ROLE) for role in expected_registered.values()]

    result = register_custom_access_role(DummyRole)
    assert result == DummyRole
    assert expected_registered == REGISTERED_ACCESS_ROLES
    assert CourseAccessRoleForm.COURSE_ACCESS_ROLES == expected_choices
    assert CourseAccessRoleForm.declared_fields['role'].choices == expected_choices
