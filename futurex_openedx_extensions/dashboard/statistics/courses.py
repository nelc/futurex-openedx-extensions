"""functions for getting statistics about courses"""
from __future__ import annotations

from typing import List

from django.db.models import Count, Q
from django.db.models.query import QuerySet
from django.utils.timezone import now
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers.tenants import get_course_org_filter_list


def get_courses_count(tenant_ids: List[int], only_active=False, only_visible=False) -> QuerySet:
    """
    Get the count of courses in the given tenants

    :param tenant_ids: List of tenant IDs to get the count for
    :type tenant_ids: List[int]
    :param only_active: Whether to only count active courses (according to dates)
    :type only_active: bool
    :param only_visible: Whether to only count visible courses (according to staff-only visibility)
    :type only_visible: bool
    :return: QuerySet of courses count per organization
    :rtype: QuerySet
    """
    course_org_filter_list = get_course_org_filter_list(tenant_ids)['course_org_filter_list']

    q_set = CourseOverview.objects.filter(org__in=course_org_filter_list)
    if only_active:
        q_set = q_set.filter(
            Q(start__isnull=True) | Q(start__lte=now()),
        ).filter(
            Q(end__isnull=True) | Q(end__gte=now()),
        )
    if only_visible:
        q_set = q_set.filter(visible_to_staff_only=False)

    return q_set.values('org').annotate(
        courses_count=Count('id')
    ).order_by('org')
