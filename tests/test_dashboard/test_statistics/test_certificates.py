"""Tests for certificates statistics."""
import pytest
from lms.djangoapps.certificates.models import GeneratedCertificate

from futurex_openedx_extensions.dashboard.statistics import certificates


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_ids, expected_result', [
    ([1], {'ORG1': 4, 'ORG2': 10}),
    ([2], {'ORG3': 7, 'ORG8': 2}),
    ([3], {}),
    ([4], {}),
    ([5], {}),
    ([6], {}),
    ([7], {'ORG3': 7}),
    ([8], {'ORG8': 2}),
    ([1, 2], {'ORG1': 4, 'ORG2': 10, 'ORG3': 7, 'ORG8': 2}),
    ([2, 7], {'ORG3': 7, 'ORG8': 2}),
    ([7, 8], {'ORG3': 7, 'ORG8': 2}),
])
def test_get_certificates_count(base_data, tenant_ids, expected_result):  # pylint: disable=unused-argument
    """Verify get_certificates_count function."""
    result = certificates.get_certificates_count(tenant_ids)
    assert result == expected_result, \
        f'Wrong certificates result for tenant(s) {tenant_ids}. expected: {expected_result}, got: {result}'


@pytest.mark.django_db
def test_get_certificates_count_not_downloadable(base_data):  # pylint: disable=unused-argument
    """Verify get_certificates_count function with empty tenant_ids."""
    result = certificates.get_certificates_count([1])
    assert result == {'ORG1': 4, 'ORG2': 10}, f'Wrong certificates result. expected: {result}'

    some_status_not_downloadable = 'whatever'
    GeneratedCertificate.objects.filter(
        course_id='course-v1:ORG1+5+5',
        user_id=40,
    ).update(status=some_status_not_downloadable)
    result = certificates.get_certificates_count([1])
    assert result == {'ORG1': 3, 'ORG2': 10}, f'Wrong certificates result. expected: {result}'
