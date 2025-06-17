"""Tests for the signals module of the helpers app"""
from unittest.mock import patch

import pytest
from common.djangoapps.student.models import CourseAccessRole
from django.core.cache import cache

from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers.models import ConfigAccessControl, TenantAsset, ViewAllowedRoles
from futurex_openedx_extensions.helpers.roles import cache_name_user_course_access_roles


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.signals.add_missing_signup_source_record')
def test_refresh_course_access_role_cache_on_save(
    mock_signup, base_data, cache_testing,
):  # pylint: disable=unused-argument
    """Verify that the cache is deleted when a CourseAccessRole is saved"""
    user_id = 1
    cache_name = cache_name_user_course_access_roles(user_id)
    cache.set(cache_name, 'test')
    dummy = CourseAccessRole.objects.create(user_id=user_id, role='test')
    assert cache.get(cache_name) is None
    mock_signup.assert_not_called()

    cache.set(cache_name, 'test')
    dummy.org = 'test'
    dummy.save()
    assert cache.get(cache_name) is None
    mock_signup.assert_called_once_with(user_id, 'test')


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
    cache.set(cs.CACHE_NAME_ALL_VIEW_ROLES, 'test')
    dummy = ViewAllowedRoles.objects.create(view_name='test', allowed_role='test')
    assert cache.get(cs.CACHE_NAME_ALL_VIEW_ROLES) is None

    cache.set(cs.CACHE_NAME_ALL_VIEW_ROLES, 'test')
    dummy.save()
    assert cache.get(cs.CACHE_NAME_ALL_VIEW_ROLES) is None


@patch('futurex_openedx_extensions.helpers.roles.is_view_exist', return_value=True)
@pytest.mark.django_db
def test_refresh_course_access_role_cache_on_delete(base_data, cache_testing):  # pylint: disable=unused-argument
    """Verify that the cache is deleted when a ViewAllowedRoles record is deleted"""
    ViewAllowedRoles.objects.create(view_name='test', allowed_role='test')
    cache.set(cs.CACHE_NAME_ALL_VIEW_ROLES, 'test')
    ViewAllowedRoles.objects.first().delete()
    assert cache.get(cs.CACHE_NAME_ALL_VIEW_ROLES) is None


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.signals.invalidate_tenant_readable_lms_configs')
def test_refresh_config_access_control_cache_on_save(
    mock_invalidate, base_data, cache_testing,
):  # pylint: disable=unused-argument
    """Verify that the cache is deleted when a ConfigAccessControl record is saved"""
    cache.set(cs.CACHE_NAME_CONFIG_ACCESS_CONTROL, 'test')
    dummy = ConfigAccessControl.objects.create(key_name='k', path='p')
    assert cache.get(cs.CACHE_NAME_CONFIG_ACCESS_CONTROL) is None
    mock_invalidate.assert_called_once_with(tenant_id=0)

    mock_invalidate.reset_mock()
    cache.set(cs.CACHE_NAME_CONFIG_ACCESS_CONTROL, 'test')
    dummy.save()
    assert cache.get(cs.CACHE_NAME_CONFIG_ACCESS_CONTROL) is None
    mock_invalidate.assert_called_once_with(tenant_id=0)


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.signals.invalidate_tenant_readable_lms_configs')
def test_refresh_config_access_control_cache_on_delete(
    mock_invalidate, base_data, cache_testing,
):  # pylint: disable=unused-argument
    """Verify that the cache is deleted when a ConfigAccessControl record is deleted"""
    dummy = ConfigAccessControl.objects.create(key_name='k', path='p')
    cache.set(cs.CACHE_NAME_CONFIG_ACCESS_CONTROL, 'test')
    mock_invalidate.assert_called_once_with(tenant_id=0)

    mock_invalidate.reset_mock()
    dummy.delete()
    assert cache.get(cs.CACHE_NAME_CONFIG_ACCESS_CONTROL) is None
    mock_invalidate.assert_called_once_with(tenant_id=0)


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.signals.invalidate_cache')
def test_refresh_tenant_info_cache_on_save_template_asset(
    mock_invalidate, base_data, cache_testing,
):  # pylint: disable=unused-argument
    """Verify that the tenant info cache is invalidated when a TenantAsset is saved"""
    dummy = TenantAsset.objects.create(
        slug='slug',
        tenant_id=1,
        file='http://example.com/slug.png',
        updated_by_id=1,
    )
    mock_invalidate.assert_called_once()

    mock_invalidate.reset_mock()
    dummy.asset_value = 'updated_value'
    dummy.save()
    mock_invalidate.assert_called_once()


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.signals.invalidate_cache')
def test_refresh_tenant_info_cache_on_delete_template_asset(
    mock_invalidate, base_data, cache_testing,
):  # pylint: disable=unused-argument
    """Verify that the tenant info cache is invalidated when a TenantAsset is deleted"""
    dummy = TenantAsset.objects.create(
        slug='slug',
        tenant_id=1,
        file='http://example.com/slug.png',
        updated_by_id=1,
    )
    mock_invalidate.reset_mock()

    dummy.delete()
    mock_invalidate.assert_called_once()
