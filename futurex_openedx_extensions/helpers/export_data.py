"""
This module contains a mixin for exporting data to CSV format and related helpers.
"""
import copy
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from eox_tenant.models import TenantConfig
from rest_framework import status as http_status
from rest_framework.generics import ListAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from futurex_openedx_extensions.helpers.models import DataExportTask
from futurex_openedx_extensions.helpers.tasks import export_data_to_csv_task

User = get_user_model()


class ExportCSVMixin(ListAPIView):
    """
    Mixin for exporting data to CSV format.
    """
    @property
    def filename(self) -> str:
        """Get the generated file name with the current timestamp including microseconds"""
        current_time = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        return f'{self.fx_view_name}_{current_time}.csv'

    def build_download_url(self, file: str) -> str:
        """Return download url from given file"""
        if file:
            return self.request.build_absolute_uri(f'/media/{file}')
        return ''

    def get_view_request_url(self, query_params: dict) -> str:
        """Create url from current request with given query params"""
        query_string = urlencode(query_params)
        full_url = f'{self.request.scheme}://{self.request.get_host()}{self.request.path}'
        if query_string:
            full_url += f'?{query_string}'
        return full_url

    def get_filtered_query_params(self) -> dict:
        """Filter query params - to avoid infinite requests loop"""
        query_params = self.request.GET.copy()
        query_params.pop('download', None)
        query_params.pop('page_size', None)
        query_params.pop('page', None)
        return query_params

    def get_serialized_fx_permission_info(self) -> dict:
        """get serialized fx_permission info for task"""
        fx_permission_info = copy.deepcopy(self.request.fx_permission_info)
        user = fx_permission_info.get('user')
        fx_permission_info.update({
            'user': None,
            'user_id': user.id
        })
        return fx_permission_info

    def generate_csv_url_response(self) -> dict:
        """Return response with csv file url"""
        filtered_query_params = self.get_filtered_query_params()
        view_url = self.get_view_request_url(filtered_query_params)
        fx_permission_info = self.get_serialized_fx_permission_info()
        view_data = {
            'query_params': filtered_query_params,
            'kwargs': self.kwargs,
            'path': self.request.path,
        }
        exported_filename = self.filename
        tenant = TenantConfig.objects.get(
            id=self.request.fx_permission_info['view_allowed_tenant_ids_any_access'][0]
        )
        fx_task = DataExportTask.objects.create(
            filename=exported_filename,
            view_name=self.__class__.fx_view_name,
            user=self.request.user,
            tenant_id=tenant.id
        )
        export_data_to_csv_task.delay(fx_task.id, view_url, view_data, fx_permission_info, exported_filename)
        return {'success': f'Task innititated successfully with id: {fx_task.id}'}

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Override the list method to generate CSV and return JSON response with CSV URL"""
        if self.request.query_params.get('download') == 'csv':
            permitted_tenant_ids = self.request.fx_permission_info['view_allowed_tenant_ids_any_access']
            if len(permitted_tenant_ids) > 1:
                raise NotImplementedError(
                    f'Download CSV functionality is not implemented for multiple tenants: {permitted_tenant_ids}'
                )
            if len(permitted_tenant_ids) == 0:
                return Response(
                    {'detail': 'Missing tenant access'},
                    status=http_status.HTTP_403_FORBIDDEN
                )
            response = self.generate_csv_url_response()
            return Response(response, status=http_status.HTTP_200_OK)
        return super().list(request, args, kwargs)
