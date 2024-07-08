"""Tests for the signals module of the helpers app"""
from unittest.mock import patch

import pytest
from common.djangoapps.student.models import CourseAccessRole
from django.core.cache import cache
from django.test import override_settings

from futurex_openedx_extensions.helpers.constants import CACHE_NAME_ALL_COURSE_ACCESS_ROLES, CACHE_NAME_ALL_VIEW_ROLES
from futurex_openedx_extensions.helpers.models import ViewAllowedRoles


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
@pytest.mark.django_db
def test_refresh_course_access_role_cache_on_save(base_data):  # pylint: disable=unused-argument
    """Verify that the cache is deleted when a CourseAccessRole is saved"""
    cache.set(CACHE_NAME_ALL_COURSE_ACCESS_ROLES, 'test')
    dummy = CourseAccessRole.objects.create(user_id=1, role='test')
    assert cache.get(CACHE_NAME_ALL_COURSE_ACCESS_ROLES) is None

    cache.set(CACHE_NAME_ALL_COURSE_ACCESS_ROLES, 'test')
    dummy.save()
    assert cache.get(CACHE_NAME_ALL_COURSE_ACCESS_ROLES) is None


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
@pytest.mark.django_db
def test_refresh_view_allowed_roles_cache_on_delete(base_data):  # pylint: disable=unused-argument
    """Verify that the cache is deleted when a CourseAccessRole record is deleted"""
    cache.set(CACHE_NAME_ALL_COURSE_ACCESS_ROLES, 'test')
    CourseAccessRole.objects.first().delete()
    assert cache.get(CACHE_NAME_ALL_COURSE_ACCESS_ROLES) is None


@patch('futurex_openedx_extensions.helpers.roles.is_view_exist', return_value=True)
@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
@pytest.mark.django_db
def test_refresh_view_allowed_roles_cache_on_save(base_data):  # pylint: disable=unused-argument
    """Verify that the cache is deleted when a ViewAllowedRoles record is saved"""
    cache.set(CACHE_NAME_ALL_VIEW_ROLES, 'test')
    dummy = ViewAllowedRoles.objects.create(view_name='test', allowed_role='test')
    assert cache.get(CACHE_NAME_ALL_VIEW_ROLES) is None

    cache.set(CACHE_NAME_ALL_VIEW_ROLES, 'test')
    dummy.save()
    assert cache.get(CACHE_NAME_ALL_VIEW_ROLES) is None


@patch('futurex_openedx_extensions.helpers.roles.is_view_exist', return_value=True)
@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
@pytest.mark.django_db
def test_refresh_course_access_role_cache_on_delete(base_data):  # pylint: disable=unused-argument
    """Verify that the cache is deleted when a ViewAllowedRoles record is deleted"""
    ViewAllowedRoles.objects.create(view_name='test', allowed_role='test')
    cache.set(CACHE_NAME_ALL_VIEW_ROLES, 'test')
    ViewAllowedRoles.objects.first().delete()
    assert cache.get(CACHE_NAME_ALL_VIEW_ROLES) is None
