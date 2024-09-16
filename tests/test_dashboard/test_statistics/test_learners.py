"""Tests for learners statistics."""

import pytest

from futurex_openedx_extensions.dashboard.statistics import learners
from futurex_openedx_extensions.helpers.permissions import get_tenant_limited_fx_permission_info


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_id, expected_result_no_staff, expected_result_include_staff', [
    (1, 16, 18),
    (2, 21, 26),
    (3, 6, 6),
    (7, 17, 20),
    (8, 9, 10),
])
def test_get_learners_count(
    base_data, user1_fx_permission_info, tenant_id, expected_result_no_staff, expected_result_include_staff,
):  # pylint: disable=unused-argument
    """Test get_learners_count function."""
    tenant_fx_permission_info = get_tenant_limited_fx_permission_info(user1_fx_permission_info, tenant_id)
    result = learners.get_learners_count(tenant_fx_permission_info)
    assert result == expected_result_no_staff, f'Wrong learners count: {result}'

    result = learners.get_learners_count(tenant_fx_permission_info, include_staff=True)
    assert result == expected_result_include_staff
