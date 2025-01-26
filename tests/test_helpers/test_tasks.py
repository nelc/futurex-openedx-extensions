"""Tests for Fx Helpers tasks"""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.models import DataExportTask
from futurex_openedx_extensions.helpers.tasks import export_data_to_csv_task


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.tasks.export_data_to_csv')
def test_export_data_to_csv_task(mocked_export_data_to_csv, base_data):  # pylint: disable=unused-argument
    """test export_data_to_csv_task functionality"""
    filename = 'test_file.csv'
    url = 'http://example.com/view'
    view_data = {'query_params': {}, 'kwargs': {}, 'path': '/test/path'}
    user = get_user_model().objects.create_user(username='testuser', password='password')
    fx_task = DataExportTask.objects.create(
        filename=filename,
        view_name='fake',
        user=user,
        tenant_id=1,
    )
    fx_permission_info = {'user_id': user.id, 'role': 'admin'}
    assert fx_task.status == DataExportTask.STATUS_IN_QUEUE

    mocked_export_data_to_csv.side_effect = lambda *args, **kwargs: DataExportTask.objects.filter(
        id=args[0]
    ).update(status=DataExportTask.STATUS_PROCESSING)
    export_data_to_csv_task(fx_task.id, url, view_data, fx_permission_info, filename)
    mocked_export_data_to_csv.assert_called_once_with(fx_task.id, url, view_data, fx_permission_info, filename)
    fx_task.refresh_from_db()
    assert fx_task.status == DataExportTask.STATUS_COMPLETED


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.models.DataExportTask.get_task')
def test_export_data_to_csv_task_error_invalid_task(mock_get_task, caplog):
    """Verify that there is an error logged when the task is invalid"""
    exc_value = FXExceptionCodes.EXPORT_CSV_TASK_NOT_FOUND.value
    mock_get_task.side_effect = FXCodedException(
        code=exc_value, message='Testing Task not found',
    )
    with pytest.raises(FXCodedException) as exc_info:
        export_data_to_csv_task('whatever', 'whatever', 'whatever', 'whatever', 'whatever')
    assert exc_info.value.code == exc_value
    assert str(exc_info.value) == str(mock_get_task.side_effect)
    assert f'CSV Export Error: ({exc_value}) {str(mock_get_task.side_effect)}' in caplog.text


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.models.DataExportTask.set_status')
@patch('futurex_openedx_extensions.helpers.models.DataExportTask.get_task')
def test_export_data_to_csv_task_error_handled(mock_get_task, mock_set_status, caplog):
    """Verify that there is an error logged when a handled exception occurs"""
    task_id = 999
    exc_value = FXExceptionCodes.UNKNOWN_ERROR.value  # Any value other than EXPORT_CSV_TASK_NOT_FOUND
    mock_get_task.side_effect = FXCodedException(
        code=exc_value, message='Testing handled error',
    )
    with pytest.raises(FXCodedException) as exc_info:
        export_data_to_csv_task(task_id, 'whatever', 'whatever', 'whatever', 'whatever')
    assert exc_info.value.code == exc_value
    assert str(exc_info.value) == str(mock_get_task.side_effect)
    assert f'CSV Export Error for task {task_id}: ({exc_value}) {str(mock_get_task.side_effect)}' in caplog.text

    mock_set_status.assert_called_once_with(
        task_id=task_id, status=DataExportTask.STATUS_FAILED, error_message=str(mock_get_task.side_effect)
    )


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.models.DataExportTask.set_status')
@patch('futurex_openedx_extensions.helpers.models.DataExportTask.get_task')
def test_export_data_to_csv_task_error_unhandled(mock_get_task, mock_set_status, caplog):
    """Verify that there is an error logged when an unhandled exception occurs"""
    task_id = 999
    mock_get_task.side_effect = Exception('Testing unhandled error')
    with pytest.raises(Exception) as exc_info:
        export_data_to_csv_task(task_id, 'whatever', 'whatever', 'whatever', 'whatever')
    assert str(exc_info.value) == str(mock_get_task.side_effect)
    assert f'CSV Export Unhandled Error for task {task_id}: (Exception) {str(mock_get_task.side_effect)}' in caplog.text

    mock_set_status.assert_called_once_with(
        task_id=task_id, status=DataExportTask.STATUS_FAILED, error_message=str(mock_get_task.side_effect)
    )
