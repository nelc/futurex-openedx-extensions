"""Tests for tenants helpers."""
from unittest.mock import patch

import pytest
from common.djangoapps.student.models import CourseEnrollment, UserSignupSource
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from eox_tenant.models import TenantConfig

from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers import tenants


@pytest.mark.django_db
def test_get_excluded_tenant_ids(base_data):  # pylint: disable=unused-argument
    """Verify get_excluded_tenant_ids function."""
    result = tenants.get_excluded_tenant_ids()
    assert result == [4, 5, 6]


@pytest.mark.django_db
def test_get_excluded_tenant_ids_dashboard_disabled(base_data):  # pylint: disable=unused-argument
    """Verify get_excluded_tenant_ids function when the dashboard is disabled."""
    TenantConfig.objects.filter(id=1).update(lms_configs={'IS_FX_DASHBOARD_ENABLED': False})
    assert tenants.get_excluded_tenant_ids() == [1, 4, 5, 6]
    tenant2 = TenantConfig.objects.get(id=2)
    tenant2.lms_configs.pop('IS_FX_DASHBOARD_ENABLED')
    tenant2.save()
    assert tenants.get_excluded_tenant_ids() == [1, 2, 4, 5, 6]


@pytest.mark.django_db
def test_get_all_tenants(base_data):  # pylint: disable=unused-argument
    """Verify get_all_tenants function."""
    result = tenants.get_all_tenants()
    assert TenantConfig.objects.count() == 8
    assert result.count() == 5
    assert result.exclude(id__in=[4, 5, 6]).count() == result.count()
    assert result.exclude(id__in=[4, 5, 6]).count() == TenantConfig.objects.exclude(id__in=[4, 5, 6]).count()


@pytest.mark.django_db
def test_get_all_tenant_ids(base_data):  # pylint: disable=unused-argument
    """Verify get_all_tenant_ids function."""
    result = tenants.get_all_tenant_ids()
    assert result == [1, 2, 3, 7, 8]


@pytest.mark.django_db
def test_get_accessible_tenant_ids_none(base_data):  # pylint: disable=unused-argument
    """Verify that get_accessible_tenant_ids returns an empty list when user is None."""
    result = tenants.get_accessible_tenant_ids(None)
    assert result == []


@pytest.mark.django_db
@pytest.mark.parametrize('user_id, expected', [
    (1, [1, 2, 3, 7, 8]),
])
def test_get_accessible_tenant_ids_super_users(base_data, user_id, expected):  # pylint: disable=unused-argument
    """Verify get_accessible_tenant_ids function for super users."""
    user = get_user_model().objects.get(id=user_id)
    assert user.is_superuser, 'only super users allowed in this test'
    result = tenants.get_accessible_tenant_ids(user)
    assert result == expected


@pytest.mark.django_db
@pytest.mark.parametrize('user_id, expected', [
    (2, [1, 2, 3, 7, 8]),
])
def test_get_accessible_tenant_ids_staff(base_data, user_id, expected):  # pylint: disable=unused-argument
    """Verify get_accessible_tenant_ids function for staff users."""
    user = get_user_model().objects.get(id=user_id)
    assert user.is_staff, 'only staff users allowed in this test'
    result = tenants.get_accessible_tenant_ids(user)
    assert result == expected
    result = tenants.get_accessible_tenant_ids(user, roles_filter=[])
    assert result == expected


@pytest.mark.django_db
@pytest.mark.parametrize('user_id, expected', [
    (3, [1]),
    (4, [1, 2, 7]),
    (9, [1, 2, 7]),
    (23, [2, 3, 8]),
])
def test_get_accessible_tenant_ids_no_staff_no_sueperuser(
    base_data, user_id, expected
):  # pylint: disable=unused-argument
    """Verify get_accessible_tenant_ids function for users with no staff and no superuser."""
    user = get_user_model().objects.get(id=user_id)
    assert not user.is_staff and not user.is_superuser, 'only users with no staff and no superuser allowed in this test'
    result = tenants.get_accessible_tenant_ids(user)
    assert result == expected
    result = tenants.get_accessible_tenant_ids(user, roles_filter=[])
    assert not result and isinstance(result, list)


