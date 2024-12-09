"""Test permissions helper classes"""
import json
from unittest.mock import Mock, patch

import pytest
from deepdiff import DeepDiff
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.test import APIRequestFactory

from futurex_openedx_extensions.helpers.permissions import (
    FXBaseAuthenticatedPermission,
    FXHasTenantAllCoursesAccess,
    FXHasTenantCourseAccess,
    IsAnonymousOrSystemStaff,
    IsSystemStaff,
    get_tenant_limited_fx_permission_info,
)
from futurex_openedx_extensions.upgrade.models_switch import CourseAccessRole
from tests.fixture_helpers import get_all_orgs, set_user


@pytest.fixture
def dummy_view():
    """Dummy view fixture"""
    class DummyView:
        """Dummy view class"""
        fx_view_name = 'dummyView'

        def __init__(self):
            self.result_of_method = {
                'dummyView': ['staff', 'admin'],
                'exported_files_data': ['instructor']
            }

        def get_allowed_roles_all_views(self):
            """Adding method to bypass the type check"""

        def get_view_user_roles_mapping(self, user, view_name):  # pylint: disable=unused-argument
            """Get view user roles mapping"""
            return self.result_of_method[view_name]

    return DummyView()


@pytest.fixture
def user_request():
    """Fixture for an authenticated user request"""
    result = APIRequestFactory().generic('GET', '/dummy/')
    set_user(result, 3)
    return result


@pytest.fixture
def permission():
    """Permission fixture"""
    class DummyPermission(FXBaseAuthenticatedPermission):
        """Dummy permission class"""
        def verify_access_roles(self, request, view):
            """Verify access roles"""
            return True
    return DummyPermission()


@pytest.mark.django_db
@pytest.mark.parametrize('user_id', [1, 2, 60])
def test_is_system_staff_ok(base_data, user_id):  # pylint: disable=unused-argument
    """Verify that IsSystemStaff returns True when user is a system staff member."""
    the_permission = IsSystemStaff()
    request = APIRequestFactory().generic('GET', '/dummy/')
    set_user(request, user_id)
    assert the_permission.has_permission(request, None) is True


@pytest.mark.django_db
@pytest.mark.parametrize('user_id', [None, 0])
def test_is_system_staff_not_authenticated(base_data, user_id):  # pylint: disable=unused-argument
    """Verify that NotAuthenticated is raised when user is not authenticated."""
    the_permission = IsSystemStaff()
    request = APIRequestFactory().generic('GET', '/dummy/')
    set_user(request, user_id)
    with pytest.raises(NotAuthenticated):
        the_permission.has_permission(request, None)


@pytest.mark.django_db
@pytest.mark.parametrize('user_id', [3, 4])
def test_is_system_staff_not_staff(base_data, user_id):  # pylint: disable=unused-argument
    """Verify that PermissionDenied is raised when user is not a system staff member."""
    the_permission = IsSystemStaff()
    request = APIRequestFactory().generic('GET', '/dummy/')
    set_user(request, user_id)
    with pytest.raises(PermissionDenied):
        the_permission.has_permission(request, None)


@pytest.mark.django_db
@pytest.mark.parametrize('user_id, expected_result, error_msg', [
    (None, True, 'anonymous users should be allowed!'),
    (0, True, 'anonymous users should be allowed!'),
    (1, True, 'superusers should be allowed!'),
    (2, True, 'system staff should be allowed!'),
    (15, False, 'non-staff users should not be allowed!'),
])
def test_is_anonymous_or_system_staff(
    base_data, user_id, expected_result, error_msg
):  # pylint: disable=unused-argument
    """Verify that IsAnonymousOrSystemStaff returns True when user is anonymous."""
    the_permission = IsAnonymousOrSystemStaff()
    request = APIRequestFactory().generic('GET', '/dummy/')
    set_user(request, user_id)
    assert the_permission.has_permission(request, None) is expected_result, error_msg


