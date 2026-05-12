"""Views for the dashboard app - admin feature"""
# pylint: disable=duplicate-code

from __future__ import annotations

from typing import Any

from common.djangoapps.student.models import get_user_by_username_or_email
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.query import QuerySet
from django.http import JsonResponse
from django_filters.rest_framework import DjangoFilterBackend
from edx_api_doc_tools import exclude_schema_for
from rest_framework import viewsets
from rest_framework.parsers import MultiPartParser
from rest_framework.views import APIView

from futurex_openedx_extensions.dashboard import serializers
from futurex_openedx_extensions.dashboard.docs_utils import docs
from futurex_openedx_extensions.dashboard.views.routers import use_read_replica_if_available
from futurex_openedx_extensions.helpers.constants import FX_VIEW_DEFAULT_AUTH_CLASSES
from futurex_openedx_extensions.helpers.filters import DefaultOrderingFilter, DefaultSearchFilter
from futurex_openedx_extensions.helpers.models import TenantAsset
from futurex_openedx_extensions.helpers.pagination import DefaultPagination
from futurex_openedx_extensions.helpers.permissions import (
    FXHasTenantAllCoursesAccess,
    FXHasTenantCourseAccess,
    IsAnonymousOrSystemStaff,
    IsSystemStaff,
)
from futurex_openedx_extensions.helpers.roles import FXViewRoleInfoMixin, get_accessible_tenant_ids
from futurex_openedx_extensions.helpers.tenants import get_all_tenants_info, get_excluded_tenant_ids, get_tenants_info

default_auth_classes = FX_VIEW_DEFAULT_AUTH_CLASSES.copy()


@docs('ExcludedTenantsView.get')
class ExcludedTenantsView(APIView):
    """View to get the list of excluded tenants"""
    authentication_classes = default_auth_classes
    permission_classes = [IsSystemStaff]

    @use_read_replica_if_available
    def get(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:  # pylint: disable=no-self-use
        """Get the list of excluded tenants"""
        return JsonResponse(get_excluded_tenant_ids())


@docs('AccessibleTenantsInfoView.get')
class AccessibleTenantsInfoView(APIView):
    """View to get the list of accessible tenants"""
    permission_classes = [IsAnonymousOrSystemStaff]

    @use_read_replica_if_available
    def get(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:  # pylint: disable=no-self-use
        """
        GET /api/fx/accessible/v1/info/?username_or_email=<usernameOrEmail>
        """
        username_or_email = request.query_params.get('username_or_email')
        try:
            user = get_user_by_username_or_email(username_or_email)
        except ObjectDoesNotExist:
            user = None

        if not user:
            return JsonResponse({})

        tenant_ids = get_accessible_tenant_ids(user)
        return JsonResponse(get_tenants_info(tenant_ids))


@docs('AccessibleTenantsInfoViewV2.get')
class AccessibleTenantsInfoViewV2(FXViewRoleInfoMixin, APIView):
    """View to get the list of accessible tenants version 2"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    fx_view_name = 'accessible_info'
    fx_view_description = 'api/fx/accessible/v2/info/: Get accessible tenants'

    @use_read_replica_if_available
    def get(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:  # pylint: disable=no-self-use
        """
        GET /api/fx/accessible/v1/info/?username_or_email=<usernameOrEmail>
        """
        username_or_email = request.query_params.get('username_or_email')
        try:
            user = get_user_by_username_or_email(username_or_email)
        except ObjectDoesNotExist:
            user = None

        if not user:
            return JsonResponse({})

        tenant_ids = get_accessible_tenant_ids(user)
        return JsonResponse(get_tenants_info(tenant_ids))


@docs('VersionInfoView.get')
class VersionInfoView(APIView):
    """View to get the version information"""
    permission_classes = [IsSystemStaff]

    @use_read_replica_if_available
    def get(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:  # pylint: disable=no-self-use
        """
        GET /api/fx/version/v1/info/
        """
        import futurex_openedx_extensions  # pylint: disable=import-outside-toplevel
        return JsonResponse({
            'version': futurex_openedx_extensions.__version__,
        })


@docs('TenantAssetsManagementView.create')
@docs('TenantAssetsManagementView.list')
@exclude_schema_for('retrieve', 'update', 'partial_update', 'destroy')
class TenantAssetsManagementView(FXViewRoleInfoMixin, viewsets.ModelViewSet):  # pylint: disable=too-many-ancestors
    """View to list and retrieve course assets."""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    serializer_class = serializers.TenantAssetSerializer
    pagination_class = DefaultPagination
    fx_view_name = 'tenant_assets'
    fx_default_read_write_roles = ['staff', 'fx_api_access_global']
    fx_default_read_only_roles = ['staff', 'fx_api_access_global']
    fx_allowed_write_methods = ['POST']
    fx_view_description = 'api/fx/tenant/v1/assets/: Tenant Assets Management APIs.'
    filter_backends = [DefaultOrderingFilter, DjangoFilterBackend, DefaultSearchFilter]
    filterset_fields = ['tenant_id', 'updated_by']
    ordering = ['-id']
    search_fields = ['slug']

    parser_classes = [MultiPartParser]

    def get_queryset(self) -> QuerySet:
        """Get the list of user uploaded files."""
        is_staff_user = self.request.fx_permission_info['is_system_staff_user']
        accessible_tenant_ids = self.request.fx_permission_info['view_allowed_tenant_ids_full_access']
        if is_staff_user:
            template_tenant_id = get_all_tenants_info()['template_tenant']['tenant_id']
            if template_tenant_id:
                accessible_tenant_ids.append(template_tenant_id)

        result = TenantAsset.objects.filter(tenant__id__in=accessible_tenant_ids)
        if not is_staff_user:
            result = result.exclude(slug__startswith='_')

        return result
