""""Theme helpers"""
from typing import Any, Optional

from common.djangoapps.student.models import CourseAccessRole
from django.conf import settings

from futurex_openedx_extensions.helpers.roles import get_accessible_tenant_ids
from futurex_openedx_extensions.helpers.tenants import get_all_tenants_info
from futurex_openedx_extensions.helpers.users import is_system_staff_user


def get_fx_dashboard_url(request: Any) -> Optional[str]:
    """
    Get Fx Dashboard URL

    :param request: Current django request.
    :type request: Request
    :return: Fx Dashboard URL
    :rtype: str
    """
    if (
        is_system_staff_user(request.user) or
        CourseAccessRole.objects.filter(user_id=request.user.id).exists()
    ):
        lang = 'en' if request.LANGUAGE_CODE == 'en' else 'ar'
        user_accessible_tenant_ids = get_accessible_tenant_ids(request.user)
        tenant_info = get_all_tenants_info()
        for tenant_id, site in tenant_info['sites'].items():
            if site == request.site.name and tenant_id in user_accessible_tenant_ids:
                return f'{request.scheme}://dashboard.{settings.LMS_BASE}/{lang}/{tenant_id}'
    return None
