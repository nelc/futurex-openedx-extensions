"""Tests for the certificates helper functions."""
from unittest.mock import Mock, patch

import pytest
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers.certificates import get_certificate_date, get_certificate_url


@pytest.mark.django_db
@pytest.mark.parametrize('certificates_url, date_should_be_returned', [
    (None, False),
    ('https://s1.sample.com/courses/course-v1:ORG1+2+2/certificate/', True),
    ('/course-v1:ORG1+2+2/certificate/', True),
    ('empty', False),
])
@patch('futurex_openedx_extensions.helpers.certificates.get_certificates_for_user_by_course_keys')
def test_learner_courses_details_serializer_get_certificate_date(
    mock_get_certificates, certificates_url, date_should_be_returned, base_data,
):  # pylint: disable=unused-argument
    """Verify that the get_certificate_date returns the correct data."""
    course = CourseOverview.objects.get(id='course-v1:ORG1+2+2')
    mock_get_certificates.return_value = {
        course.id: {
            'download_url': certificates_url,
            'created': 'not None value',
        },
    } if certificates_url != 'empty' else {}

    assert get_certificate_date(44, course.id) == ('not None value' if date_should_be_returned else None)


@pytest.mark.django_db
@pytest.mark.parametrize('certificates_url, expected_url', [
    (None, None),
    (
        'https://s1.sample.com/courses/course-v1:ORG1+2+2/certificate/',
        'https://s1.sample.com/courses/course-v1:ORG1+2+2/certificate/'
    ),
    (
        '/course-v1:ORG1+2+2/certificate/',
        'https://s1.sample.com/course-v1:ORG1+2+2/certificate/'
    ),
    ('empty', None),
])
@patch('futurex_openedx_extensions.helpers.certificates.get_certificates_for_user_by_course_keys')
def test_learner_courses_details_serializer_get_certificate_url(
    mock_get_certificates, certificates_url, expected_url, base_data,
):  # pylint: disable=unused-argument
    """Verify that the get_certificate_url returns the correct data."""
    request = Mock(site=Mock(), scheme='https')
    course = CourseOverview.objects.get(id='course-v1:ORG1+2+2')
    mock_get_certificates.return_value = {
        course.id: {
            'download_url': certificates_url,
        },
    } if certificates_url != 'empty' else {}

    assert get_certificate_url(request, 44, course.id) == expected_url
