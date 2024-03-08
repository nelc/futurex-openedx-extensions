"""Tests for learners statistics."""
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
def test_get_learners_count_having_enrollment_per_org(base_data, tenant_id, expected_result):
    """Test get_learners_count_having_enrollment_per_org function."""
    result = learners.get_learners_count_having_enrollment_per_org(tenant_id)
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
def test_get_learners_count_having_enrollment_for_tenant(base_data, tenant_id, expected_result):
    """Test get_learners_count_having_enrollment_for_tenant function."""
    result = learners.get_learners_count_having_enrollment_for_tenant(tenant_id)
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
def test_get_learners_count_having_no_enrollment(base_data, tenant_id, expected_result):
    """Test get_learners_count_having_no_enrollment function."""
    result = learners.get_learners_count_having_no_enrollment(tenant_id)
    assert result == expected_result, f'Wrong learners count: {result} for tenant: {tenant_id}'


@pytest.mark.django_db
def test_get_learners_count(base_data):
    """Test get_learners_count function."""
    result = learners.get_learners_count([1, 2, 4])
    assert result == {
        1: {
            'learners_count': 17,
            'learners_count_no_enrollment': 0,
            'learners_count_per_org': {'ORG1': 4, 'ORG2': 17},
        },
        2: {'learners_count': 16,
            'learners_count_no_enrollment': 5,
            'learners_count_per_org': {'ORG3': 13, 'ORG8': 6},
            },
        4: {
            'learners_count': 0,
            'learners_count_no_enrollment': 0,
            'learners_count_per_org': {},
        },
    }, f'Wrong learners count: {result}'
