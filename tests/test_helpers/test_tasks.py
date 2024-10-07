"""Tests for Fx Helpers tasks"""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from futurex_openedx_extensions.helpers.models import DataExportTask
from futurex_openedx_extensions.helpers.tasks import export_data_to_csv_task


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.tasks.export_data_to_csv')
def test_export_data_to_csv_task(mocked_export_data_to_csv):
    """test export_data_to_csv_task functionality"""
    filename = 'test_file.csv'
    fx_task = DataExportTask.objects.create(filename=filename, status=DataExportTask.STATUS_PENDING)
    url = 'http://example.com/view'
    view_data = {'query_params': {}, 'kwargs': {}, 'path': '/test/path'}
    user = get_user_model().objects.create_user(username='testuser', password='password')
    fx_permission_info = {'user': user.id}
    mocked_export_data_to_csv.return_value = filename
    export_data_to_csv_task(fx_task.id, url, view_data, fx_permission_info, filename)
    mocked_export_data_to_csv.assert_called_once_with(url, view_data, fx_permission_info, filename)
    fx_task.refresh_from_db()
    assert fx_task.status == DataExportTask.STATUS_COMPLETED
