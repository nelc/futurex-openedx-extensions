"""functions for getting statistics about courses"""
from __future__ import annotations

from datetime import date, datetime
from typing import Dict

from common.djangoapps.student.models import CourseEnrollment
from django.db.models import Case, CharField, Count, Q, Sum, Value, When
from django.db.models.functions import Coalesce, Lower
from django.db.models.query import QuerySet
from django.utils.timezone import now
from eox_nelp.course_experience.models import FeedbackCourse

from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.dashboard.toggles import is_legacy_filtered_counts_enabled
from futurex_openedx_extensions.helpers.caching import cache_dict
from futurex_openedx_extensions.helpers.constants import COURSE_STATUSES, RATING_RANGE
from futurex_openedx_extensions.helpers.extractors import get_valid_duration
from futurex_openedx_extensions.helpers.permissions import build_fx_permission_info
from futurex_openedx_extensions.helpers.querysets import (
    annotate_period,
    check_staff_exist_queryset,
    get_base_queryset_courses,
)


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

    return q_set.values(org_lower_case=Lower('org')).annotate(
        courses_count=Count('id')
    ).order_by(Lower('org'))


COURSES_BREAKDOWN_STAGES = [
    'all_courses',
    'in_visible_courses',
]


def get_courses_count_breakdown(fx_permission_info: dict) -> QuerySet:
    """
    Get the courses count per organization broken down by filter stage.

    Only one filter separates the two stages, so the breakdown is short by nature: `all_courses`
    counts every course the caller can reach, and `in_visible_courses` keeps those visible in the
    catalog, which is what `get_courses_count` reports. The difference is exactly the
    `hidden_courses` statistic.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :return: QuerySet of courses count per organization and stage
    :rtype: QuerySet
    """
    q_set = get_base_queryset_courses(fx_permission_info, visible_filter=None, active_filter=None)

    visible_q = Q(catalog_visibility__in=['about', 'both']) & Q(visible_to_staff_only=False)

    return q_set.values(org_lower_case=Lower('org')).annotate(
        all_courses=Count('id'),
        in_visible_courses=Count('id', filter=visible_q),
    ).order_by(Lower('org'))


def _get_enrollments_count(
    fx_permission_info: dict,
    visible_filter: bool | None = True,
    active_filter: bool | None = None,
    include_staff: bool = False,
) -> QuerySet:
    """
    Get the count of courses in the given tenants

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param visible_filter: Value to filter courses on catalog visibility. None means no filter.
    :type visible_filter: bool | None
    :param active_filter: Value to filter courses on active status. None means no filter.
    :type active_filter: bool | None
    :param include_staff: Value to include staff users in the count. False means exclude staff users.
    :type include_staff: bool
    :return: QuerySet of courses count per organization
    :rtype: QuerySet
    """
    if not is_legacy_filtered_counts_enabled():
        return CourseEnrollment.objects.filter(
            course_id__in=get_base_queryset_courses(
                fx_permission_info, visible_filter=None, active_filter=None
            ).values_list('id', flat=True),
            is_active=True,
        )

    q_set = CourseEnrollment.objects.filter(
        course_id__in=get_base_queryset_courses(
            fx_permission_info, visible_filter=visible_filter, active_filter=active_filter
        ).values_list('id', flat=True),
        is_active=True,
    ).exclude(
        Q(user__is_active=False) | Q(user__is_staff=True) | Q(user__is_superuser=True)
    )

    if not include_staff:
        q_set = q_set.exclude(check_staff_exist_queryset('user_id', 'course__org', 'course_id'))

    return q_set


