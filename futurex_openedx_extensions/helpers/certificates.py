"""Helper functions for certificates."""
from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from lms.djangoapps.certificates.api import get_certificates_for_user_by_course_keys
from opaque_keys.edx.locator import CourseLocator

from futurex_openedx_extensions.helpers.converters import relative_url_to_absolute_url
from futurex_openedx_extensions.helpers.tenants import set_request_domain_by_org


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
    certificate = get_certificates_for_user_by_course_keys(user, [course_id])
    if certificate:
        url = certificate.get(course_id, {}).get('download_url')
        if url and url.startswith('/'):
            set_request_domain_by_org(request, course_id.org)
            url = relative_url_to_absolute_url(url, request)
        return url

    return None