@pytest.mark.django_db
def test_get_all_course_org_filter_list(base_data):  # pylint: disable=unused-argument
    """Verify get_all_course_org_filter_list function."""
    result = tenants.get_all_course_org_filter_list()
    assert result == {
        1: ['ORG1', 'ORG2'],
        2: ['ORG3', 'ORG8'],
        3: ['ORG4', 'ORG5'],
        7: ['ORG3'],
        8: ['ORG8'],
    }


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
@pytest.mark.django_db
def test_get_all_course_org_filter_list_is_being_cached():
    """Verify that get_all_course_org_filter_list is being cached."""
    assert cache.get(cs.CACHE_NAME_ALL_COURSE_ORG_FILTER_LIST) is None
    result = tenants.get_all_course_org_filter_list()
    assert cache.get(cs.CACHE_NAME_ALL_COURSE_ORG_FILTER_LIST)['data'] == result
    cache.set(cs.CACHE_NAME_ALL_COURSE_ORG_FILTER_LIST, None)


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_ids, expected', [
    ([1, 2, 3, 7], {
        'course_org_filter_list': ['ORG1', 'ORG2', 'ORG3', 'ORG8', 'ORG4', 'ORG5'],
        'duplicates': {
            2: [7],
            7: [2],
        },
        'invalid': [],
    }),
    ([2, 3], {
        'course_org_filter_list': ['ORG3', 'ORG8', 'ORG4', 'ORG5'],
        'duplicates': {},
        'invalid': [],
    }),
    ([2, 3, 4], {
        'course_org_filter_list': ['ORG3', 'ORG8', 'ORG4', 'ORG5'],
        'duplicates': {},
        'invalid': [4],
    }),
    ([2, 3, 7, 8], {
        'course_org_filter_list': ['ORG3', 'ORG8', 'ORG4', 'ORG5'],
        'duplicates': {
            2: [7, 8],
            7: [2],
            8: [2],
        },
        'invalid': [],
    }),
    ([], {
        'course_org_filter_list': [],
        'duplicates': {},
        'invalid': [],
    }),
])
def test_get_course_org_filter_list(base_data, tenant_ids, expected):  # pylint: disable=unused-argument
    """Verify get_course_org_filter_list function."""
    result = tenants.get_course_org_filter_list(tenant_ids)
    assert result == expected


@pytest.mark.django_db
@pytest.mark.parametrize('user_id, expected', [
    (1, [1, 2, 3, 7, 8]),
    (2, [1, 2, 3, 7, 8]),
    (3, [1]),
    (15, []),
])
def test_get_accessible_tenant_ids(base_data, user_id, expected):  # pylint: disable=unused-argument
    """Verify get_accessible_tenant_ids function."""
    user = get_user_model().objects.get(id=user_id)
    result = tenants.get_accessible_tenant_ids(user)
    assert result == expected


@pytest.mark.django_db
def test_get_all_tenants_info(base_data):  # pylint: disable=unused-argument
    """Verify get_all_tenants_info function."""
    result = tenants.get_all_tenants_info()
    assert result['tenant_ids'] == [1, 2, 3, 7, 8]
    assert result['sites'] == {
        1: 's1.sample.com',
        2: 's2.sample.com',
        3: 's3.sample.com',
        7: 's7.sample.com',
        8: 's8.sample.com',
    }


@pytest.mark.django_db
@pytest.mark.parametrize('config_key, info_key, test_value, expected_result', [
    ('LMS_BASE', 'lms_root_url', 'lms.example.com', 'https://lms.example.com'),
    ('LMS_ROOT_URL', 'lms_root_url', 'https://lms.example.com', 'https://lms.example.com'),
    ('SITE_NAME', 'lms_root_url', 'lms.example.com', 'https://lms.example.com'),
    ('PLATFORM_NAME', 'platform_name', 'Test Platform', 'Test Platform'),
    ('platform_name', 'platform_name', 'Test Platform', 'Test Platform'),
    ('logo_image_url', 'logo_image_url', 'https://img.example.com/dummy.jpg', 'https://img.example.com/dummy.jpg'),
])
@patch('futurex_openedx_extensions.helpers.tenants.get_excluded_tenant_ids', return_value=[])
def test_get_all_tenants_info_configs(
    base_data, config_key, info_key, test_value, expected_result
):  # pylint: disable=unused-argument
    """Verify get_all_tenants_info function returning the correct logo_url."""
    tenant_config = TenantConfig.objects.create()
    assert tenant_config.lms_configs.get(config_key) is None

    result = tenants.get_all_tenants_info()
    assert result['info'][tenant_config.id][info_key] == ''

    tenant_config.lms_configs[config_key] = test_value
    tenant_config.save()
    result = tenants.get_all_tenants_info()
    assert result['info'][tenant_config.id][info_key] == expected_result


