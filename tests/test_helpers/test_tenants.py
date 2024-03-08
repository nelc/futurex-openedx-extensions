"""Tests for tenants helpers."""

import pytest
from django.contrib.auth import get_user_model
from eox_tenant.models import TenantConfig

from futurex_openedx_extensions.helpers import tenants
from futurex_openedx_extensions.helpers.tenants import TENANT_LIMITED_ADMIN_ROLES
from tests.base_test_data import _base_data


@pytest.mark.django_db
def test_get_excluded_tenant_ids(base_data):
    """Verify get_excluded_tenant_ids function."""
    result = tenants.get_excluded_tenant_ids()
    assert result == [4, 5, 6]


@pytest.mark.django_db
def test_get_all_tenants(base_data):
    """Verify get_all_tenants function."""
    result = tenants.get_all_tenants()
    assert TenantConfig.objects.count() == 8
    assert result.count() == 5
    assert result.exclude(id__in=[4, 5, 6]).count() == result.count()
    assert result.exclude(id__in=[4, 5, 6]).count() == TenantConfig.objects.exclude(id__in=[4, 5, 6]).count()


@pytest.mark.django_db
def test_get_all_tenant_ids(base_data):
    """Verify get_all_tenant_ids function."""
    result = tenants.get_all_tenant_ids()
    assert result == [1, 2, 3, 7, 8]


@pytest.mark.django_db
def test_get_accessible_tenant_ids_none(base_data):
    """Verify that get_accessible_tenant_ids returns an empty list when user is None."""
    result = tenants.get_accessible_tenant_ids(None)
    assert result == []


@pytest.mark.django_db
@pytest.mark.parametrize("user_id, expected", [
    (1, [1, 2, 3, 7, 8]),
])
def test_get_accessible_tenant_ids_super_users(base_data, user_id, expected):
    """Verify get_accessible_tenant_ids function for super users."""
    user = get_user_model().objects.get(id=user_id)
    assert user.is_superuser, 'only super users allowed in this test'
    result = tenants.get_accessible_tenant_ids(user)
    assert result == expected


@pytest.mark.django_db
@pytest.mark.parametrize("user_id, expected", [
    (2, [1, 2, 3, 7, 8]),
])
def test_get_accessible_tenant_ids_staff(base_data, user_id, expected):
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
def test_get_accessible_tenant_ids_no_staff_no_sueperuser(base_data, user_id, expected):
    """Verify get_accessible_tenant_ids function for users with no staff and no superuser."""
    user = get_user_model().objects.get(id=user_id)
    assert not user.is_staff and not user.is_superuser, 'only users with no staff and no superuser allowed in this test'
    result = tenants.get_accessible_tenant_ids(user)
    assert result == expected


@pytest.mark.django_db
def test_get_accessible_tenant_ids_complex(base_data):
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
            if role not in TENANT_LIMITED_ADMIN_ROLES:
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
                (role not in TENANT_LIMITED_ADMIN_ROLES) or
                (role != user_access_role and user.id not in users) or
                (org != user_access and user.id not in users) or
                (role == user_access_role and org == user_access and user.id in users)
            ), (f'test data is not as expected, user {user.id} should be only in {user_access_role} for {user_access}. '
                f'Found in {role} for {org}' if user.id in users else f'Found in {role} for {org}')

    expected_to_not_include_tenant_8 = [2, 7]
    result = tenants.get_accessible_tenant_ids(user)
    assert result == expected_to_not_include_tenant_8


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
def test_check_tenant_access(base_data, user_id, ids_to_check, expected):
    """Verify check_tenant_access function."""
    user = get_user_model().objects.get(id=user_id)
    result = tenants.check_tenant_access(user, ids_to_check)
    assert result == expected


@pytest.mark.django_db
def test_get_all_course_org_filter_list(base_data):
    """Verify get_all_course_org_filter_list function."""
    result = tenants.get_all_course_org_filter_list()
    assert result == {
        1: ['ORG1', 'ORG2'],
        2: ['ORG3', 'ORG8'],
        3: ['ORG4', 'ORG5'],
        7: ['ORG3'],
        8: ['ORG8'],
    }


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
def test_get_course_org_filter_list(base_data, tenant_ids, expected):
    """Verify get_course_org_filter_list function."""
    result = tenants.get_course_org_filter_list(tenant_ids)
    assert result == expected


@pytest.mark.django_db
@pytest.mark.parametrize("user_id, expected", [
    (1, [1, 2, 3, 7, 8]),
    (2, [1, 2, 3, 7, 8]),
    (3, []),
])
def test_get_accessible_tenant_ids(base_data, user_id, expected):
    """Verify get_accessible_tenant_ids function."""
    user = get_user_model().objects.get(id=user_id)
    result = tenants.get_accessible_tenant_ids(user)
    assert result == expected


@pytest.mark.django_db
def test_get_all_tenants_info(base_data):
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
def test_get_tenant_site(base_data, tenant_id, expected):
    """Verify get_tenant_site function."""
    assert expected == tenants.get_tenant_site(tenant_id)