def get_enrollments_count(
    fx_permission_info: dict,
    visible_filter: bool | None = True,
    active_filter: bool | None = None,
    include_staff: bool = False,
) -> QuerySet:
    """
    Get the count of courses in the given tenants

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param visible_filter: Value to filter courses on catalog visibility. None means no filter.
    :type visible_filter: bool | None
    :param active_filter: Value to filter courses on active status. None means no filter.
    :type active_filter: bool | None
    :param include_staff: Value to include staff users in the count. False means exclude staff users.
    :type include_staff: bool
    :return: QuerySet of courses count per organization
    :rtype: QuerySet
    """
    q_set = _get_enrollments_count(
        fx_permission_info, visible_filter=visible_filter, active_filter=active_filter, include_staff=include_staff,
    )

    return q_set.values(org_lower_case=Lower('course__org')).annotate(
        enrollments_count=Count('id')
    ).order_by(Lower('course__org'))


ENROLLMENTS_BREAKDOWN_STAGES = [
    'all_rows',
    'active_enrollment',
    'active_user',
    'excluding_platform_staff',
    'in_visible_courses',
    'excluding_course_staff',
]


def get_enrollments_count_breakdown(
    fx_permission_info: dict,
    include_staff: bool = False,
) -> QuerySet:
    """
    Get the enrollments count per organization broken down by filter stage.

    Each stage adds exactly one of the filters that `get_enrollments_count` applies, in the order it
    applies them, so the drop between two stages is attributable to a single rule. The first stage is
    the raw row count that Open edX's own screens report; the last stage equals what
    `get_enrollments_count` returns for the same arguments.

    The whole breakdown is computed in a single pass with conditional aggregation. Running one query
    per stage would multiply the cost of an already expensive query.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param include_staff: Value to include staff users in the last stage. False means exclude them.
    :type include_staff: bool
    :return: QuerySet of enrollments count per organization and stage
    :rtype: QuerySet
    """
    q_set = CourseEnrollment.objects.filter(
        course_id__in=get_base_queryset_courses(
            fx_permission_info, visible_filter=None, active_filter=None
        ).values_list('id', flat=True),
    ).annotate(
        is_course_staff=check_staff_exist_queryset('user_id', 'course__org', 'course_id'),
    )

    visible_q = Q(course__catalog_visibility__in=['about', 'both']) & Q(course__visible_to_staff_only=False)
    active_enrollment_q = Q(is_active=True)
    active_user_q = active_enrollment_q & Q(user__is_active=True)
    not_platform_staff_q = active_user_q & Q(user__is_staff=False) & Q(user__is_superuser=False)
    visible_courses_q = not_platform_staff_q & visible_q
    not_course_staff_q = visible_courses_q if include_staff else visible_courses_q & Q(is_course_staff=False)

    return q_set.values(org_lower_case=Lower('course__org')).annotate(
        all_rows=Count('id'),
        active_enrollment=Count('id', filter=active_enrollment_q),
        active_user=Count('id', filter=active_user_q),
        excluding_platform_staff=Count('id', filter=not_platform_staff_q),
        in_visible_courses=Count('id', filter=visible_courses_q),
        excluding_course_staff=Count('id', filter=not_course_staff_q),
    ).order_by(Lower('course__org'))


