"""functions for getting statistics about certificates"""
from __future__ import annotations

from typing import Dict

from django.db.models import Count, OuterRef, Subquery
from lms.djangoapps.certificates.models import GeneratedCertificate
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers.querysets import get_base_queryset_courses


def get_certificates_count(
    fx_permission_info: dict, visible_courses_filter: bool | None = True, active_courses_filter: bool | None = None
) -> Dict[str, int]:
    """
    Get the count of issued certificates in the given tenants. The count is grouped by organization. Certificates
    for admins, staff, and superusers are also included.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param visible_courses_filter: Value to filter courses on catalog visibility. None means no filter.
    :type visible_courses_filter: bool | None
    :param active_courses_filter: Value to filter courses on active status. None means no filter.
    :type active_courses_filter: bool | None
    :return: Count of certificates per organization
    :rtype: Dict[str, int]
    """
    result = list(GeneratedCertificate.objects.filter(
        status='downloadable',
        course_id__in=get_base_queryset_courses(
            fx_permission_info,
            visible_filter=visible_courses_filter,
            active_filter=active_courses_filter,
        ),
    ).annotate(course_org=Subquery(
        CourseOverview.objects.filter(
            id=OuterRef('course_id')
        ).values('org')
    )).values('course_org').annotate(certificates_count=Count('id')).values_list('course_org', 'certificates_count'))

    return dict(result)
