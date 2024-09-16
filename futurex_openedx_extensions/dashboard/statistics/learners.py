"""functions for getting statistics about learners"""
from __future__ import annotations

from common.djangoapps.student.models import UserSignupSource
from django.db.models import BooleanField, Q, Value

from futurex_openedx_extensions.helpers.querysets import check_staff_exist_queryset
from futurex_openedx_extensions.helpers.tenants import get_tenant_site


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
    tenant_sites = [get_tenant_site(tenant_id) for tenant_id in fx_permission_info['permitted_tenant_ids']]

    if include_staff:
        is_staff_queryset = Q(Value(False, output_field=BooleanField()))
    else:
        is_staff_queryset = check_staff_exist_queryset(
            ref_user_id='user_id',
            ref_org=fx_permission_info['view_allowed_full_access_orgs'],
            ref_course_id=None,
        )

    user_from_signup_source = UserSignupSource.objects.filter(
        site__in=tenant_sites
    ).exclude(
        Q(user__is_superuser=True) |
        Q(user__is_staff=True) |
        Q(user__is_active=False)
    ).exclude(
        is_staff_queryset
    ).values('user_id').order_by('user_id').distinct()

    return user_from_signup_source.count()
