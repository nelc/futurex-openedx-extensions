"""Tests for the signals module of the helpers app"""
from unittest.mock import patch

import pytest
from common.djangoapps.student.models import CourseAccessRole
from django.core.cache import cache

from futurex_openedx_extensions.helpers.constants import CACHE_NAME_ALL_VIEW_ROLES
from futurex_openedx_extensions.helpers.models import ViewAllowedRoles
from futurex_openedx_extensions.helpers.roles import cache_name_user_course_access_roles


@pytest.mark.django_db
def test_refresh_course_access_role_cache_on_save(base_data, cache_testing):  # pylint: disable=unused-argument
    """Verify that the cache is deleted when a CourseAccessRole is saved"""
    user_id = 1
    cache_name = cache_name_user_course_access_roles(user_id)
    cache.set(cache_name, 'test')
    dummy = CourseAccessRole.objects.create(user_id=user_id, role='test')
    assert cache.get(cache_name) is None

    cache.set(cache_name, 'test')
    dummy.save()
    assert cache.get(cache_name) is None


@pytest.mark.django_db
def test_refresh_view_allowed_roles_cache_on_delete(base_data, cache_testing):  # pylint: disable=unused-argument
    """Verify that the cache is deleted when a CourseAccessRole record is deleted"""
    user_id = 3
    cache_name = cache_name_user_course_access_roles(user_id)
    cache.set(cache_name, 'test')

    CourseAccessRole.objects.filter(user_id=user_id + 1).delete()
    assert cache.get(cache_name) == 'test'

    CourseAccessRole.objects.filter(user_id=user_id).delete()
    assert cache.get(cache_name) is None


@patch('futurex_openedx_extensions.helpers.roles.is_view_exist', return_value=True)
@pytest.mark.django_db
def test_refresh_view_allowed_roles_cache_on_save(base_data, cache_testing):  # pylint: disable=unused-argument
    """Verify that the cache is deleted when a ViewAllowedRoles record is saved"""
    cache.set(CACHE_NAME_ALL_VIEW_ROLES, 'test')
    dummy = ViewAllowedRoles.objects.create(view_name='test', allowed_role='test')
    assert cache.get(CACHE_NAME_ALL_VIEW_ROLES) is None

    cache.set(CACHE_NAME_ALL_VIEW_ROLES, 'test')
    dummy.save()
    assert cache.get(CACHE_NAME_ALL_VIEW_ROLES) is None


@patch('futurex_openedx_extensions.helpers.roles.is_view_exist', return_value=True)
@pytest.mark.django_db
def test_refresh_course_access_role_cache_on_delete(base_data, cache_testing):  # pylint: disable=unused-argument
    """Verify that the cache is deleted when a ViewAllowedRoles record is deleted"""
    ViewAllowedRoles.objects.create(view_name='test', allowed_role='test')
    cache.set(CACHE_NAME_ALL_VIEW_ROLES, 'test')
    ViewAllowedRoles.objects.first().delete()
    assert cache.get(CACHE_NAME_ALL_VIEW_ROLES) is None
