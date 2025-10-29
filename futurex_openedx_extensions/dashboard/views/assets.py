"""Assets views for the dashboard app"""
from __future__ import annotations

import os
import uuid
from typing import Any

from django.db.models.query import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from drf_yasg.utils import swagger_auto_schema
from edx_api_doc_tools import exclude_schema_for
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from futurex_openedx_extensions.dashboard import serializers
from futurex_openedx_extensions.dashboard.docs_utils import docs
from futurex_openedx_extensions.helpers.constants import (
    ALLOWED_FILE_EXTENSIONS,
    CONFIG_FILES_UPLOAD_DIR,
    FX_VIEW_DEFAULT_AUTH_CLASSES,
)
from futurex_openedx_extensions.helpers.converters import error_details_to_dictionary
from futurex_openedx_extensions.helpers.filters import DefaultOrderingFilter, DefaultSearchFilter
from futurex_openedx_extensions.helpers.models import TenantAsset
from futurex_openedx_extensions.helpers.pagination import DefaultPagination
from futurex_openedx_extensions.helpers.permissions import FXHasTenantAllCoursesAccess
from futurex_openedx_extensions.helpers.roles import FXViewRoleInfoMixin
from futurex_openedx_extensions.helpers.tenants import get_all_tenants_info
from futurex_openedx_extensions.helpers.upload import get_storage_dir, upload_file

default_auth_classes = FX_VIEW_DEFAULT_AUTH_CLASSES.copy()


class FileUploadView(FXViewRoleInfoMixin, APIView):
    """View to upload file"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'upload_file'
    fx_view_description = 'api/fx/file/v1/upload/: Upload file'
    fx_default_read_write_roles = ['staff', 'fx_api_access_global']
    fx_default_read_only_roles = ['staff', 'fx_api_access_global']

    parser_classes = [MultiPartParser]

    @swagger_auto_schema(
        request_body=serializers.FileUploadSerializer,
    )
    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """
        POST /api/fx/file/v1/upload/

        Validates the payload, saves the file, and returns the file URL.
        """
        serializer = serializers.FileUploadSerializer(data=request.data, context={'request': self.request})

        if not serializer.is_valid():
            return Response(serializer.errors, status=http_status.HTTP_400_BAD_REQUEST)

        file = serializer.validated_data['file']
        slug = serializer.validated_data['slug']
        tenant_id = serializer.validated_data['tenant_id']

        file_extension = os.path.splitext(file.name)[1]
        if file_extension.lower() not in ALLOWED_FILE_EXTENSIONS:
            return Response(
                error_details_to_dictionary(
                    reason=f'Invalid file type. Allowed types are {ALLOWED_FILE_EXTENSIONS}.'
                ),
                status=http_status.HTTP_400_BAD_REQUEST
            )
        short_uuid = uuid.uuid4().hex[:8]
        file_name = f'{slug}-{short_uuid}{file_extension}'
        storage_path = os.path.join(get_storage_dir(tenant_id, CONFIG_FILES_UPLOAD_DIR), file_name)
        return Response(
            {'url': upload_file(storage_path, file), 'uuid': short_uuid},
            status=http_status.HTTP_201_CREATED
        )


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
