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
from tests.base_test_data import _base_data


@pytest.mark.django_db
def test_get_excluded_tenant_ids(base_data):  # pylint: disable=unused-argument
    """Verify get_excluded_tenant_ids function."""
    result = tenants.get_excluded_tenant_ids()
    assert result == [4, 5, 6]


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
@pytest.mark.parametrize("user_id, expected", [
    (1, [1, 2, 3, 7, 8]),
])
def test_get_accessible_tenant_ids_super_users(base_data, user_id, expected):  # pylint: disable=unused-argument
    """Verify get_accessible_tenant_ids function for super users."""
    user = get_user_model().objects.get(id=user_id)
    assert user.is_superuser, 'only super users allowed in this test'
    result = tenants.get_accessible_tenant_ids(user)
    assert result == expected


@pytest.mark.django_db
@pytest.mark.parametrize("user_id, expected", [
    (2, [1, 2, 3, 7, 8]),
])
def test_get_accessible_tenant_ids_staff(base_data, user_id, expected):  # pylint: disable=unused-argument
    """Verify get_accessible_tenant_ids function for staff users."""
    user = get_user_model().objects.get(id=user_id)
    assert user.is_staff, 'only staff users allowed in this test'
    result = tenants.get_accessible_tenant_ids(user)
    assert result == expected