@pytest.mark.django_db
@pytest.mark.parametrize('config_keys, data_prefix, call_index', [
    (['LMS_ROOT_URL', 'LMS_BASE', 'SITE_NAME'], 'https://', 0),
    (['PLATFORM_NAME', 'platform_name'], '', 1),
])
@patch(
    'futurex_openedx_extensions.helpers.tenants.get_excluded_tenant_ids',
    return_value=[1, 2, 3, 4, 5, 6, 7, 8]
)
@patch('futurex_openedx_extensions.helpers.tenants.get_first_not_empty_item')
@patch('futurex_openedx_extensions.helpers.tenants.fix_lms_base')
def test_get_all_tenants_info_config_priorities(
    mock_fix_lms_base, mock_get_first_not_empty_item, base_data, config_keys, data_prefix, call_index
):  # pylint: disable=unused-argument, too-many-arguments
    """Verify get_all_tenants_info is respecting the priority of the config keys."""
    assert not tenants.get_all_tenants_info()['tenant_ids']
    tenant_config = TenantConfig.objects.create()
    for config_key in config_keys:
        tenant_config.lms_configs[config_key] = f'{data_prefix}{config_key}_value'
    tenant_config.save()

    mock_fix_lms_base.side_effect = lambda x: x

    _ = tenants.get_all_tenants_info()
    assert mock_get_first_not_empty_item.call_args_list[call_index][0][0] == [
        f'{data_prefix}{config_key}_value' for config_key in config_keys
    ]


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
@pytest.mark.django_db
def test_get_all_tenants_info_is_being_cached():
    """Verify that get_all_tenants_info is being cached."""
    assert cache.get(cs.CACHE_NAME_ALL_TENANTS_INFO) is None
    result = tenants.get_all_tenants_info()
    assert cache.get(cs.CACHE_NAME_ALL_TENANTS_INFO)['data'] == result
    cache.set(cs.CACHE_NAME_ALL_TENANTS_INFO, None)


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_id, expected', [
    (1, 's1.sample.com'),
    (2, 's2.sample.com'),
    (3, 's3.sample.com'),
    (4, None),
    (5, None),
    (6, None),
    (7, 's7.sample.com'),
    (8, 's8.sample.com'),
])
def test_get_tenant_site(base_data, tenant_id, expected):  # pylint: disable=unused-argument
    """Verify get_tenant_site function."""
    assert expected == tenants.get_tenant_site(tenant_id)


@pytest.mark.django_db
@pytest.mark.parametrize('org, expected', [
    ('ORG1', [1]),
    ('ORG2', [1]),
    ('ORG3', [2, 7]),
    ('ORG4', [3]),
    ('ORG5', [3]),
    ('ORG8', [2, 8]),
])
def test_get_tenants_by_org(base_data, org, expected):  # pylint: disable=unused-argument
    """Verify get_tenants_by_org function."""
    assert expected == tenants.get_tenants_by_org(org)


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_ids, expected', [
    ([1], ['s1.sample.com']),
    ([2, 3], ['s2.sample.com', 's3.sample.com']),
    ([2, 3, 4], ['s2.sample.com', 's3.sample.com']),
    ([2, 3, 7, 8], ['s2.sample.com', 's3.sample.com', 's7.sample.com', 's8.sample.com']),
])
def test_get_tenants_sites(base_data, tenant_ids, expected):  # pylint: disable=unused-argument
    """Verify get_tenants_sites function."""
    assert expected == tenants.get_tenants_sites(tenant_ids)


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_ids', [
    [],
    None,
    [99],
])
def test_get_tenants_sites_bad_tenants(base_data, tenant_ids):  # pylint: disable=unused-argument
    """Verify get_tenants_sites function."""
    result = tenants.get_tenants_sites(tenant_ids)
    assert result is not None and len(result) == 0


@pytest.mark.django_db
def test_get_user_id_from_username_tenants_non_existent_username(base_data):  # pylint: disable=unused-argument
    """Verify get_user_id_from_username_tenants function for non-existent username."""
    username = 'non_existent_username'
    tenant_ids = [1, 2, 3, 7, 8]
    assert not get_user_model().objects.filter(username=username).exists(), 'test data is not as expected'
    assert TenantConfig.objects.filter(id__in=tenant_ids).count() == len(tenant_ids), 'test data is not as expected'

    assert tenants.get_user_id_from_username_tenants(username, tenant_ids) == 0


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_ids', [
    [],
    None,
    [99],
])
def test_get_user_id_from_username_tenants_bad_tenant(base_data, tenant_ids):  # pylint: disable=unused-argument
    """Verify get_user_id_from_username_tenants function for non-existent tenant."""
    username = 'user1'
    assert get_user_model().objects.filter(username=username).exists(), 'test data is not as expected'

    assert tenants.get_user_id_from_username_tenants(username, tenant_ids) == 0