def test_fx_base_authenticated_permission_no_direct_use(
    db, dummy_view, user_request
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that FXBaseAuthenticatedPermission raises NotImplementedError when used directly."""
    the_permission = FXBaseAuthenticatedPermission()

    with pytest.raises(NotImplementedError):
        the_permission.has_permission(user_request, dummy_view)


def test_fx_base_authenticated_permission_view_type_check(
    db, user_request, permission
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that FXBaseAuthenticatedPermission raises NotImplementedError when used directly."""
    class BadTypeOfView:  # pylint: disable=too-few-public-methods
        """Bad type of view: get_allowed_roles_all_views is missing from the class"""

    with pytest.raises(TypeError) as exc:
        permission.has_permission(user_request, BadTypeOfView())
    assert str(exc.value) == (
        'View (BadTypeOfView) does not have (get_allowed_roles_all_views) method! Fix this by adding '
        '(FXViewRoleInfoMixin) to the view class definition, or avoid using permission class (DummyPermission)'
    )


def test_fx_base_authenticated_permission_not_authenticated(
    db, dummy_view, permission
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that FXBaseAuthenticatedPermission raises NotAuthenticated when user is not authenticated."""
    request = APIRequestFactory().generic('GET', '/dummy/')
    set_user(request, None)

    with pytest.raises(NotAuthenticated):
        permission.has_permission(request, dummy_view)


@pytest.mark.parametrize('user_id', [1, 2, 60])
def test_fx_base_authenticated_permission_staff_always_allowed(
    db, dummy_view, permission, user_id
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that FXBaseAuthenticatedPermission returns True when user is staff."""
    request = APIRequestFactory().generic('GET', '/dummy/')
    set_user(request, user_id)
    permission.has_permission(request, dummy_view)
    assert request.fx_permission_info == {
        'user': request.user,
        'user_roles': {},
        'is_system_staff_user': True,
        'view_allowed_roles': ['staff', 'admin'],
        'view_allowed_full_access_orgs': get_all_orgs(),
        'view_allowed_course_access_orgs': [],
        'view_allowed_any_access_orgs': get_all_orgs(),
        'view_allowed_tenant_ids_any_access': [1, 2, 3, 7, 8],
        'view_allowed_tenant_ids_full_access': [1, 2, 3, 7, 8],
        'view_allowed_tenant_ids_partial_access': [],
        'download_allowed': True,
    }


@pytest.mark.django_db
@pytest.mark.parametrize('view_allowed_roles, exported_files_data_roles, user_roles, download_allowed, usecase', [
    (['staff'], ['instructor'], ['staff'], False, 'user does not have download access'),
    (['staff'], ['instructor'], ['staff', 'instructor'], True, 'user have download access'),
])
def test_fx_base_authenticated_permission_for_download_allowed(
    base_data, dummy_view, permission, support_user, view_allowed_roles,
    exported_files_data_roles, user_roles, download_allowed, usecase
):  # pylint: disable=unused-argument, redefined-outer-name, too-many-arguments
    """Verify that FXBaseAuthenticatedPermission fills fx_permission_info correctly for global users."""
    request = APIRequestFactory().generic('GET', '/dummy/')
    set_user(request, support_user.id)
    roles_default_data = {
        'orgs_full_access': [],
        'tenant_ids_full_access': [],
        'course_limited_access': [],
        'orgs_of_courses': [],
        'tenant_ids': []
    }
    dummy_view.result_of_method['dummyView'] = view_allowed_roles
    dummy_view.result_of_method['exported_files_data'] = exported_files_data_roles
    with patch('futurex_openedx_extensions.helpers.permissions.get_user_course_access_roles') as mocked_user_roles:
        mocked_user_roles.return_value = {
            'roles': {role: roles_default_data for role in user_roles}
        }
        permission.has_permission(request, dummy_view)
        assert request.fx_permission_info['download_allowed'] == download_allowed, usecase


@pytest.mark.django_db
@pytest.mark.parametrize('view_allowed_roles, allowed_tenant_ids', [
    (['staff', 'no-support-in-the-list'], []),
    (['support'], [1, 2, 3, 7, 8]),
])
def test_fx_base_authenticated_permission_global_role_allow_all_tenants(
    base_data, dummy_view, permission, support_user, view_allowed_roles, allowed_tenant_ids,
):  # pylint: disable=unused-argument, redefined-outer-name, too-many-arguments
    """Verify that FXBaseAuthenticatedPermission fills fx_permission_info correctly for global users."""
    request = APIRequestFactory().generic('GET', '/dummy/')
    set_user(request, support_user.id)
    dummy_view.result_of_method['dummyView'] = view_allowed_roles
    permission.has_permission(request, dummy_view)
    if allowed_tenant_ids:
        orgs = get_all_orgs()
    else:
        orgs = []

    assert not DeepDiff(
        request.fx_permission_info,
        {
            'user': request.user,
            'user_roles': {
                'support': {
                    'orgs_full_access': [],
                    'tenant_ids_full_access': [],
                    'course_limited_access': [],
                    'orgs_of_courses': [],
                    'tenant_ids': []
                }
            },
            'is_system_staff_user': False,
            'view_allowed_roles': view_allowed_roles,
            'view_allowed_full_access_orgs': orgs,
            'view_allowed_course_access_orgs': [],
            'view_allowed_any_access_orgs': orgs,
            'view_allowed_tenant_ids_any_access': allowed_tenant_ids,
            'view_allowed_tenant_ids_full_access': allowed_tenant_ids,
            'view_allowed_tenant_ids_partial_access': [],
            'download_allowed': False  # user has support role while data export view allowed role is instructor.
        },
        ignore_order=True
    )


def test_fx_base_authenticated_permission_selected_tenants(
    db, dummy_view, permission
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that FXBaseAuthenticatedPermission recognizes selected tenants."""
    user_id = 9
    tenant_1_and_2_orgs = ['org1', 'org2', 'org3', 'org8']
    tenant_3_orgs = ['org4', 'org5']
    assert CourseAccessRole.objects.filter(user_id=user_id, org__in=tenant_1_and_2_orgs).exists(), \
        f'Bad test data, user{user_id} should have access to Tenant 1 and 2'
    assert not CourseAccessRole.objects.filter(user_id=user_id, org__in=tenant_3_orgs).exists(), \
        f'Bad test data, user{user_id} should not have access to Tenant 3'

    request = APIRequestFactory().generic('GET', '/dummy/?tenant_ids=1,2')
    set_user(request, user_id)
    permission.has_permission(request, dummy_view)

    request = APIRequestFactory().generic('GET', '/dummy/?tenant_ids=1,2,3')
    set_user(request, user_id)
    with pytest.raises(PermissionDenied) as exc:
        permission.has_permission(request, dummy_view)
    assert str(exc.value) == json.dumps({
        'reason': 'User does not have access to these tenants', 'details': {'tenant_ids': [3]}
    })


def test_fx_has_tenant_all_courses_access_correct_base():
    """Verify that FXHasTenantAllCoursesAccess works as expected."""
    assert issubclass(FXHasTenantAllCoursesAccess, FXBaseAuthenticatedPermission)


@pytest.mark.parametrize('allowed_full_access, allowed_course_access', [
    ({1, 2, 3}, {3, 4}),
    ({1, 2, 3}, {}),
])
def test_fx_has_tenant_all_courses_access_correct_base_success(
    allowed_full_access, allowed_course_access
):
    """Verify that FXHasTenantAllCoursesAccess works as expected in happy path."""
    request = Mock(fx_permission_info={
        'view_allowed_full_access_orgs': set(allowed_full_access),
        'view_allowed_course_access_orgs': set(allowed_course_access),
    })
    assert FXHasTenantAllCoursesAccess().verify_access_roles(request, None) is True


@pytest.mark.parametrize('allowed_full_access, allowed_course_access', [
    ({}, {1, 2, 3}),
    ({}, {1, 2, 3}),
])
def test_fx_has_tenant_all_courses_access_correct_base_fail(
    allowed_full_access, allowed_course_access
):
    """
    Verify that FXHasTenantAllCoursesAccess raises PermissionDenied when user doesn't have full access
    to any organization.
    """
    request = Mock(fx_permission_info={
        'view_allowed_full_access_orgs': set(allowed_full_access),
        'view_allowed_course_access_orgs': set(allowed_course_access),
    })
    with pytest.raises(PermissionDenied) as exc:
        assert FXHasTenantAllCoursesAccess().verify_access_roles(request, None)
    assert str(exc.value) == json.dumps({'reason': 'User does not have full access to any organization'})


def test_fx_has_tenant_course_access_correct_base():
    """Verify that FXHasTenantCourseAccess works as expected."""
    assert issubclass(FXHasTenantCourseAccess, FXBaseAuthenticatedPermission)


@pytest.mark.parametrize('allowed_full_access, allowed_course_access', [
    ({1, 2, 3}, {3, 4}),
    ({1}, {3}),
    ({}, {3, 4}),
    ({1, 2, 3}, {}),
])
def test_fx_has_tenant_course_access_correct_base_success(
    allowed_full_access, allowed_course_access
):
    """Verify that FXHasTenantCourseAccess works as expected in happy path."""
    request = Mock(fx_permission_info={
        'view_allowed_full_access_orgs': set(allowed_full_access),
        'view_allowed_course_access_orgs': set(allowed_course_access),
        'view_allowed_any_access_orgs': set(allowed_full_access) | set(allowed_course_access),
    })
    assert FXHasTenantCourseAccess().verify_access_roles(request, None) is True


def test_fx_has_tenant_course_access_correct_base_fail():
    """Verify that FXHasTenantCourseAccess raises PermissionDenied when user doesn't have access to any organization."""
    request = Mock(fx_permission_info={
        'view_allowed_full_access_orgs': set(),
        'view_allowed_course_access_orgs': set(),
        'view_allowed_any_access_orgs': set(),
    })
    with pytest.raises(PermissionDenied) as exc:
        FXHasTenantCourseAccess().verify_access_roles(request, None)
    assert str(exc.value) == json.dumps({'reason': 'User does not have course access to the tenant'})


def test_get_tenant_limited_fx_permission_info():
    """Verify that get_tenant_limited_fx_permission_info works as expected."""
    fx_permission_info = {
        'user': 'user object, copy as it is',
        'user_roles': ['list', 'of', 'roles', ' - copy as it is'],
        'is_system_staff_user': 'boolean, copy as it is',
        'view_allowed_roles': 'list of roles, copy as it is',
        'view_allowed_full_access_orgs': [
            'intersection of this list and the list of orgs for the given tenant', 'org1', 'org3'
        ],
        'view_allowed_course_access_orgs': [
            'intersection of this list and the list of orgs for the given tenant', 'org2', 'org3', 'org4'
        ],
        'view_allowed_any_access_orgs': [
            'all orgs in the given tenants', 'org1', 'org2', 'org3', 'org3'
        ],
        'view_allowed_tenant_ids_any_access': 'list of tenants, replace with the given tenant_id',
        'view_allowed_tenant_ids_full_access': 'list of tenants with full access',
        'view_allowed_tenant_ids_partial_access': 'list of tenants with partial access',
    }

    with patch('futurex_openedx_extensions.helpers.permissions.get_course_org_filter_list', return_value={
        'course_org_filter_list': ['org1', 'org2']
    }):
        assert not DeepDiff(get_tenant_limited_fx_permission_info(fx_permission_info, 1), {
            'user': fx_permission_info['user'],
            'user_roles': fx_permission_info['user_roles'],
            'is_system_staff_user': fx_permission_info['is_system_staff_user'],
            'view_allowed_roles': fx_permission_info['view_allowed_roles'],
            'view_allowed_full_access_orgs': ['org1'],
            'view_allowed_course_access_orgs': ['org2'],
            'view_allowed_any_access_orgs': ['org1', 'org2'],
            'view_allowed_tenant_ids_any_access': [1],
            'view_allowed_tenant_ids_full_access': [1],
            'view_allowed_tenant_ids_partial_access': [],
        }, ignore_order=True)
