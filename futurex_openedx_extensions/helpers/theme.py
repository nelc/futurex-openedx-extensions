""""Theme helpers"""
from typing import Any, Optional

from django.conf import settings

from futurex_openedx_extensions.helpers.roles import get_accessible_tenant_ids
from futurex_openedx_extensions.helpers.tenants import get_all_tenants_info
from futurex_openedx_extensions.helpers.users import is_system_staff_user
from futurex_openedx_extensions.upgrade.models_switch import CourseAccessRole


def get_fx_dashboard_url(request: Any) -> Optional[str]:
    """
    Get Fx Dashboard URL

    :param request: Current django request.
    :type request: Request
    :return: Fx Dashboard URL
    :rtype: str
    """
    if (
        getattr(request, 'site', None) is None or
        not getattr(request.site, 'domain', None) or
        not getattr(settings, 'NELC_DASHBOARD_BASE', None)
    ):
        return None

    if (
        is_system_staff_user(request.user) or
        CourseAccessRole.objects.filter(user_id=request.user.id).exists()
    ):
        lang = 'en' if request.LANGUAGE_CODE == 'en' else 'ar'
        user_accessible_tenant_ids = get_accessible_tenant_ids(request.user)
        tenant_info = get_all_tenants_info()
        for tenant_id, site in tenant_info['sites'].items():
            if site == request.site.domain and tenant_id in user_accessible_tenant_ids:
                return f'{request.scheme}://{settings.NELC_DASHBOARD_BASE}/{lang}/{tenant_id}'
    return None
