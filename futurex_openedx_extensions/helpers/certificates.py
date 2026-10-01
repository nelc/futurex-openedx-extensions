"""Helper functions for certificates."""
from __future__ import annotations

from typing import Any

from common.djangoapps.course_modes.models import CourseMode
from django.contrib.auth import get_user_model
from lms.djangoapps.certificates.api import get_certificate_template, get_certificates_for_user_by_course_keys
from opaque_keys.edx.keys import CourseKey
from opaque_keys.edx.locator import CourseLocator
from openedx_filters import PipelineStep
from openedx_filters.learning.filters import CertificateCreationRequested
from xmodule.modulestore.django import modulestore

from futurex_openedx_extensions.helpers.converters import relative_url_to_absolute_url
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.models import CourseCertificateIssuance
from futurex_openedx_extensions.helpers.tenants import set_request_domain_by_org


def get_certificate_date(user: get_user_model, course_id: CourseLocator) -> Any:
    """
    Return the certificate date for the given user and course.

    :param user: The user object.
    :type user: get_user_model
    :param course_id: The course ID.
    :type course_id: CourseLocator
    :return: The certificate URL.
    """
    certificates = get_certificates_for_user_by_course_keys(user, [course_id])
    passing_certificate_url = certificates.get(course_id, {}).get('download_url')
    if passing_certificate_url:
        return certificates.get(course_id, {}).get('created')

    return None


def get_certificate_url(request: Any, user: get_user_model, course_id: CourseLocator) -> Any:
    """
    Return the certificate URL for the given user and course.

    :param request: The request object.
    :type request: Any
    :param user: The user object.
    :type user: get_user_model
    :param course_id: The course ID.
    :type course_id: CourseLocator
    :return: The certificate URL.
    """
    certificates = get_certificates_for_user_by_course_keys(user, [course_id])
    passing_certificate_url = certificates.get(course_id, {}).get('download_url')
    if passing_certificate_url:
        if passing_certificate_url.startswith('/'):
            set_request_domain_by_org(request, course_id.org)
            passing_certificate_url = relative_url_to_absolute_url(passing_certificate_url, request)
        return passing_certificate_url

    return None


def _has_certificate_template(course_key: CourseKey, language: str | None) -> bool:
    """
    Return True if a certificate template resolves for any of the course modes (honor when the course has none).
    """
    modes = [
        mode.slug for mode in CourseMode.modes_for_course(
            course_id=course_key, include_expired=True, only_selectable=False,
        )
    ] or ['honor']
    return any(get_certificate_template(course_key, mode, language) for mode in modes)


def enable_course_certificates(course_key: CourseKey, user: get_user_model) -> None:
    """
    Make the course issue certificates: activate its certificate configuration (creating it if missing), enable the
    HTML certificate view, and enable issuance.

    :param course_key: The course key.
    :type course_key: CourseKey
    :param user: The user performing the change.
    :type user: get_user_model
    """
    course = modulestore().get_course(course_key)
    if not course:
        raise FXCodedException(
            code=FXExceptionCodes.COURSE_CERTIFICATE_COURSE_NOT_FOUND,
            message=f'Course not found: {course_key}',
        )

    if not _has_certificate_template(course_key, course.language):
        raise FXCodedException(
            code=FXExceptionCodes.COURSE_CERTIFICATE_TEMPLATE_NOT_FOUND,
            message=f'No active certificate template matches the course: {course_key}',
        )

    certificates = course.certificates or {}
    configurations = certificates.setdefault('certificates', [])
    if configurations:
        configurations[0]['is_active'] = True
    else:
        configurations.append({
            'id': 100,
            'name': 'Course Certificate',
            'description': 'Course Certificate',
            'version': 1,
            'is_active': True,
            'course_title': '',
            'signatories': [],
        })
    course.certificates = certificates
    course.cert_html_view_enabled = True
    modulestore().update_item(course, user.id)

    CourseCertificateIssuance.set_issuance_enabled(course_key, True, user)


def disable_course_certificates(course_key: CourseKey, user: get_user_model) -> None:
    """
    Stop issuing NEW certificates for the course. The certificate configuration and the HTML certificate view are
    left untouched so already-issued certificates remain valid.

    :param course_key: The course key.
    :type course_key: CourseKey
    :param user: The user performing the change.
    :type user: get_user_model
    """
    CourseCertificateIssuance.set_issuance_enabled(course_key, False, user)


class StopCertificateIssuanceWhenDisabled(PipelineStep):  # pylint: disable=too-few-public-methods
    """
    Filter step for org.openedx.learning.certificate.creation.requested.v1 that prevents creating a certificate
    for a course whose issuance is disabled.
    """
    def run_filter(  # pylint: disable=arguments-differ, too-many-arguments, unused-argument
        self, user: Any, course_key: Any, mode: Any, status: Any, grade: Any, generation_mode: Any,
    ) -> dict:
        """Raise PreventCertificateCreation when issuance is disabled for the course."""
        if not CourseCertificateIssuance.is_issuance_enabled(course_key):
            raise CertificateCreationRequested.PreventCertificateCreation(
                f'Certificate issuance is disabled for the course: {course_key}'
            )
        return {}
