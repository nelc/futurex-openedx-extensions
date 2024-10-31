"""
This module contains a mixin for exporting data to CSV format and related helpers.
"""
import copy
from datetime import datetime
from typing import Any

from django.contrib.auth import get_user_model
from rest_framework import status as http_status
from rest_framework.request import Request
from rest_framework.response import Response

from futurex_openedx_extensions.helpers.models import DataExportTask
from futurex_openedx_extensions.helpers.tasks import export_data_to_csv_task

User = get_user_model()


class ExportCSVMixin:
    """
    Mixin for exporting data to CSV format.
    """
    @property
    def export_filename(self) -> str:
        """Get the generated file name with the current timestamp including microseconds"""
        current_time = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        return f'{self.fx_view_name}_{current_time}.csv'  # type: ignore[attr-defined]

    def get_view_request_url(self) -> str:
        """Create url from current request with given query params"""
        return f'{self.request.scheme}://{self.request.get_host()}{self.request.path}'  # type: ignore[attr-defined]

    def get_filtered_query_params(self) -> dict:
        """Filter query params - to avoid infinite requests loop"""
        query_params = self.request.GET.copy()  # type: ignore[attr-defined]
        query_params.pop('download', None)
        query_params.pop('page_size', None)
        query_params.pop('page', None)
        return query_params

    def get_serialized_fx_permission_info(self) -> dict:
        """get serialized fx_permission info for task"""
        fx_permission_info = copy.deepcopy(self.request.fx_permission_info)  # type: ignore[attr-defined]
        user = fx_permission_info.get('user')
        fx_permission_info.update({
            'user': None,
            'user_id': user.id
        })
        return fx_permission_info

    def generate_csv_url_response(self) -> dict:
        """Return response with csv file url"""
        filtered_query_params = self.get_filtered_query_params()
        view_url = self.get_view_request_url()
        fx_permission_info = self.get_serialized_fx_permission_info()
        view_data = {
            'query_params': filtered_query_params,
            'kwargs': self.kwargs,  # type: ignore[attr-defined]
            'path': self.request.path,  # type: ignore[attr-defined]
        }
        exported_filename = self.export_filename
        fx_task = DataExportTask.objects.create(
            filename=exported_filename,
            view_name=self.__class__.fx_view_name,  # type: ignore[attr-defined]
            user=self.request.user,  # type: ignore[attr-defined]
            tenant_id=self.request.fx_permission_info[  # type: ignore[attr-defined]
                'view_allowed_tenant_ids_any_access'
            ][0],
        )
        export_data_to_csv_task.delay(fx_task.id, view_url, view_data, fx_permission_info, exported_filename)
        return {'success': f'Task initiated successfully with id: {fx_task.id}'}

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Override the list method to generate CSV and return JSON response with CSV URL"""
        if self.request.query_params.get('download', '').lower() == 'csv':  # type: ignore[attr-defined]
            permitted_tenant_ids = self.request.fx_permission_info[  # type: ignore[attr-defined]
                'view_allowed_tenant_ids_any_access'
            ]
            if len(permitted_tenant_ids) > 1:
                return Response(
                    {'detail': 'Download CSV functionality is not implemented for multiple tenants!'},
                    status=http_status.HTTP_400_BAD_REQUEST,
                )
            if len(permitted_tenant_ids) == 0:
                return Response(
                    {'detail': 'Missing tenant access'},
                    status=http_status.HTTP_403_FORBIDDEN
                )
            response = self.generate_csv_url_response()
            return Response(response, status=http_status.HTTP_200_OK)
        return super().list(request, args, kwargs)  # type: ignore
