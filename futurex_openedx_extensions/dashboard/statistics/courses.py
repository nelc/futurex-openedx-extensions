"""functions for getting statistics about courses"""
from __future__ import annotations

from typing import List

from django.db.models import Case, CharField, Count, Q, Value, When
from django.db.models.query import QuerySet
from django.utils.timezone import now

from futurex_openedx_extensions.helpers.constants import COURSE_STATUSES
from futurex_openedx_extensions.helpers.querysets import get_base_queryset_courses
from futurex_openedx_extensions.helpers.tenants import get_course_org_filter_list


def get_courses_count(tenant_ids: List[int], only_visible: bool = True, only_active: bool = False) -> QuerySet:
    """
    Get the count of courses in the given tenants

    :param tenant_ids: List of tenant IDs to get the count for
    :type tenant_ids: List[int]
    :param only_visible: Whether to only count courses that are visible in the catalog
    :type only_visible: bool
    :param only_active: Whether to only count active courses (according to dates)
    :type only_active: bool
    :return: QuerySet of courses count per organization
    :rtype: QuerySet
    """
    course_org_filter_list = get_course_org_filter_list(tenant_ids)['course_org_filter_list']

    q_set = get_base_queryset_courses(course_org_filter_list, only_visible=only_visible, only_active=only_active)

    return q_set.values('org').annotate(
        courses_count=Count('id')
    ).order_by('org')


def get_courses_count_by_status(
    tenant_ids: List[int], only_visible: bool = True, only_active: bool = False
) -> QuerySet:
    """
    Get the count of courses in the given tenants by status

    :param tenant_ids: List of tenant IDs to get the count for
    :type tenant_ids: List[int]
    :param only_visible: Whether to only count courses that are visible in the catalog
    :type only_visible: bool
    :param only_active: Whether to only count active courses (according to dates)
    :type only_active: bool
    :return: QuerySet of courses count per organization and status
    :rtype: QuerySet
    """
    course_org_filter_list = get_course_org_filter_list(tenant_ids)['course_org_filter_list']

    q_set = get_base_queryset_courses(course_org_filter_list, only_visible=only_visible, only_active=only_active)

    q_set = q_set.annotate(
        status=Case(
            When(
                Q(end__isnull=False) & Q(end__lt=now()),
                then=Value(COURSE_STATUSES['archived'])
            ),
            When(
                Q(start__isnull=False) & Q(start__gt=now()),
                then=Value(COURSE_STATUSES['upcoming'])
            ),
            default=Value(COURSE_STATUSES['active']),
            output_field=CharField()
        )
    ).values('status', 'self_paced').annotate(
        courses_count=Count('id')
    ).values('status', 'self_paced', 'courses_count')

    return q_set
