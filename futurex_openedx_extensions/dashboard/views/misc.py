"""Views for the dashboard app - misc feature"""
# pylint: disable=duplicate-code

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from django.db.models.query import QuerySet
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django_filters.rest_framework import DjangoFilterBackend
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from futurex_openedx_extensions.dashboard import serializers
from futurex_openedx_extensions.dashboard.docs_utils import docs
from futurex_openedx_extensions.dashboard.views.routers import use_read_replica_if_available
from futurex_openedx_extensions.helpers.constants import (
    ALLOWED_FILE_EXTENSIONS,
    CONFIG_FILES_UPLOAD_DIR,
    COURSE_ACCESS_ROLES_SUPPORTED_READ,
    FX_VIEW_DEFAULT_AUTH_CLASSES,
)
from futurex_openedx_extensions.helpers.converters import error_details_to_dictionary
from futurex_openedx_extensions.helpers.filters import DefaultOrderingFilter, DefaultSearchFilter
from futurex_openedx_extensions.helpers.models import DataExportTask
from futurex_openedx_extensions.helpers.pagination import DefaultPagination
from futurex_openedx_extensions.helpers.permissions import FXHasTenantAllCoursesAccess, FXHasTenantCourseAccess
from futurex_openedx_extensions.helpers.roles import FXViewRoleInfoMixin
from futurex_openedx_extensions.helpers.tenants import get_all_tenants_info
from futurex_openedx_extensions.helpers.upload import get_storage_dir, upload_file

default_auth_classes = FX_VIEW_DEFAULT_AUTH_CLASSES.copy()
logger = logging.getLogger(__name__)


@docs('DataExportManagementView.list')
@docs('DataExportManagementView.partial_update')
@docs('DataExportManagementView.retrieve')
class DataExportManagementView(FXViewRoleInfoMixin, viewsets.ModelViewSet):  # pylint: disable=too-many-ancestors
    """View to list and retrieve data export tasks."""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    serializer_class = serializers.DataExportTaskSerializer
    pagination_class = DefaultPagination
    fx_view_name = 'exported_files_data'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_default_read_write_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_allowed_write_methods = ['PATCH']
    fx_view_description = 'api/fx/export/v1/tasks/: Data Export Task Management APIs.'
    http_method_names = ['get', 'patch']
    filter_backends = [DjangoFilterBackend, DefaultOrderingFilter, DefaultSearchFilter]
    filterset_fields = ['related_id', 'view_name']
    ordering = ['-id']
    search_fields = ['filename', 'notes']

    def get_queryset(self) -> QuerySet:
        """Get the list of user tasks."""
        return DataExportTask.objects.filter(
            user=self.request.user,
            tenant__id__in=self.fx_permission_info['view_allowed_tenant_ids_any_access']
        )

    def get_object(self) -> DataExportTask:
        """Override to ensure that the user can only retrieve their own tasks."""
        task_id = self.kwargs.get('pk')  # Use 'pk' for the default lookup
        task = get_object_or_404(DataExportTask, id=task_id, user=self.request.user)
        return task


@docs('TenantInfoView.get')
class TenantInfoView(FXViewRoleInfoMixin, APIView):
    """View to get the list of excluded tenants"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    fx_view_name = 'tenant_info'
    fx_default_read_only_roles = COURSE_ACCESS_ROLES_SUPPORTED_READ.copy()
    fx_view_description = 'api/fx/tenants/v1/info/<tenant_id>/: tenant basic information'

    @use_read_replica_if_available
    def get(
        self, request: Any, tenant_id: str, *args: Any, **kwargs: Any,
    ) -> JsonResponse | Response:
        """Get the tenant's information by tenant ID"""
        if int(tenant_id) not in self.request.fx_permission_info['view_allowed_tenant_ids_any_access']:
            return Response(
                error_details_to_dictionary(reason='You do not have access to this tenant'),
                status=http_status.HTTP_403_FORBIDDEN,
            )

        result = {'tenant_id': int(tenant_id)}
        result.update(get_all_tenants_info()['info'].get(int(tenant_id)))
        return JsonResponse(result)


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


class SetThemePreviewCookieView(APIView):
    """View to set theme preview cookie"""
    def get(self, request: Any) -> Any:  # pylint: disable=no-self-use
        """Set theme preview cookie"""
        next_url = request.GET.get('next', request.build_absolute_uri())
        if request.COOKIES.get('theme-preview') == 'yes':
            return redirect(next_url)

        return render(request, template_name='set_theme_preview.html', context={'next_url': next_url})
