"""Helper functions for working with Django querysets."""
from __future__ import annotations

from typing import List

from common.djangoapps.student.models import UserSignupSource
from django.db.models import BooleanField, Case, Exists, OuterRef, Q, Value, When
from django.db.models.query import QuerySet
from django.utils.timezone import now
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview


def get_base_queryset_courses(
    course_org_filter_list: List[str],
    visible_filter: bool | None = True,
    active_filter: bool | None = None,
) -> QuerySet:
    """
    Get the default course queryset for the given filters.

    :param course_org_filter_list: List of course organizations to filter by
    :type course_org_filter_list: List[str]
    :param visible_filter: Value to filter courses on catalog visibility. None means no filter.
    :type visible_filter: bool | None
    :param active_filter: Value to filter courses on active status. None means no filter.
    :type active_filter: bool | None
    :return: QuerySet of courses
    :rtype: QuerySet
    """
    now_time = now()
    course_is_active_queryset = (
        (Q(start__isnull=True) | Q(start__lte=now_time)) &
        (Q(end__isnull=True) | Q(end__gte=now_time))
    )

    course_is_visible_queryset = Q(catalog_visibility__in=['about', 'both']) & Q(visible_to_staff_only=False)

    q_set = CourseOverview.objects.filter(
        org__in=course_org_filter_list,
    ).annotate(
        course_is_active=Case(
            When(course_is_active_queryset, then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        ),
    ).annotate(
        course_is_visible=Case(
            When(course_is_visible_queryset, then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        ),
    )

    if active_filter is not None:
        q_set = q_set.filter(course_is_active=active_filter)

    if visible_filter is not None:
        q_set = q_set.filter(course_is_visible=visible_filter)

    return q_set


def get_has_site_login_queryset(tenant_sites: List[str]) -> QuerySet:
    """
    Get the queryset of users who have logged in to any of the given tenant sites.

    :param tenant_sites: List of tenant sites to check for
    :type tenant_sites: List[str]
    :return: QuerySet of users
    :rtype: QuerySet
    """
    return Exists(
        UserSignupSource.objects.filter(
            user_id=OuterRef('id'),
            site__in=tenant_sites
        )
    )
