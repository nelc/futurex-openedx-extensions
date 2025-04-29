"""Live statistics"""
from django.conf import settings

from futurex_openedx_extensions.dashboard.statistics.certificates import (
    get_certificates_count,
    get_learning_hours_count,
)
from futurex_openedx_extensions.dashboard.statistics.courses import get_courses_count, get_enrollments_count
from futurex_openedx_extensions.dashboard.statistics.learners import get_learners_count
from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers.caching import cache_dict
from futurex_openedx_extensions.helpers.permissions import build_fx_permission_info


@cache_dict(
    settings.FX_CACHE_TIMEOUT_LIVE_STATISTICS_PER_TENANT,
    lambda tenant_id: f'{cs.CACHE_NAME_LIVE_STATISTICS_PER_TENANT}_{tenant_id}',
)
def get_live_statistics(tenant_id: int) -> dict:
    """
    Get the live statistics for the given tenant.

    :param tenant_id: The ID of the tenant.
    :type tenant_id: int
    :return: A dictionary containing the live statistics for the given tenant.
    :rtype: dict
    """
    fx_permission_info = build_fx_permission_info(tenant_id)
    result = {
        'learners_count': 0,
        'courses_count': 0,
        'enrollments_count': 0,
        'certificates_count': 0,
        'learning_hours_count': 0,
    }
    if fx_permission_info['view_allowed_tenant_ids_any_access']:
        result['learners_count'] = get_learners_count(fx_permission_info)
        result['courses_count'] = sum(org_count['courses_count'] for org_count in get_courses_count(fx_permission_info))
        result['enrollments_count'] = sum(
            org_count['enrollments_count'] for org_count in get_enrollments_count(fx_permission_info)
        )
        result['certificates_count'] = sum(
            certificate_count for certificate_count in get_certificates_count(fx_permission_info).values()
        )
        result['learning_hours_count'] = get_learning_hours_count(fx_permission_info)

    return result
