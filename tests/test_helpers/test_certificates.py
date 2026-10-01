"""Tests for the certificates helper functions."""
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model
from opaque_keys.edx.keys import CourseKey
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from openedx_filters.learning.filters import CertificateCreationRequested

from futurex_openedx_extensions.helpers.certificates import (
    StopCertificateIssuanceWhenDisabled,
    _has_certificate_template,
    disable_course_certificates,
    enable_course_certificates,
    get_certificate_date,
    get_certificate_url,
)
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.models import CourseCertificateIssuance

COURSE_KEY = CourseKey.from_string('course-v1:ORG1+1+1')


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


@pytest.mark.parametrize('mode_slugs, expected_modes', [
    ([], ['honor']),
    (['audit', 'verified'], ['audit', 'verified']),
])
@patch('futurex_openedx_extensions.helpers.certificates.get_certificate_template')
@patch('futurex_openedx_extensions.helpers.certificates.CourseMode.modes_for_course')
def test_has_certificate_template_modes(mock_modes, mock_get_template, mode_slugs, expected_modes):
    """Verify that the template is checked for every course mode, falling back to honor"""
    mock_modes.return_value = [Mock(slug=slug) for slug in mode_slugs]
    mock_get_template.return_value = None

    assert _has_certificate_template(COURSE_KEY, 'ar') is False
    assert [call.args for call in mock_get_template.call_args_list] == [
        (COURSE_KEY, mode, 'ar') for mode in expected_modes
    ]


@patch('futurex_openedx_extensions.helpers.certificates.get_certificate_template', return_value=Mock())
@patch('futurex_openedx_extensions.helpers.certificates.CourseMode.modes_for_course', return_value=[])
def test_has_certificate_template_found(*_):
    """Verify that a matching template is detected"""
    assert _has_certificate_template(COURSE_KEY, 'ar') is True


def _mock_course(certificates):
    """Return a mock course with the given certificates field."""
    return Mock(certificates=certificates, language='ar', cert_html_view_enabled=False)


@pytest.mark.django_db
@pytest.mark.parametrize('certificates, expected_configurations', [
    (None, None),
    ({}, None),
    ({'certificates': []}, None),
    (
        {'certificates': [{'id': 5, 'name': 'Existing', 'is_active': False}]},
        [{'id': 5, 'name': 'Existing', 'is_active': True}],
    ),
])
@patch('futurex_openedx_extensions.helpers.certificates._has_certificate_template', return_value=True)
@patch('futurex_openedx_extensions.helpers.certificates.modulestore')
def test_enable_course_certificates(mock_modulestore, _, certificates, expected_configurations):
    """Verify that enabling activates (or creates) the configuration, enables the HTML view, and enables issuance"""
    user = get_user_model().objects.get(id=1)
    course = _mock_course(certificates)
    mock_modulestore.return_value.get_course.return_value = course
    CourseCertificateIssuance.set_issuance_enabled(COURSE_KEY, False, user)

    enable_course_certificates(COURSE_KEY, user)

    store = mock_modulestore.return_value
    store.branch_setting.assert_called_once_with('draft-preferred', COURSE_KEY)
    assert [call[0] for call in store.mock_calls] == [
        'branch_setting', 'branch_setting().__enter__', 'get_course', 'update_item', 'branch_setting().__exit__',
    ], 'the course must be read and updated inside the draft branch context'
    configurations = course.certificates['certificates']
    if expected_configurations is None:
        assert len(configurations) == 1
        assert configurations[0]['is_active'] is True
        assert configurations[0]['signatories'] == []
    else:
        assert configurations == expected_configurations
    assert course.cert_html_view_enabled is True
    mock_modulestore.return_value.update_item.assert_called_once_with(course, user.id)
    assert CourseCertificateIssuance.is_issuance_enabled(COURSE_KEY) is True


