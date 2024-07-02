"""functions for getting statistics about courses"""
from __future__ import annotations

from django.db.models import Case, CharField, Count, Q, Value, When
from django.db.models.query import QuerySet
from django.utils.timezone import now

from futurex_openedx_extensions.helpers.constants import COURSE_STATUSES
from futurex_openedx_extensions.helpers.querysets import get_base_queryset_courses


def get_courses_count(
    fx_permission_info: dict, visible_filter: bool | None = True, active_filter: bool | None = None
) -> QuerySet:
    """
    Get the count of courses in the given tenants

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param visible_filter: Value to filter courses on catalog visibility. None means no filter.
    :type visible_filter: bool | None
    :param active_filter: Value to filter courses on active status. None means no filter.
    :type active_filter: bool | None
    :return: QuerySet of courses count per organization
    :rtype: QuerySet
    """
    q_set = get_base_queryset_courses(
        fx_permission_info, visible_filter=visible_filter, active_filter=active_filter
    )

    return q_set.values('org').annotate(
        courses_count=Count('id')
    ).order_by('org')


def get_courses_count_by_status(
    fx_permission_info: dict, visible_filter: bool | None = True, active_filter: bool | None = None
) -> QuerySet:
    """
    Get the count of courses in the given tenants by status

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param visible_filter: Value to filter courses on catalog visibility. None means no filter
    :type visible_filter: bool | None
    :param active_filter: Value to filter courses on active status. None means no filter (according to dates)
    :type active_filter: bool | None
    :return: QuerySet of courses count per organization and status
    :rtype: QuerySet
    """
    q_set = get_base_queryset_courses(
        fx_permission_info, visible_filter=visible_filter, active_filter=active_filter
    )

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