@pytest.mark.django_db
@pytest.mark.parametrize("user_id, expected", [
    (3, []),
    (4, [1, 2, 7]),
    (9, [1]),
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


@pytest.mark.django_db
def test_get_accessible_tenant_ids_complex(base_data):  # pylint: disable=unused-argument
    """Verify get_accessible_tenant_ids function for complex cases"""
    user = get_user_model().objects.get(id=10)
    user_access_role = 'org_course_creator_group'
    user_access = 'ORG3'

    assert not user.is_staff and not user.is_superuser, 'only users with no staff and no superuser allowed in this test'
    assert _base_data['tenant_config'][2]['lms_configs']['course_org_filter'] == [
        'ORG3', 'ORG8'], 'test data is not as expected'
    assert _base_data['tenant_config'][7]['lms_configs']['course_org_filter'] == 'ORG3', 'test data is not as expected'
    assert _base_data['tenant_config'][8]['lms_configs']['course_org_filter'] == [
        'ORG8'], 'test data is not as expected'

    for role, orgs in _base_data["course_access_roles"].items():
        for org, users in orgs.items():
            if role not in cs.TENANT_LIMITED_ADMIN_ROLES:
                continue
            if role != user_access_role or org != user_access:
                assert user.id not in users, (
                    f'test data is not as expected, user {user.id} should be only in '
                    f'{user_access_role} for {user_access}. Found in {role} for {org}'
                )
            else:
                assert user.id in users, (
                    f'test data is not as expected, user {user.id} was not found in '
                    f'{user_access_role} for {user_access}'
                )
            assert (
                (role not in cs.TENANT_LIMITED_ADMIN_ROLES) or
                (role != user_access_role and user.id not in users) or
                (org != user_access and user.id not in users) or
                (role == user_access_role and org == user_access and user.id in users)
            ), (f'test data is not as expected, user {user.id} should be only in {user_access_role} for {user_access}. '
                f'Found in {role} for {org}' if user.id in users else f'Found in {role} for {org}')

    tenant_8_not_expected = [2, 7]
    result = tenants.get_accessible_tenant_ids(user)
    assert result == tenant_8_not_expected


@pytest.mark.django_db
@pytest.mark.parametrize("user_id, ids_to_check, expected", [
    (1, '1,2,3,7', (True, {})),
    (2, '1,2,3,7', (True, {})),
    (3, '1,2,3,7', (
        False, {
            'details': {'tenant_ids': [1, 2, 3, 7]},
            'reason': 'User does not have access to these tenants'
        }
    )),
    (1, '1,7,9', (
        False, {
            'details': {'tenant_ids': [9]},
            'reason': 'Invalid tenant IDs provided'
        }
    )),
    (1, '1,2,E,7', (
        False, {
            'details': {'error': "invalid literal for int() with base 10: 'E'"},
            'reason': 'Invalid tenant IDs provided. It must be a comma-separated list of integers'
        }
    )),
])
def test_check_tenant_access(base_data, user_id, ids_to_check, expected):  # pylint: disable=unused-argument
    """Verify check_tenant_access function."""
    user = get_user_model().objects.get(id=user_id)
    result = tenants.check_tenant_access(user, ids_to_check)
    assert result == expected


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
    assert cache.get(cs.CACHE_NAME_ALL_COURSE_ORG_FILTER_LIST) == result


@pytest.mark.django_db
@pytest.mark.parametrize("tenant_ids, expected", [
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
@pytest.mark.parametrize("user_id, expected", [
    (1, [1, 2, 3, 7, 8]),
    (2, [1, 2, 3, 7, 8]),
    (3, []),
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
@pytest.mark.parametrize("config_key, info_key, test_value, expected_result", [
    ("LMS_BASE", "lms_root_url", "lms.example.com", "https://lms.example.com"),
    ("LMS_ROOT_URL", "lms_root_url", "https://lms.example.com", "https://lms.example.com"),
    ("SITE_NAME", "lms_root_url", "lms.example.com", "https://lms.example.com"),
    ("PLATFORM_NAME", "platform_name", "Test Platform", "Test Platform"),
    ("platform_name", "platform_name", "Test Platform", "Test Platform"),
    ("logo_image_url", "logo_image_url", "https://img.example.com/dummy.jpg", "https://img.example.com/dummy.jpg"),
])
@patch('futurex_openedx_extensions.helpers.tenants.get_excluded_tenant_ids', return_value=[])
def test_get_all_tenants_info_configs(
    base_data, config_key, info_key, test_value, expected_result
):  # pylint: disable=unused-argument
    """Verify get_all_tenants_info function returning the correct logo_url."""
    tenant_config = TenantConfig.objects.create()
    assert tenant_config.lms_configs.get(config_key) is None

    result = tenants.get_all_tenants_info()
    assert result["info"][tenant_config.id][info_key] == ""

    tenant_config.lms_configs[config_key] = test_value
    tenant_config.save()
    result = tenants.get_all_tenants_info()
    assert result["info"][tenant_config.id][info_key] == expected_result


@pytest.mark.django_db
@pytest.mark.parametrize("config_keys, data_prefix, call_index", [
    (["LMS_ROOT_URL", "LMS_BASE", "SITE_NAME"], "https://", 0),
    (["PLATFORM_NAME", "platform_name"], "", 1),
])
@patch(
    'futurex_openedx_extensions.helpers.tenants.get_excluded_tenant_ids',
    return_value=[1, 2, 3, 4, 5, 6, 7, 8]
)
@patch('futurex_openedx_extensions.helpers.tenants.get_first_not_empty_item')
def test_get_all_tenants_info_config_priorities(
    mock_get_first_not_empty_item, base_data, config_keys, data_prefix, call_index
):  # pylint: disable=unused-argument
    """Verify get_all_tenants_info is respecting the priority of the config keys."""
    assert not tenants.get_all_tenants_info()["tenant_ids"]
    tenant_config = TenantConfig.objects.create()
    for config_key in config_keys:
        tenant_config.lms_configs[config_key] = f"{data_prefix}{config_key}_value"
    tenant_config.save()

    _ = tenants.get_all_tenants_info()
    assert mock_get_first_not_empty_item.call_args_list[call_index][0][0] == [
        f"{data_prefix}{config_key}_value" for config_key in config_keys
    ]


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
@pytest.mark.django_db
def test_get_all_tenants_info_is_being_cached():
    """Verify that get_all_tenants_info is being cached."""
    assert cache.get(cs.CACHE_NAME_ALL_TENANTS_INFO) is None
    result = tenants.get_all_tenants_info()
    assert cache.get(cs.CACHE_NAME_ALL_TENANTS_INFO) == result


@pytest.mark.django_db
@pytest.mark.parametrize("tenant_id, expected", [
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
@pytest.mark.parametrize("org, expected", [
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
@pytest.mark.parametrize("tenant_ids, expected", [
    ([1], ['s1.sample.com']),
    ([2, 3], ['s2.sample.com', 's3.sample.com']),
    ([2, 3, 4], ['s2.sample.com', 's3.sample.com']),
    ([2, 3, 7, 8], ['s2.sample.com', 's3.sample.com', 's7.sample.com', 's8.sample.com']),
])
def test_get_tenants_sites(base_data, tenant_ids, expected):  # pylint: disable=unused-argument
    """Verify get_tenants_sites function."""
    assert expected == tenants.get_tenants_sites(tenant_ids)


@pytest.mark.django_db
@pytest.mark.parametrize("tenant_ids", [
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
@pytest.mark.parametrize("tenant_ids", [
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
@pytest.mark.parametrize("username, tenant_ids, orgs, sites, is_enrolled, is_signup", [
    ('user15', [1], ['ORG1', 'ORG2'], ['s1.sample.com'], True, False),
    ('user50', [7], ['ORG3'], ['s7.sample.com'], False, True),
    ('user4', [1], ['ORG1', 'ORG2'], ['s1.sample.com'], True, True),
])
def test_get_user_id_from_username_tenants(
    base_data, username, tenant_ids, orgs, sites, is_enrolled, is_signup
):  # pylint: disable=unused-argument, too-many-arguments
    """Verify get_user_id_from_username_tenants function for a user enrolled in a course but not in the site signup."""
    username = 'user15'
    tenant_ids = [1]
    assert get_user_model().objects.filter(username=username).exists(), 'test data is not as expected'
    assert TenantConfig.objects.filter(id__in=tenant_ids).count() == len(tenant_ids), 'test data is not as expected'

    assert CourseEnrollment.objects.filter(
        user__username=username,
        course__org__in=['ORG1', 'ORG2'],
    ).exists(), 'test data is not as expected'
    assert not UserSignupSource.objects.filter(
        user__username=username,
        site='s1.sample.com',
    ).exists(), 'test data is not as expected'

    assert tenants.get_user_id_from_username_tenants(username, tenant_ids) == int(username[len("user"):])
