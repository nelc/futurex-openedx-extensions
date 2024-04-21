"""functions for getting statistics about certificates"""
from __future__ import annotations

from typing import Dict, List

from django.db.models import Count, OuterRef, Subquery
from lms.djangoapps.certificates.models import GeneratedCertificate
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers.querysets import get_base_queryset_courses
from futurex_openedx_extensions.helpers.tenants import get_course_org_filter_list


def get_certificates_count(
    tenant_ids: List[int], only_visible_courses: bool = True, only_active_courses: bool = False
) -> Dict[str, int]:
    """
    Get the count of issued certificates in the given tenants. The count is grouped by organization. Certificates
    for admins, staff, and superusers are also included.

    :param tenant_ids: List of tenant IDs to get the count for
    :type tenant_ids: List[int]
    :param only_visible_courses: Whether to only count courses that are visible in the catalog
    :type only_visible_courses: bool
    :param only_active_courses: Whether to only count active courses (according to dates)
    :type only_active_courses: bool
    :return: Count of certificates per organization
    :rtype: Dict[str, int]
    """
    course_org_filter_list = get_course_org_filter_list(tenant_ids)['course_org_filter_list']

    result = list(GeneratedCertificate.objects.filter(
        status='downloadable',
        course_id__in=get_base_queryset_courses(
            course_org_filter_list,
            only_visible=only_visible_courses,
            only_active=only_active_courses,
        ),
    ).annotate(course_org=Subquery(
        CourseOverview.objects.filter(
            id=OuterRef('course_id')
        ).values('org')
    )).values('course_org').annotate(certificates_count=Count('id')).values_list('course_org', 'certificates_count'))

    return dict(result)
