"""functions for getting statistics about courses"""
from __future__ import annotations

from django.db.models import Case, CharField, Count, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.db.models.query import QuerySet
from django.utils.timezone import now

from futurex_openedx_extensions.dashboard.details.courses import annotate_courses_rating_queryset
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


def get_courses_ratings(
    fx_permission_info: dict,
    visible_filter: bool | None = True,
    active_filter: bool | None = None,
) -> QuerySet:
    """
    Get the average rating of courses in the given tenants

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param visible_filter: Value to filter courses on catalog visibility. None means no filter
    :type visible_filter: bool | None
    :param active_filter: Value to filter courses on active status. None means no filter (according to dates)
    :type active_filter: bool | None
    :return: QuerySet of average rating per organization
    :rtype: QuerySet
    """
    q_set = get_base_queryset_courses(
        fx_permission_info, visible_filter=visible_filter, active_filter=active_filter
    )

    q_set = annotate_courses_rating_queryset(q_set).filter(rating_count__gt=0)
    # annotate the count of all records with FeedbackCourse rating equal 1 using subquery on FeedbackCourse
    q_set = q_set.annotate(
        course_rating_1_count=Count(
            'feedbackcourse',
            filter=Q(feedbackcourse__rating_content=1)
        ),
        course_rating_2_count=Count(
            'feedbackcourse',
            filter=Q(feedbackcourse__rating_content=2)
        ),
        course_rating_3_count=Count(
            'feedbackcourse',
            filter=Q(feedbackcourse__rating_content=3)
        ),
        course_rating_4_count=Count(
            'feedbackcourse',
            filter=Q(feedbackcourse__rating_content=4)
        ),
        course_rating_5_count=Count(
            'feedbackcourse',
            filter=Q(feedbackcourse__rating_content=5)
        ),
    )

    q_set = q_set.aggregate(
        total_rating=Coalesce(Sum('rating_total'), 0),
        courses_count=Coalesce(Count('id'), 0),
        rating_1_count=Coalesce(Sum('course_rating_1_count'), 0),
        rating_2_count=Coalesce(Sum('course_rating_2_count'), 0),
        rating_3_count=Coalesce(Sum('course_rating_3_count'), 0),
        rating_4_count=Coalesce(Sum('course_rating_4_count'), 0),
        rating_5_count=Coalesce(Sum('course_rating_5_count'), 0),
    )

    return q_set
