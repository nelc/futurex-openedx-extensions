"""Tests for the signals module of the helpers app"""

import logging
from unittest.mock import patch

import pytest
from common.djangoapps.student.models import CourseAccessRole, UserProfile
from django.core.cache import cache

from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers.models import ConfigAccessControl, TenantAsset, ViewAllowedRoles
from futurex_openedx_extensions.helpers.roles import cache_name_user_course_access_roles

tenant_info_test_cases = [
    (1, 2, False, 'Non-template tenant will not trigger cache invalidation'),
    (1, None, False, 'Undefined template tenant will not trigger cache invalidation'),
    (2, 2, True, 'Template tenant will trigger cache invalidation'),
]


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
    mock_invalidate.assert_called_once_with(tenant_ids=[1, 2, 3, 7, 8])

    mock_invalidate.reset_mock()
    cache.set(cs.CACHE_NAME_CONFIG_ACCESS_CONTROL, 'test')
    dummy.save()
    assert cache.get(cs.CACHE_NAME_CONFIG_ACCESS_CONTROL) is None
    mock_invalidate.assert_called_once_with(tenant_ids=[1, 2, 3, 7, 8])


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.signals.invalidate_tenant_readable_lms_configs')
def test_refresh_config_access_control_cache_on_delete(
    mock_invalidate, base_data, cache_testing,
):  # pylint: disable=unused-argument
    """Verify that the cache is deleted when a ConfigAccessControl record is deleted"""
    dummy = ConfigAccessControl.objects.create(key_name='k', path='p')
    cache.set(cs.CACHE_NAME_CONFIG_ACCESS_CONTROL, 'test')
    mock_invalidate.assert_called_once_with(tenant_ids=[1, 2, 3, 7, 8])

    mock_invalidate.reset_mock()
    dummy.delete()
    assert cache.get(cs.CACHE_NAME_CONFIG_ACCESS_CONTROL) is None
    mock_invalidate.assert_called_once_with(tenant_ids=[1, 2, 3, 7, 8])


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_id, template_id, trigger_flag, test_usecase', tenant_info_test_cases)
@patch('futurex_openedx_extensions.helpers.signals.invalidate_cache')
@patch('futurex_openedx_extensions.helpers.signals.get_all_tenants_info')
def test_refresh_tenant_info_cache_on_save_template_asset(
    mock_tenants_info, mock_invalidate, tenant_id, template_id, trigger_flag, test_usecase, base_data, cache_testing,
):  # pylint: disable=unused-argument, too-many-arguments
    """Verify that the tenant info cache is invalidated when a TenantAsset is saved"""
    mock_tenants_info.return_value = {
        'template_tenant': {
            'tenant_id': template_id,
        }
    }
    dummy = TenantAsset.objects.create(
        slug='slug',
        tenant_id=tenant_id,
        file='http://example.com/slug.png',
        updated_by_id=1,
    )
    if trigger_flag:
        mock_invalidate.assert_called_once()
    else:
        mock_invalidate.assert_not_called()

    mock_invalidate.reset_mock()
    dummy.asset_value = 'updated_value'
    dummy.save()
    if trigger_flag:
        mock_invalidate.assert_called_once()
    else:
        mock_invalidate.assert_not_called()


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.signals.invalidate_cache')
@pytest.mark.parametrize('tenant_id, template_id, trigger_flag, test_usecase', tenant_info_test_cases)
@patch('futurex_openedx_extensions.helpers.signals.get_all_tenants_info')
def test_refresh_tenant_info_cache_on_delete_template_asset(
    mock_tenants_info, mock_invalidate, tenant_id, template_id, trigger_flag, test_usecase, base_data, cache_testing,
):  # pylint: disable=unused-argument, too-many-arguments
    """Verify that the tenant info cache is invalidated when a TenantAsset is deleted"""
    mock_tenants_info.return_value = {
        'template_tenant': {
            'tenant_id': template_id,
        }
    }
    dummy = TenantAsset.objects.create(
        slug='slug',
        tenant_id=tenant_id,
        file='http://example.com/slug.png',
        updated_by_id=1,
    )
    mock_invalidate.reset_mock()

    dummy.delete()
    if trigger_flag:
        mock_invalidate.assert_called_once()
    else:
        mock_invalidate.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize(
    'original, expected, expect_warning',
    [
        ('male', 'm', True),
        ('Male', 'm', True),
        ('female', 'f', True),
        ('FEMALE', 'f', True),
        ('m', 'm', False),
        ('f', 'f', False),
        ('', '', False),
        ('M', '', True),
        ('other', '', True),
    ],
)
def test_fix_profile_gender_issues_on_create(original, expected, expect_warning, caplog):
    """Verify that creating a UserProfile normalizes gender and logs when changed."""
    caplog.set_level(logging.WARNING)
    user_id = 10
    profile = UserProfile.objects.create(user_id=user_id, gender=original)
    profile.refresh_from_db()
    assert profile.gender == expected

    if expect_warning:
        assert any(
            (str(original) in rec.getMessage() and str(expected) in rec.getMessage())
            for rec in caplog.records
        )
    else:
        assert not any('UserProfile.gender updated for user' in rec.getMessage() for rec in caplog.records)


@pytest.mark.django_db
def test_fix_profile_gender_issues_on_update(caplog):
    """Verify that updating an existing UserProfile triggers normalization on save."""
    caplog.set_level(logging.WARNING)
    user_id = 11
    profile = UserProfile.objects.create(user_id=user_id, gender='')
    profile.gender = 'Male'
    profile.save()
    profile.refresh_from_db()
    assert profile.gender == 'm'
    assert any('UserProfile.gender updated for user' in rec.getMessage() for rec in caplog.records)