@pytest.mark.django_db
@pytest.mark.parametrize('username, tenant_ids, orgs, sites, is_enrolled, is_signup', [
    ('user15', [1], ['ORG1', 'ORG2'], ['s1.sample.com'], True, False),
    ('user50', [7], ['ORG3'], ['s7.sample.com'], False, True),
    ('user4', [1], ['ORG1', 'ORG2'], ['s1.sample.com'], True, True),
])
def test_get_user_id_from_username_tenants(
    base_data, username, tenant_ids, orgs, sites, is_enrolled, is_signup
):  # pylint: disable=unused-argument, too-many-arguments
    """
    Verify get_user_id_from_username_tenants function returns the expected result according
    to course enrollment and signup source.
    """
    assert get_user_model().objects.filter(username=username).exists(), 'test data is not as expected'

    enrollment_qs = CourseEnrollment.objects.filter(
        user__username=username,
        course__org__in=orgs,
    )
    signup_qs = UserSignupSource.objects.filter(
        user__username=username,
        site__in=sites,
    )
    assert enrollment_qs.exists() is is_enrolled, 'test data is not as expected'
    assert signup_qs.exists() is is_signup, 'test data is not as expected'

    assert tenants.get_user_id_from_username_tenants(username, tenant_ids) == int(username[len('user'):])

    enrollment_qs.delete()
    signup_qs.delete()
    assert tenants.get_user_id_from_username_tenants(username, tenant_ids) == 0


@pytest.mark.django_db
def test_get_user_id_from_username_tenants_inactive_enrollment(base_data):  # pylint: disable=unused-argument
    """Verify get_user_id_from_username_tenants function for inactive enrollment."""
    username = 'user15'
    tenant_ids = [1]
    assert get_user_model().objects.filter(username=username).exists(), 'test data is not as expected'
    assert not UserSignupSource.objects.filter(
        user__username=username,
        site__in=['s1.sample.com'],
    ).exists(), 'test data is not as expected'

    assert tenants.get_user_id_from_username_tenants(username, tenant_ids) == int(username[len('user'):])
    CourseEnrollment.objects.filter(
        user__username=username,
        course__org__in=['ORG1', 'ORG2'],
    ).update(is_active=False)
    assert tenants.get_user_id_from_username_tenants(username, tenant_ids) == int(username[len('user'):])


@pytest.mark.parametrize('lms_root_scheme, domain_name, expected_result', [
    ('http', 'example.com', 'http://example.com'),
    ('http', 'http://example.com', 'http://example.com'),
    ('http', 'https://example.com', 'https://example.com'),
    ('https', 'example.com', 'https://example.com'),
    ('https', 'http://example.com', 'http://example.com'),
    ('https', 'https://example.com', 'https://example.com'),
])
def test_fix_lms_base_scheme(lms_root_scheme, domain_name, expected_result):
    """Verify that fix_lms_base sets the correct scheme for the result."""
    with override_settings(LMS_ROOT_URL=f'{lms_root_scheme}://lms.example.com'):
        assert expected_result == tenants.fix_lms_base(domain_name)


@pytest.mark.parametrize('lms_root_port, domain_name, expected_result', [
    (None, 'example.com', 'https://example.com'),
    (None, 'example.com:8080', 'https://example.com:8080'),
    (3030, 'example.com', 'https://example.com:3030'),
    (3030, 'example.com:8080', 'https://example.com:8080'),
])
def test_fix_lms_base_port(lms_root_port, domain_name, expected_result):
    """Verify that fix_lms_base sets the correct port for the result."""
    port = f':{lms_root_port}' if lms_root_port else ''
    with override_settings(LMS_ROOT_URL=f'https://lms.example.com{port}'):
        assert expected_result == tenants.fix_lms_base(domain_name)


@pytest.mark.parametrize('domain_name', [
    None, '',
])
def test_fix_lms_base_empty_domain_name(domain_name):
    """Verify that fix_lms_base sets the correct port for the result."""
    assert tenants.fix_lms_base(domain_name) == ''
