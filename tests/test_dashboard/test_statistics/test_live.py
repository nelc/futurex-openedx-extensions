"""Tests for live statistics."""
from unittest.mock import patch

import pytest

from futurex_openedx_extensions.dashboard.statistics import live
from futurex_openedx_extensions.helpers.permissions import build_fx_permission_info


@patch('futurex_openedx_extensions.dashboard.statistics.live.build_fx_permission_info')
@pytest.mark.django_db
def test_get_live_statistics_valid_tenant_id(
    mocked_build, base_data,
):  # pylint: disable=unused-argument
    """Verify that the live statistics are returned correctly."""
    mocked_build.return_value = build_fx_permission_info(tenant_id=1)

    assert live.get_live_statistics(tenant_id=1) == {
        'learners_count': 16,
        'courses_count': 12,
        'enrollments_count': 26,
        'certificates_count': 11,
        'learning_hours_count': 220,
    }


@patch('futurex_openedx_extensions.dashboard.statistics.live.build_fx_permission_info')
@pytest.mark.django_db
def test_get_live_statistics_invalid_tenant_id(
    mocked_build, base_data,
):  # pylint: disable=unused-argument
    """Verify that the live statistics returns zeros when the tenant id is invalid."""
    mocked_build.return_value = build_fx_permission_info(tenant_id=1)
    mocked_build.return_value['view_allowed_tenant_ids_any_access'] = []
    keys = ['learners_count', 'courses_count', 'enrollments_count', 'certificates_count', 'learning_hours_count']
    result = live.get_live_statistics(tenant_id=1)
    assert len(result) == len(keys)
    for key in keys:
        assert result[key] == 0
