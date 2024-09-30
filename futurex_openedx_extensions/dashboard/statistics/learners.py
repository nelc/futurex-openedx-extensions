"""functions for getting statistics about learners"""
from __future__ import annotations

from futurex_openedx_extensions.helpers.querysets import get_learners_search_queryset, get_permitted_learners_queryset


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
    queryset = get_learners_search_queryset()

    queryset = get_permitted_learners_queryset(
        queryset=queryset,
        fx_permission_info=fx_permission_info,
        include_staff=include_staff,
    )

    return queryset.count()
