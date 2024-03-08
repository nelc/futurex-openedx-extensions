"""Permission classes for FutureX Open edX Extensions."""
import json

from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.permissions import IsAuthenticated

from futurex_openedx_extensions.helpers.tenants import check_tenant_access


class HasTenantAccess(IsAuthenticated):
    """Permission class to check if the user is a tenant admin."""
    def has_permission(self, request, view):
        """Check if the user is a permission to the tenant"""
        if not super().has_permission(request, view):
            raise NotAuthenticated()

        tenant_ids = request.GET.get('tenant_ids')
        if tenant_ids:
            has_access, details = check_tenant_access(request.user, tenant_ids)
            if not has_access:
                raise PermissionDenied(detail=json.dumps(details))

        return True
