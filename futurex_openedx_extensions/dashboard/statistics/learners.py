"""functions for getting statistics about learners"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Count, Q

from futurex_openedx_extensions.dashboard.toggles import is_legacy_filtered_counts_enabled
from futurex_openedx_extensions.helpers.querysets import (
    check_staff_exist_queryset,
    get_learners_search_queryset,
    get_permitted_learners_queryset,
)


def get_learners_count(
    fx_permission_info: dict,
    include_staff: bool = False,
) -> int:
    """
    Get the count of learners in the given list of tenants. Admins and staff are excluded from the count.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param include_staff: flag to include staff users
    :type include_staff: bool
    :return: Dictionary of tenant ID and the count of learners
    :rtype: Dict[int, Dict[str, int]]
    """
    if not is_legacy_filtered_counts_enabled():
        return get_permitted_learners_queryset(
            queryset=get_learners_search_queryset(
                superuser_filter=None, staff_filter=None,
            ),
            fx_permission_info=fx_permission_info,
            include_staff=True,
        ).count()

    queryset = get_learners_search_queryset()

    queryset = get_permitted_learners_queryset(
        queryset=queryset,
        fx_permission_info=fx_permission_info,
        include_staff=include_staff,
    )

    return queryset.count()


LEARNERS_BREAKDOWN_STAGES = [
    'in_tenant',
    'active_user',
    'excluding_platform_staff',
    'excluding_course_staff',
]


def get_learners_count_breakdown(
    fx_permission_info: dict,
    include_staff: bool = False,
) -> dict:
    """
    Get the learners count broken down by filter stage.

    The base stage is deliberately the tenant-scoped population rather than every user on the
    platform: tenant membership for a learner is decided by signup source (or, for tenants the caller
    only partially accesses, by enrolment), and an unscoped first stage would report the whole
    installation, which tells the caller nothing. Each later stage adds one of the filters
    `get_learners_count` applies, so the drop between two stages is attributable to a single rule,
    and the last stage equals `get_learners_count` for the same arguments.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param include_staff: Value to include staff users in the last stage. False means exclude them.
    :type include_staff: bool
    :return: Dictionary of learners count per stage
    :rtype: dict
    """
    queryset = get_permitted_learners_queryset(
        queryset=get_user_model().objects.all(),
        fx_permission_info=fx_permission_info,
        include_staff=True,
    ).annotate(
        is_course_staff=check_staff_exist_queryset(
            ref_user_id='id',
            ref_org=fx_permission_info['view_allowed_any_access_orgs'],
            ref_course_id=None,
        ),
    )

    active_user_q = Q(is_active=True)
    not_platform_staff_q = active_user_q & Q(is_staff=False) & Q(is_superuser=False)
    not_course_staff_q = not_platform_staff_q if include_staff else not_platform_staff_q & Q(is_course_staff=False)

    return queryset.aggregate(
        in_tenant=Count('id'),
        active_user=Count('id', filter=active_user_q),
        excluding_platform_staff=Count('id', filter=not_platform_staff_q),
        excluding_course_staff=Count('id', filter=not_course_staff_q),
    )
