"""Test permissions helper classes"""
import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.test import APIRequestFactory

from futurex_openedx_extensions.helpers.permissions import HasCourseAccess, HasTenantAccess, IsSystemStaff


def set_user(request, user_id):
    """Set user"""
    if user_id is None:
        request.user = None
    elif user_id == 0:
        request.user = AnonymousUser()
    else:
        request.user = get_user_model().objects.get(id=user_id)


@pytest.mark.django_db
@pytest.mark.parametrize('method, query_params, user_id', [
    ('GET', '?tenant_ids=1,2,3', 1),
    ('GET', '?tenant_ids=1,2,3', 2),
    ('GET', '', 1),
])
def test_has_tenant_access(base_data, method, query_params, user_id):  # pylint: disable=unused-argument
    """Verify that HasTenantAccess returns True when user has access to all tenants."""
    permission = HasTenantAccess()
    request = APIRequestFactory().generic(method, f'/dummy/{query_params}')
    request.user = get_user_model().objects.get(id=user_id)
    assert permission.has_permission(request, None) is True


@pytest.mark.django_db
@pytest.mark.parametrize('method, query_params, user_id, reason, bad_tenant_ids', [
    ('GET', '?tenant_ids=1,2,3', 5, 'denied', [1, 2, 3]),
    ('GET', '?tenant_ids=1,2,3', 6, 'denied', [1, 2, 3]),
    ('GET', '?tenant_ids=1,2,3,4,9', 1, 'invalid', [9, 4]),
])
def test_has_tenant_access_no_access(
    base_data, method, query_params, user_id, reason, bad_tenant_ids
):  # pylint: disable=unused-argument, too-many-arguments
    """Verify that PermissionDenied is raised when user does not have access to one of the tenants."""
    permission = HasTenantAccess()
    request = APIRequestFactory().generic(method, f'/dummy/{query_params}')
    set_user(request, user_id)

    expected_error = {
        'reason': 'User does not have access to these tenants',
        'details': {'tenant_ids': bad_tenant_ids}
    }
    if reason == 'denied':
        expected_error['reason'] = 'User does not have access to these tenants'
    else:
        expected_error['reason'] = 'Invalid tenant IDs provided'
    expected_error = json.dumps(expected_error)

    with pytest.raises(PermissionDenied) as exc_info:
        permission.has_permission(request, None)
    assert str(exc_info.value) == expected_error


@pytest.mark.django_db
@pytest.mark.parametrize('user_id', [0, None])
def test_has_tenant_access_not_authenticated(base_data, user_id):  # pylint: disable=unused-argument
    """Verify that NotAuthenticated is raised when user is not authenticated."""
    permission = HasTenantAccess()
    request = APIRequestFactory().generic('GET', '/dummy/')
    set_user(request, user_id)
    with pytest.raises(NotAuthenticated):
        permission.has_permission(request, None)


@pytest.mark.django_db
@pytest.mark.parametrize('user_id', [1, 2, 60])
def test_is_system_staff_ok(base_data, user_id):  # pylint: disable=unused-argument
    """Verify that IsSystemStaff returns True when user is a system staff member."""
    permission = IsSystemStaff()
    request = APIRequestFactory().generic('GET', '/dummy/')
    set_user(request, user_id)
    assert permission.has_permission(request, None) is True


@pytest.mark.django_db
@pytest.mark.parametrize('user_id', [None, 0])
def test_is_system_staff_not_authenticated(base_data, user_id):  # pylint: disable=unused-argument
    """Verify that NotAuthenticated is raised when user is not authenticated."""
    permission = IsSystemStaff()
    request = APIRequestFactory().generic('GET', '/dummy/')
    set_user(request, user_id)
    with pytest.raises(NotAuthenticated):
        permission.has_permission(request, None)


@pytest.mark.django_db
@pytest.mark.parametrize('user_id', [3, 4])
def test_is_system_staff_not_staff(base_data, user_id):  # pylint: disable=unused-argument
    """Verify that PermissionDenied is raised when user is not a system staff member."""
    permission = IsSystemStaff()
    request = APIRequestFactory().generic('GET', '/dummy/')
    set_user(request, user_id)
    with pytest.raises(PermissionDenied):
        permission.has_permission(request, None)


@pytest.mark.django_db
@pytest.mark.parametrize('user_id', [1, 2, 60, 4])
def test_has_course_access_true(base_data, user_id):  # pylint: disable=unused-argument
    """Verify that HasCourseAccess returns True when user has access to the course."""
    permission = HasCourseAccess()
    request = APIRequestFactory().generic('GET', '/dummy/course-v1:ORG1+1+1/')
    set_user(request, user_id)
    assert permission.has_permission(request, None) is True


@pytest.mark.django_db
@pytest.mark.parametrize('user_id', [15, 21])
def test_has_course_access_false(base_data, user_id):  # pylint: disable=unused-argument
    """Verify that HasCourseAccess raises PermissionDenied when user does not have access to the course."""
    permission = HasCourseAccess()
    request = APIRequestFactory().generic('GET', '/dummy/course-v1:ORG1+1+1/')
    set_user(request, user_id)
    with pytest.raises(PermissionDenied):
        permission.has_permission(request, None)


@pytest.mark.django_db
@pytest.mark.parametrize('user_id', [None, 0])
def test_has_course_access_not_authenticated(base_data, user_id):  # pylint: disable=unused-argument
    """Verify that HasCourseAccess raises NotAuthenticated when user is not authenticated."""
    permission = HasCourseAccess()
    request = APIRequestFactory().generic('GET', '/dummy/course-v1:ORG1+1+1/')
    set_user(request, user_id)
    with pytest.raises(NotAuthenticated):
        permission.has_permission(request, None)


@pytest.mark.django_db
def test_has_course_access_no_course(base_data):  # pylint: disable=unused-argument
    """Verify that HasCourseAccess raises NotAuthenticated when there is no course in the request."""
    permission = HasCourseAccess()
    request = APIRequestFactory().generic('GET', '/dummy/')
    set_user(request, 1)
    with pytest.raises(PermissionDenied):
        permission.has_permission(request, None)


@pytest.mark.django_db
def test_has_course_access_bad_course(base_data):  # pylint: disable=unused-argument
    """Verify that HasCourseAccess raises PermissionDenied when the course dose not exist."""
    permission = HasCourseAccess()
    request = APIRequestFactory().generic('GET', '/dummy/course-v1:ORG9+9+9/')
    set_user(request, 1)
    with pytest.raises(PermissionDenied):
        permission.has_permission(request, None)
