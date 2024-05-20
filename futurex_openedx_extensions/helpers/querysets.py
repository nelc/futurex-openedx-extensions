"""Helper functions for working with Django querysets."""
from __future__ import annotations

from typing import List

from django.db.models import Q
from django.db.models.query import QuerySet
from django.utils.timezone import now
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview


def get_base_queryset_courses(
    course_org_filter_list: List[str],
    only_visible: bool = True,
    only_active: bool = False,
) -> QuerySet:
    """
    Get the default course queryset for the given filters.

    :param course_org_filter_list: List of course organizations to filter by
    :type course_org_filter_list: List[str]
    :param only_visible: Whether to only include courses that are visible in the catalog
    :type only_visible: bool
    :param only_active: Whether to only include active courses
    :type only_active: bool
    :return: QuerySet of courses
    :rtype: QuerySet
    """
    q_set = CourseOverview.objects.filter(org__in=course_org_filter_list)
    if only_active:
        q_set = q_set.filter(
            Q(start__isnull=True) | Q(start__lte=now()),
        ).filter(
            Q(end__isnull=True) | Q(end__gte=now()),
        )
    if only_visible:
        q_set = q_set.filter(catalog_visibility__in=['about', 'both'])

    return q_set