def get_enrollments_count_aggregated(  # pylint: disable=too-many-arguments
    fx_permission_info: dict,
    visible_filter: bool | None = True,
    active_filter: bool | None = None,
    include_staff: bool = False,
    aggregate_period: str = 'month',
    date_from: date | None = None,
    date_to: date | None = None,
    favors_backward: bool = True,
    max_period_chunks: int = 0,
) -> tuple[QuerySet, datetime | None, datetime | None]:
    """
    Get the count of enrollments in the given tenants aggregated by period. The query will return a limited number of
    period values, depending on the date range and the period.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param visible_filter: Value to filter courses on catalog visibility. None means no filter.
    :type visible_filter: bool | None
    :param active_filter: Value to filter courses on active status. None means no filter.
    :type active_filter: bool | None
    :param include_staff: Value to include staff users in the count. False means exclude staff users.
    :type include_staff: bool
    :param aggregate_period: Period to aggregate the count of enrollments. Possible values are 'day', 'month'.
    :type aggregate_period: str
    :param date_from: Start date to filter enrollments (inclusive). None means no filter.
    :type date_from: date | None
    :param date_to: End date to filter enrollments (inclusive). None means no filter.
    :type date_to: date | None
    :param favors_backward: Value to indicate if dates are favored to go backward. False means forward.
    :type favors_backward: bool
    :param max_period_chunks: Maximum number of period chunks to return. 0 means as default. Negative means no limit.
    :type max_period_chunks: int
    :return: QuerySet of enrollments count per organization and period
    """
    calculated_date_from, calculated_date_to = get_valid_duration(
        period=aggregate_period,
        date_from=date_from,
        date_to=date_to,
        favors_backward=favors_backward,
        max_chunks=max_period_chunks,
    )

    q_set = _get_enrollments_count(
        fx_permission_info, visible_filter=visible_filter, active_filter=active_filter, include_staff=include_staff,
    )

    if calculated_date_from:
        q_set = q_set.filter(created__gte=calculated_date_from)
    if calculated_date_to:
        q_set = q_set.filter(created__lte=calculated_date_to)

    q_set = annotate_period(query_set=q_set, period=aggregate_period, field_name='created')

    q_set = q_set.values('period').annotate(
        enrollments_count=Count('id')
    ).order_by('period')

    return q_set, calculated_date_from, calculated_date_to


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


def cache_name_courses_rating(
    tenant_id: int,
    visible_filter: bool | None = True,
    active_filter: bool | None = None,
) -> str:
    """
    Generate cache key for get_courses_ratings

    :param tenant_id: Tenant ID
    :type tenant_id: int
    :param visible_filter: Value to filter courses on catalog visibility
    :type visible_filter: bool | None
    :param active_filter: Value to filter courses on active status
    :type active_filter: bool | None
    :return: Cache key string
    :rtype: str
    """
    return f'{cs.CACHE_NAME_COURSES_RATINGS}_t{tenant_id}_v{visible_filter}_a{active_filter}'


@cache_dict(
    timeout='FX_CACHE_TIMEOUT_COURSES_RATINGS',
    key_generator_or_name=cache_name_courses_rating
)
def get_courses_ratings(
    tenant_id: int,
    visible_filter: bool | None = True,
    active_filter: bool | None = None,
) -> Dict[str, int]:
    """
    Get the average rating of courses for a single tenant. Results are cached per tenant.

    :param tenant_id: Tenant ID to get ratings for
    :type tenant_id: int
    :param visible_filter: Value to filter courses on catalog visibility. None means no filter
    :type visible_filter: bool | None
    :param active_filter: Value to filter courses on active status. None means no filter (according to dates)
    :type active_filter: bool | None
    :return: Dictionary containing the total rating, courses count, and rating count per rating value
    :rtype: Dict[str, int]
    """
    fx_permission_info = build_fx_permission_info(tenant_id)

    accessible_course_ids = list(
        get_base_queryset_courses(fx_permission_info, visible_filter=visible_filter, active_filter=active_filter)
        .values_list('id', flat=True)
    )

    feedbacks_qs = FeedbackCourse.objects.filter(
        course_id__in=accessible_course_ids,
        rating_content__isnull=False,
        rating_content__gt=0,
    )

    rating_groups = feedbacks_qs.values('rating_content').annotate(count=Count('id'))

    rating_map = {int(item['rating_content']): int(item['count']) for item in rating_groups}

    total_rating_agg = feedbacks_qs.aggregate(total_rating=Coalesce(Sum('rating_content'), 0))
    courses_count_agg = feedbacks_qs.aggregate(courses_count=Coalesce(Count('course_id', distinct=True), 0))

    result: Dict[str, int] = {
        'total_rating': int(total_rating_agg.get('total_rating', 0)),
        'courses_count': int(courses_count_agg.get('courses_count', 0)),
    }

    for rate_value in RATING_RANGE:
        result[f'rating_{rate_value}_count'] = int(rating_map.get(rate_value, 0))

    return result