@pytest.mark.django_db
@pytest.mark.parametrize('course, has_template, expected_code', [
    (None, True, FXExceptionCodes.COURSE_CERTIFICATE_COURSE_NOT_FOUND),
    (_mock_course(None), False, FXExceptionCodes.COURSE_CERTIFICATE_TEMPLATE_NOT_FOUND),
])
@patch('futurex_openedx_extensions.helpers.certificates._has_certificate_template')
@patch('futurex_openedx_extensions.helpers.certificates.modulestore')
def test_enable_course_certificates_errors(
    mock_modulestore, mock_has_template, course, has_template, expected_code,
):
    """Verify that enabling fails without changing anything when the course or the template is missing"""
    mock_modulestore.return_value.get_course.return_value = course
    mock_has_template.return_value = has_template

    with pytest.raises(FXCodedException) as exc_info:
        enable_course_certificates(COURSE_KEY, get_user_model().objects.get(id=1))

    assert exc_info.value.code == expected_code.value
    mock_modulestore.return_value.update_item.assert_not_called()
    assert not CourseCertificateIssuance.objects.filter(course_key=COURSE_KEY).exists()


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.certificates.modulestore')
def test_disable_course_certificates(mock_modulestore):
    """Verify that disabling only stops issuance and does not touch the course"""
    disable_course_certificates(COURSE_KEY, get_user_model().objects.get(id=1))

    assert CourseCertificateIssuance.is_issuance_enabled(COURSE_KEY) is False
    mock_modulestore.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize('issuance_enabled', [None, True, False])
def test_stop_certificate_issuance_when_disabled(issuance_enabled):
    """Verify that the filter step prevents certificate creation only for disabled courses"""
    if issuance_enabled is not None:
        CourseCertificateIssuance.set_issuance_enabled(COURSE_KEY, issuance_enabled, None)
    step = StopCertificateIssuanceWhenDisabled('org.openedx.learning.certificate.creation.requested.v1', [])
    kwargs = {
        'user': Mock(), 'course_key': COURSE_KEY, 'mode': 'honor', 'status': None, 'grade': 0.9,
        'generation_mode': 'batch',
    }

    if issuance_enabled is False:
        with pytest.raises(CertificateCreationRequested.PreventCertificateCreation):
            step.run_filter(**kwargs)
    else:
        assert not step.run_filter(**kwargs)


@pytest.mark.django_db
@pytest.mark.parametrize('scenario', ['enabled', 'disabled', 'step_error'])
def test_certificate_filter_pipeline_fail_open(settings, scenario):
    """
    Verify, through the real openedx-filters pipeline with fail_silently=True, that a disabled course is still
    refused while an unexpected error inside the step lets the certificate be created.
    """
    settings.OPEN_EDX_FILTERS_CONFIG = {
        'org.openedx.learning.certificate.creation.requested.v1': {
            'fail_silently': True,
            'pipeline': ['futurex_openedx_extensions.helpers.certificates.StopCertificateIssuanceWhenDisabled'],
        },
    }
    if scenario == 'disabled':
        CourseCertificateIssuance.set_issuance_enabled(COURSE_KEY, False, None)
    user = Mock()
    kwargs = {
        'user': user, 'course_key': COURSE_KEY, 'mode': 'honor', 'status': None, 'grade': 0.9,
        'generation_mode': 'batch',
    }

    with patch.object(
        CourseCertificateIssuance, 'is_issuance_enabled',
        side_effect=RuntimeError('table does not exist') if scenario == 'step_error' else
        CourseCertificateIssuance.is_issuance_enabled,
    ):
        if scenario == 'disabled':
            with pytest.raises(CertificateCreationRequested.PreventCertificateCreation):
                CertificateCreationRequested.run_filter(**kwargs)
        else:
            assert CertificateCreationRequested.run_filter(**kwargs) == (
                user, COURSE_KEY, 'honor', None, 0.9, 'batch',
            )
