"""Tests for certificates statistics."""
import pytest
from lms.djangoapps.certificates.models import GeneratedCertificate

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
