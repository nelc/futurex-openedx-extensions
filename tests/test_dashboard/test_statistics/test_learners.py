"""Tests for learners statistics."""
from unittest.mock import Mock

import pytest

from futurex_openedx_extensions.dashboard.statistics import learners


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_id, expected_result', [
    (1, {'ORG1': 4, 'ORG2': 17}),
    (2, {'ORG3': 13, 'ORG8': 6}),
    (3, {'ORG4': 4}),
    (4, {}),
    (5, {}),
    (6, {}),
    (7, {'ORG3': 13}),
    (8, {'ORG8': 6}),
])
def test_get_learners_count_having_enrollment_per_org(
    base_data, user1_fx_permission_info, tenant_id, expected_result
):  # pylint: disable=unused-argument
    """Test get_learners_count_having_enrollment_per_org function."""
    result = learners.get_learners_count_having_enrollment_per_org(user1_fx_permission_info, tenant_id)
    assert result.count() == len(expected_result), 'Wrong number of organizations returned'

    for result_tenant_id in result:
        assert result_tenant_id['org'] in expected_result, f'Unexpected org: {result_tenant_id["org"]}'
        assert result_tenant_id['learners_count'] == expected_result[result_tenant_id['org']], \
            f'Wrong learners count: {result_tenant_id["learners_count"]}, org: {result_tenant_id["org"]}'


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_id, expected_result', [
    (1, 17),
    (2, 16),
    (3, 4),
    (4, 0),
    (5, 0),
    (6, 0),
    (7, 13),
    (8, 6),
])
def test_get_learners_count_having_enrollment_for_tenant(
    base_data, user1_fx_permission_info, tenant_id, expected_result
):  # pylint: disable=unused-argument
    """Test get_learners_count_having_enrollment_for_tenant function."""
    result = learners.get_learners_count_having_enrollment_for_tenant(user1_fx_permission_info, tenant_id)
    assert result == expected_result, f'Wrong learners count: {result} for tenant: {tenant_id}'


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_id, expected_result', [
    (1, 0),
    (2, 5),
    (3, 2),
    (4, 0),
    (5, 0),
    (6, 0),
    (7, 4),
    (8, 3),
])
def test_get_learners_count_having_no_enrollment(
    base_data, user1_fx_permission_info, tenant_id, expected_result
):  # pylint: disable=unused-argument
    """Test get_learners_count_having_no_enrollment function."""
    result = learners.get_learners_count_having_no_enrollment(user1_fx_permission_info, tenant_id)
    assert result == expected_result, f'Wrong learners count: {result} for tenant: {tenant_id}'


@pytest.mark.django_db
def test_get_learners_count_having_no_enrollment_without_full_access_to_tenant():
    """Test get_learners_count_having_no_enrollment function without full access to tenant."""
    tenant_id = 2
    fx_permission_info = {
        'user': Mock(username='dummy'),
        'is_system_staff_user': True,
        'user_roles': [],
        'permitted_tenant_ids': [tenant_id],
        'view_allowed_roles': [],
        'view_allowed_full_access_orgs': ['ORG3', 'ORG8'],
        'view_allowed_course_access_orgs': [],
    }
    assert learners.get_learners_count_having_no_enrollment(fx_permission_info, tenant_id) > 0
    fx_permission_info.update({
        'is_system_staff_user': False,
        'view_allowed_full_access_orgs': ['ORG3'],
        'view_allowed_course_access_orgs': ['ORG8'],
    })
    assert learners.get_learners_count_having_no_enrollment(fx_permission_info, tenant_id) == 0


@pytest.mark.django_db
def test_get_learners_count(base_data, user1_fx_permission_info):  # pylint: disable=unused-argument
    """Test get_learners_count function."""
    result = learners.get_learners_count(user1_fx_permission_info)
    assert result == {
        1: {'learners_count': 17, 'learners_count_no_enrollment': 0, 'learners_count_per_org': {'ORG1': 4, 'ORG2': 17}},
        2: {'learners_count': 16, 'learners_count_no_enrollment': 5, 'learners_count_per_org': {'ORG3': 13, 'ORG8': 6}},
        3: {'learners_count': 4, 'learners_count_no_enrollment': 2, 'learners_count_per_org': {'ORG4': 4}},
        4: {'learners_count': 0, 'learners_count_no_enrollment': 0, 'learners_count_per_org': {}},
        7: {'learners_count': 13, 'learners_count_no_enrollment': 4, 'learners_count_per_org': {'ORG3': 13}},
        8: {'learners_count': 6, 'learners_count_no_enrollment': 3, 'learners_count_per_org': {'ORG8': 6}}
    }, f'Wrong learners count: {result}'
