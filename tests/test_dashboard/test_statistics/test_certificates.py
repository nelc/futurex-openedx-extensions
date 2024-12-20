"""Tests for certificates statistics."""
import pytest
from django.test import override_settings
from lms.djangoapps.certificates.models import GeneratedCertificate
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.dashboard.statistics import certificates
from tests.fixture_helpers import get_tenants_orgs


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_ids, expected_result', [
    ([1], {'org1': 4, 'org2': 10}),
    ([2], {'org3': 7, 'org8': 2}),
    ([3], {}),
    ([4], {}),
    ([5], {}),
    ([6], {}),
    ([7], {'org3': 7}),
    ([8], {'org8': 2}),
    ([1, 2], {'org1': 4, 'org2': 10, 'org3': 7, 'org8': 2}),
    ([2, 7], {'org3': 7, 'org8': 2}),
    ([7, 8], {'org3': 7, 'org8': 2}),
])
def test_get_certificates_count(
    base_data, fx_permission_info, tenant_ids, expected_result
):  # pylint: disable=unused-argument
    """Verify get_certificates_count function."""
    fx_permission_info['view_allowed_full_access_orgs'] = get_tenants_orgs(tenant_ids)
    fx_permission_info['view_allowed_any_access_orgs'] = get_tenants_orgs(tenant_ids)
    result = certificates.get_certificates_count(fx_permission_info)
    assert result == expected_result, \
        f'Wrong certificates result for tenant(s) {tenant_ids}. expected: {expected_result}, got: {result}'


@pytest.mark.django_db
def test_get_certificates_count_not_downloadable(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify get_certificates_count function with empty tenant_ids."""
    result = certificates.get_certificates_count(fx_permission_info)
    assert result == {'org1': 4, 'org2': 10}, f'Wrong certificates result. expected: {result}'

    some_status_not_downloadable = 'whatever'
    GeneratedCertificate.objects.filter(
        course_id='course-v1:ORG1+5+5',
        user_id=40,
    ).update(status=some_status_not_downloadable)
    result = certificates.get_certificates_count(fx_permission_info)
    assert result == {'org1': 3, 'org2': 10}, f'Wrong certificates result. expected: {result}'


@pytest.mark.django_db
@override_settings(FX_DEFAULT_COURSE_EFFORT=10)
@pytest.mark.parametrize('tenant_ids, expected_result', [
    ([1], 14 * 10),
    ([2], 9 * 10),
    ([3], 0 * 10),
])
def test_get_learning_hours_count_for_default_course_effort(
    base_data, fx_permission_info, tenant_ids, expected_result
):  # pylint: disable=unused-argument
    """Verify get_learning_hours_count function."""
    fx_permission_info['view_allowed_full_access_orgs'] = get_tenants_orgs(tenant_ids)
    fx_permission_info['view_allowed_any_access_orgs'] = get_tenants_orgs(tenant_ids)
    result = certificates.get_learning_hours_count(fx_permission_info)
    assert result == expected_result, \
        f'Wrong learning hours count for tenant(s) {tenant_ids}. expected: {expected_result}, got: {result}'


@pytest.mark.django_db
@override_settings(FX_DEFAULT_COURSE_EFFORT=10)
@pytest.mark.parametrize('effort, expected_result, usecase', [
    # 2 is the certificate_count in tenant_id 8
    ('20:30', 20.5 * 2, 'Valid, proper HH:MM format with 2-digit minutes'),
    ('20:05', 20.1 * 2, 'Valid, minutes as a single digit with leading zero'),
    ('20:5', 20.1 * 2, 'Valid, minutes as a single digit without leading zero'),
    ('5:5', 5.1 * 2, 'Valid, both hours and minutes are single digits'),
    ('30', 30 * 2, 'Valid, only hours provided (no minutes)'),
    ('5:120', 10 * 2, 'Invalid, minutes exceed 60, use default value'),
    ('invalid', 10 * 2, 'Invalid, non-numeric value for hours, use default value'),
    ('20:invalid', 10 * 2, 'Invalid, non-numeric value for minutes, use default value'),
])
def test_get_learning_hours_count_for_different_course_effor_format(
    base_data, fx_permission_info, effort, expected_result, usecase
):  # pylint: disable=unused-argument
    """Verify get_learning_hours_count function for different course format."""
    fx_permission_info['view_allowed_full_access_orgs'] = get_tenants_orgs([8])
    fx_permission_info['view_allowed_any_access_orgs'] = get_tenants_orgs([8])
    CourseOverview.objects.filter(id='course-v1:ORG8+1+1').update(effort=effort)
    result = certificates.get_learning_hours_count(fx_permission_info)
    assert result == expected_result, f'Wrong learning hours count  usecase: {usecase}'
