"""Test export csv"""
import csv
import logging
import os
import tempfile
from unittest.mock import MagicMock, mock_open, patch

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.test import override_settings
from storages.backends.s3boto3 import S3Boto3Storage

from futurex_openedx_extensions.helpers.exceptions import FXCodedException
from futurex_openedx_extensions.helpers.export_csv import (
    _combine_partial_files,
    _generate_csv_with_tracked_progress,
    _get_mocked_request,
    _get_response_data,
    _get_storage_dir,
    _get_user,
    _get_view_class_instance,
    _paginated_response_generator,
    _upload_file_to_storage,
    export_data_to_csv,
    generate_file_url,
    get_exported_file_url,
)
from futurex_openedx_extensions.helpers.models import DataExportTask

_FILENAME = 'test.csv'


@pytest.fixture
def fx_task():
    """Fixture for DataExportTask."""
    return DataExportTask.objects.create(
        filename=_FILENAME,
        view_name='fake',
        user_id=30,
        tenant_id=1,
    )


@pytest.mark.django_db
@pytest.mark.parametrize('user_id', [
    ('0'),
    (0),
    ('INVALID'),
    (None)
])
def test_export_data_to_csv_invalid_user(
    fx_task, user_id, base_data,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Test export_data_to_csv with invalid user id."""
    with pytest.raises(FXCodedException) as exc_info:
        export_data_to_csv(fx_task.id, 'url', {}, {'user_id': user_id}, 'test_filename')
    assert str(exc_info.value) == f'CSV Export: Invalid user id: {user_id}'


@pytest.mark.django_db
def test_get_user_valid_id():
    """Test _get_user with a valid user_id."""
    assert _get_user(30) == get_user_model().objects.get(id=30)


def test_get_view_class_instance():
    """Test _get_view_class_instance with a valid path."""
    with patch('futurex_openedx_extensions.helpers.export_csv.resolve') as mocked_resolve:
        mocked_resolve.return_value.func = 'abc'
        assert _get_view_class_instance('/api/path') == 'abc'


@pytest.mark.django_db
@pytest.mark.parametrize('path', [
    (''),
    (None),
])
def test_export_data_to_csv_invalid_path(path, base_data):  # pylint: disable=unused-argument
    """Test export_data_to_csv with invalid user id."""
    with pytest.raises(FXCodedException) as exc_info:
        _get_view_class_instance(path)
    assert str(exc_info.value) == f'CSV Export: Missing required params "path" {path}'


@pytest.mark.django_db
@override_settings(ALLOWED_HOSTS=['test-url.somthing'])
def test_get_mocked_request(base_data):  # pylint: disable=unused-argument
    """Test _get_mocked_request creates a mocked request properly."""
    user = get_user_model().objects.get(id=30)
    fx_info = {'role': 'admin', 'user': user}
    url = 'http://test-url.somthing/?test=123'
    request = _get_mocked_request(url, fx_info)
    assert request.method == 'GET'
    assert request.user == user
    assert request.fx_permission_info == fx_info


@pytest.mark.django_db
def test_get_mocked_request_invalid_url(base_data):  # pylint: disable=unused-argument
    """Test _get_mocked_request creates a mocked request properly."""
    fx_info = {'role': 'admin', 'user': get_user_model().objects.get(id=30)}
    url = '/test-url/?test=123'
    with pytest.raises(FXCodedException) as exc_info:
        _get_mocked_request(url, fx_info)
    assert str(exc_info.value) == f'CSV Export: invalid URL used when mocking the request: {url}'
    assert exc_info.value.code == 6007


def test_get_response_data_success():
    """Test _get_response_data with a successful mocked request."""
    expected_data = {'count': 1, 'results': [{'id': 1, 'name': 'Test'}]}
    response = MagicMock()
    response.data = expected_data
    response.status_code = 200
    data, count = _get_response_data(response)
    assert data == expected_data['results']
    assert count == 1


@pytest.mark.parametrize('status_code, data, exception_msg', [
    (400, {}, 'CSV Export: View returned status code: 400'),
    (200, {}, 'CSV Export: Unable to process view response.'),
    (200, {'other_than_results': []}, 'CSV Export: The "results" key is missing or is not a list.'),
    (200, {'results': 'not list'}, 'CSV Export: The "results" key is missing or is not a list.'),
    (200, {'results': []}, 'CSV Export: The "count" key is missing or is not an int.'),
    (200, {'results': [], 'count': 'not int'}, 'CSV Export: The "count" key is missing or is not an int.'),
])
def test_get_response_data_failure(
    status_code, data, exception_msg
):
    """Test _get_response_data with failure of response or unexpected response"""
    response = MagicMock()
    response.data = data
    response.status_code = status_code
    with pytest.raises(FXCodedException) as exc_info:
        _get_response_data(response)
    assert str(exc_info.value) == exception_msg


@pytest.mark.django_db
@override_settings(ALLOWED_HOSTS=['example.com'])
@patch('futurex_openedx_extensions.helpers.export_csv._get_response_data')
def test_paginated_response_generator(mock_get_response_data, view_data):
    """Test _paginated_response_generator"""
    url = 'http://example.com/api/data'
    fx_info = {'role': 'admin', 'user': get_user_model().objects.get(id=30)}
    view_data['url'] = f'{url}?test=value'
    mocked_response_1 = MagicMock()
    mocked_response_1.status_code = 200
    mocked_response_1.data = {
        'next': f'{url}?test=value&page_size={view_data["page_size"]}&page=2',
        'results': [{'id': 1}, {'id': 2}],
        'count': 3
    }
    mocked_response_2 = MagicMock()
    mocked_response_2.status_code = 200
    mocked_response_2.data = {
        'count': 3,
        'next': None,
        'results': [{'id': 3}]
    }
    mock_get_response_data.side_effect = [
        (mocked_response_1.data['results'], 3),
        (mocked_response_2.data['results'], 3),
        (mocked_response_2.data['results'], 3),  # for the long running process check
    ]
    view_instance = MagicMock()
    view_instance.side_effect = [
        mocked_response_1,
        mocked_response_2,
        mocked_response_2,  # for the long running process check
    ]

    results = list(_paginated_response_generator(fx_info, view_data, view_instance))
    assert len(results) == 2
    assert results[0] == ([{'id': 1}, {'id': 2}], 0.67, 2)
    assert results[1] == ([{'id': 3}], 1.0, 3)

    view_instance.assert_called()
    assert view_instance.call_count == 2
    assert view_data['end_page'] is None

    with patch('futurex_openedx_extensions.helpers.export_csv._is_long_running_process', return_value=True):
        list(_paginated_response_generator(fx_info, view_data, view_instance))
        assert view_data['end_page'] is not None


@pytest.mark.django_db
@override_settings(ALLOWED_HOSTS=['example.com'])
@patch('futurex_openedx_extensions.helpers.export_csv._get_response_data')
def test_paginated_response_generator_for_empty_response_data(
    mock_get_response_data, base_data, view_data,
):  # pylint: disable=unused-argument
    """Test _paginated_response_generator for empty response when there are no records"""
    fx_info = {'role': 'admin', 'user': get_user_model().objects.get(id=30)}
    mocked_response = MagicMock()
    mocked_response.status_code = 200
    mocked_response.data = {'count': 0, 'next': None, 'results': []}
    mock_get_response_data.return_value = ([], 0)
    view_instance = MagicMock(return_value=mocked_response)
    generator = _paginated_response_generator(fx_info, view_data, view_instance)
    expected_data = []
    expected_progress = 0
    expected_processed_records = 0
    results = list(generator)
    assert len(results) == 1
    assert results[0] == (expected_data, expected_progress, expected_processed_records)
    view_instance.assert_called_once()


def test_get_storage_dir():
    """Return storgae dir"""
    tenant_id = 1
    expected = os.path.join(settings.FX_DASHBOARD_STORAGE_DIR, f'{str(tenant_id)}/exported_files')
    result = _get_storage_dir(str(tenant_id))
    assert result == expected


@pytest.mark.parametrize('partial', [True, False])
def test_upload_file_to_storage(partial):
    """Test uploading a file to the default storage."""
    dummy_content = b'Test content'
    # create dummy temp file
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(dummy_content)
        temp_file_path = temp_file.name
    fake_tenant = 'fake'
    storage_path = f'{settings.FX_DASHBOARD_STORAGE_DIR}/{fake_tenant}/exported_files/{_FILENAME}'
    if partial:
        storage_path = f'{storage_path}_parts/{_FILENAME}_000001'
    result = _upload_file_to_storage(temp_file_path, _FILENAME, fake_tenant, partial_tag=1 if partial else 0)
    assert result == storage_path
    # verify file created on default storage with right content
    with default_storage.open(storage_path, 'rb') as storage_file:
        uploaded_content = storage_file.read()
        assert uploaded_content == dummy_content
    os.remove(temp_file_path)
    default_storage.delete(storage_path)
    if partial:
        os.rmdir(f'{settings.FX_DASHBOARD_STORAGE_DIR}/{fake_tenant}/exported_files/{_FILENAME}_parts')
    os.rmdir(f'{settings.FX_DASHBOARD_STORAGE_DIR}/{fake_tenant}/exported_files')
    os.rmdir(f'{settings.FX_DASHBOARD_STORAGE_DIR}/{fake_tenant}')
    os.rmdir(settings.FX_DASHBOARD_STORAGE_DIR)


@patch('futurex_openedx_extensions.helpers.export_csv.default_storage')
@patch('futurex_openedx_extensions.helpers.export_csv._get_storage_dir')
def test_upload_file_to_storage_set_private(mock_get_storage_dir, mock_storage):  # pylint: disable=redefined-outer-name
    """Verify that the uploaded file is set to private when the storage type is S3Boto3Storage."""
    mock_get_storage_dir.return_value = 'fake_exported_files'
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b'Test content')
        temp_file_path = temp_file.name

    storage_path = f'{mock_get_storage_dir.return_value}/{_FILENAME}'
    mock_put = MagicMock()
    mock_object = MagicMock(Acl=MagicMock(return_value=MagicMock(put=mock_put)))
    mock_storage.bucket.Object.return_value = mock_object

    _upload_file_to_storage(temp_file_path, _FILENAME, 99)
    mock_storage.bucket.Object.assert_not_called()
    mock_put.assert_not_called()

    mock_storage.__class__ = S3Boto3Storage
    _upload_file_to_storage(temp_file_path, _FILENAME, 99)
    mock_storage.bucket.Object.assert_called_once_with(storage_path)
    mock_put.assert_called_once_with(ACL='private')


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.export_csv._paginated_response_generator')
@patch('futurex_openedx_extensions.helpers.models.DataExportTask.get_task')
@pytest.mark.parametrize('last_percentage, case_description', [
    (0.99, 'last percentage could be less than %100 if some records were dropped from the view during the export'),
    (1.0, 'mostly, last percentage will be %100'),
    (1.01, 'we allow the possibility of %1 records added to the view during the export'),
])
def test_generate_csv_with_tracked_progress(
    mock_get_task, mock_generator, last_percentage, case_description, base_data, view_data,
):  # pylint: disable=unused-argument, too-many-arguments
    """Test _generate_csv_with_tracked_progress."""
    tenant = MagicMock(id=1)
    task = MagicMock()
    task.tenant = tenant
    task.status = DataExportTask.STATUS_PROCESSING
    mock_get_task.return_value = task

    storage_dir = f'{settings.FX_DASHBOARD_STORAGE_DIR}/{str(tenant.id)}/exported_files'
    fake_storage_path = f'{storage_dir}/{_FILENAME}'
    fx_permission_info = {'user': get_user_model().objects.get(id=30), 'role': 'admin'}
    mock_generator.return_value = iter([
        ([{'id': 1}, {'id': 2}], 0.67, 2),
        ([{'id': 3}], last_percentage, 3)
    ])
    assert _generate_csv_with_tracked_progress(
        task, fx_permission_info, view_data, _FILENAME, MagicMock()
    )
    task.save.assert_called()
    assert task.save.call_count == 2
    assert task.progress == 1.0, 'Test case failed! progress must be %100 when the task is finished, regardless of' \
        ' the value of last_percentage. Failed case: ' + case_description
    with open(fake_storage_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 3
        assert rows[0] == {'id': '1'}
        assert rows[1] == {'id': '2'}
        assert rows[2] == {'id': '3'}

    default_storage.delete(fake_storage_path)
    os.rmdir(storage_dir)
    os.rmdir(f'{settings.FX_DASHBOARD_STORAGE_DIR}/{str(tenant.id)}')
    os.rmdir(settings.FX_DASHBOARD_STORAGE_DIR)


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.export_csv._upload_file_to_storage')
@patch('futurex_openedx_extensions.helpers.export_csv._paginated_response_generator')
@patch('futurex_openedx_extensions.helpers.export_csv.os.remove')
def test_generate_csv_with_tracked_progress_for_exception(
    mock_os_remove, mock_generator, mock_file_upload, base_data,
):  # pylint: disable=unused-argument
    """Test _generate_csv_with_tracked_progress for exception."""
    task = MagicMock()
    fx_permission_info = {'user': get_user_model().objects.get(id=30), 'role': 'admin'}
    view_data = {
        'page_size': 2,
        'url': 'http://example.com',
        'kwargs': {}
    }
    mock_generator.side_effect = Exception('Some exception')
    with pytest.raises(Exception) as _:
        _generate_csv_with_tracked_progress(
            task, fx_permission_info, view_data, _FILENAME, MagicMock()
        )
    mock_file_upload.assert_not_called()
    mock_os_remove.assert_called_once()


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.export_csv._upload_file_to_storage')
@patch('futurex_openedx_extensions.helpers.export_csv._paginated_response_generator')
@patch('futurex_openedx_extensions.helpers.export_csv.os.remove')
@patch('futurex_openedx_extensions.helpers.models.DataExportTask.get_task')
def test_generate_csv_with_tracked_progress_for_os_removal_exception(
    mock_get_task, mock_os_remove, mock_generator, mock_file_upload, base_data, view_data,
):  # pylint: disable=unused-argument, too-many-arguments
    """Test _generate_csv_with_tracked_progress for os exception"""
    tenant = MagicMock(id=1)
    task = MagicMock()
    task.id = 99
    task.tenant_id = tenant.id
    mock_get_task.return_value = task

    fake_storage_path = f'{settings.FX_DASHBOARD_STORAGE_DIR}/{str(tenant.id)}/{_FILENAME}'
    mock_generator.return_value = iter([])
    mock_os_remove.side_effect = Exception('Some exception')
    mock_file_upload.return_value = fake_storage_path
    assert _generate_csv_with_tracked_progress(
        task_id=task.id,
        fx_permission_info={'not': 'reached in this test'},
        view_data=view_data,
        filename=_FILENAME,
        view_instance=MagicMock(),
    )


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.export_csv._paginated_response_generator')
def test_generate_csv_with_tracked_progress_for_empty_records(
    mock_generator, fx_task, base_data, view_data,
):  # pylint: disable=redefined-outer-name, unused-argument
    """_generate_csv_with_tracked_progress for empty records"""
    tenant = MagicMock(id=1)
    storage_dir = f'{settings.FX_DASHBOARD_STORAGE_DIR}/{str(tenant.id)}/exported_files'
    fake_storage_path = f'{storage_dir}/{_FILENAME}'
    fx_permission_info = {'user': get_user_model().objects.get(id=30), 'role': 'admin'}
    mock_generator.return_value = iter([([], 0, 0)])
    assert _generate_csv_with_tracked_progress(
        fx_task.id, fx_permission_info, view_data, _FILENAME, MagicMock(),
    )
    assert fx_task.progress == 0
    with open(fake_storage_path, 'r', newline='', encoding='utf-8') as f:
        assert f.read() == ''
    default_storage.delete(fake_storage_path)
    os.rmdir(storage_dir)
    os.rmdir(f'{settings.FX_DASHBOARD_STORAGE_DIR}/{str(tenant.id)}')
    os.rmdir(settings.FX_DASHBOARD_STORAGE_DIR)


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.export_csv._paginated_response_generator')
@patch('futurex_openedx_extensions.helpers.export_csv._upload_file_to_storage')
def test_generate_csv_with_tracked_progress_for_single_file_export(
    _, mock_generator, fx_task, base_data, view_data, caplog,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify that _generate_csv_with_tracked_progress works for a single file export."""
    caplog.set_level(logging.INFO)
    mock_generator.side_effect = iter([[], 0, 0])
    assert _generate_csv_with_tracked_progress(
        fx_task.id, {'dummy': 'dummy'}, view_data, _FILENAME, MagicMock(),
    )
    assert 'CSV Export: file uploaded successfully for task 1 (no partial files).' in caplog.text


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.export_csv._paginated_response_generator')
@patch('futurex_openedx_extensions.helpers.export_csv._upload_file_to_storage')
def test_generate_csv_with_tracked_progress_for_partial_export(
    _, mock_generator, fx_task, base_data, view_data, caplog,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify that _generate_csv_with_tracked_progress works for a partial export."""
    def generator_side_effect(_, sent_view_data, __):
        sent_view_data['end_page'] = 1
        yield [], 0, 0

    caplog.set_level(logging.INFO)

    mock_generator.side_effect = generator_side_effect
    assert not _generate_csv_with_tracked_progress(
        fx_task.id, {'dummy': 'dummy'}, view_data, _FILENAME, MagicMock(),
    )
    assert 'CSV Export: partial file uploaded successfully for task 1' in caplog.text
    assert view_data['start_page'] == 2
    assert view_data['end_page'] is None


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.export_csv._combine_partial_files')
@patch('futurex_openedx_extensions.helpers.export_csv._paginated_response_generator')
@patch('futurex_openedx_extensions.helpers.export_csv._upload_file_to_storage')
def test_generate_csv_with_tracked_progress_for_last_partial_export(
    _, mock_generator, combine_mock, fx_task, base_data, view_data,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify that _generate_csv_with_tracked_progress works for a last partial export."""
    mock_generator.side_effect = iter([[], 0, 0])
    view_data['start_page'] = 2
    assert _generate_csv_with_tracked_progress(
        fx_task.id, {'dummy': 'dummy'}, view_data, _FILENAME, MagicMock(),
    )
    combine_mock.assert_called_once()


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.export_csv._get_view_class_instance')
@patch('futurex_openedx_extensions.helpers.export_csv._generate_csv_with_tracked_progress')
def test_export_data_to_csv(
    mock_generate_csv, mock_get_view, fx_task, base_data, view_data,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Test _export_data_to_csv"""
    user = get_user_model().objects.get(id=30)
    mock_view_instance = MagicMock()
    mock_view_instance.view_class.pagination_class.max_page_size = 50
    mock_get_view.return_value = mock_view_instance
    url = 'http://example.com/api/data'
    fx_permission_info = {'user_id': user.id, 'role': 'admin'}
    fake_storage_path = f'{settings.FX_DASHBOARD_STORAGE_DIR}/{_FILENAME}'
    mock_generate_csv.return_value = fake_storage_path
    expected_url = f'{url}?page={view_data["start_page"]}&page_size=50'
    result = export_data_to_csv(fx_task.id, url, view_data, fx_permission_info, _FILENAME)
    assert result == fake_storage_path
    assert fx_permission_info['user'] == user
    assert view_data['url'] == expected_url
    assert view_data['page_size'] == 50
    assert view_data['view_instance'] == mock_view_instance
    mock_generate_csv.assert_called_once_with(
        fx_task.id, fx_permission_info, view_data, _FILENAME, mock_view_instance
    )
    mock_get_view.assert_called_once_with(view_data['path'])


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.export_csv._get_view_class_instance')
@patch('futurex_openedx_extensions.helpers.export_csv._generate_csv_with_tracked_progress')
def test_export_data_to_csv_for_default_page_size(
    mock_generate_csv, mock_get_view, fx_task, base_data, view_data,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Test _export_data_to_csv"""
    user = get_user_model().objects.get(id=30)
    fake_storage_path = f'{settings.FX_DASHBOARD_STORAGE_DIR}/{_FILENAME}'
    mocked_view_instance = MagicMock()
    mocked_view_instance.view_class.pagination_class.max_page_size = None
    mock_get_view.return_value = mocked_view_instance
    url = 'http://example.com/api/data'
    fx_permission_info = {'user_id': user.id, 'role': 'admin'}
    mock_generate_csv.return_value = fake_storage_path
    expected_url = f'{url}?page={view_data["start_page"]}&page_size=100'
    result = export_data_to_csv(fx_task.id, url, view_data, fx_permission_info, _FILENAME)
    assert result == fake_storage_path
    assert view_data['url'] == expected_url
    assert view_data['page_size'] == 100


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.export_csv._get_view_class_instance')
@patch('futurex_openedx_extensions.helpers.export_csv._generate_csv_with_tracked_progress')
def test_export_data_to_csv_for_missing_pagination_class(
    mock_generate_csv, mock_get_view, fx_task, base_data, view_data,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Test _export_data_to_csv"""
    user = get_user_model().objects.get(id=30)
    fake_storage_path = f'{settings.FX_DASHBOARD_STORAGE_DIR}/{_FILENAME}'
    mocked_view_instance = MagicMock()
    mocked_view_instance.view_class.pagination_class = None
    mock_get_view.return_value = mocked_view_instance
    url = 'http://example.com/api/data'
    fx_permission_info = {'user_id': user.id, 'role': 'admin'}
    mock_generate_csv.return_value = fake_storage_path
    expected_url = f'{url}?page={view_data["start_page"]}&page_size=100'
    result = export_data_to_csv(fx_task.id, url, view_data, fx_permission_info, _FILENAME)
    assert result == fake_storage_path
    assert view_data['url'] == expected_url
    assert view_data['page_size'] == 100


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.export_csv._get_view_class_instance')
@patch('futurex_openedx_extensions.helpers.export_csv._generate_csv_with_tracked_progress')
def test_export_data_to_csv_for_filename_extension(
    mock_generate_csv, mock_get_view, fx_task, base_data, view_data
):  # pylint: disable=redefined-outer-name, unused-argument
    """Test _export_data_to_csv"""
    filename = 'test'
    mock_view_instance = MagicMock()
    mock_get_view.return_value = mock_view_instance
    fx_permission_info = {'user_id': 30, 'role': 'admin'}
    mock_generate_csv.return_value = 'randome/path/test.csv'
    export_data_to_csv(fx_task.id, 'http://example.com/api', view_data, fx_permission_info, filename)
    mock_generate_csv.assert_called_once_with(
        fx_task.id, fx_permission_info, view_data, f'{filename}.csv', mock_view_instance
    )


@pytest.mark.django_db
@pytest.mark.parametrize('is_file_exist, is_task_completed, expected_return_value', [
    (True, True, 'http://example.com/exported_file.csv'),
    (False, False, None),
    (False, True, None)
])
@patch('futurex_openedx_extensions.helpers.export_csv.default_storage')
@patch('futurex_openedx_extensions.helpers.export_csv.generate_file_url')
def test_get_exported_file_url(
    mocked_generate_url, mock_storage, is_file_exist, is_task_completed, expected_return_value, base_data,
):  # pylint: disable=too-many-arguments, unused-argument
    """Test get exported file URL"""
    mock_storage.exists.return_value = is_file_exist
    mock_storage.url.return_value = 'http://example.com/exported_file.csv' if is_file_exist else None
    mocked_generate_url.return_value = expected_return_value
    task = DataExportTask.objects.create(
        tenant_id=1,
        filename='exported_file.csv',
        status=DataExportTask.STATUS_COMPLETED if is_task_completed else DataExportTask.STATUS_IN_QUEUE,
        user_id=30,
    )
    result = get_exported_file_url(task)
    assert result == expected_return_value


@pytest.mark.django_db
def test_export_data_to_csv_for_url(base_data, fx_task):  # pylint: disable=redefined-outer-name, unused-argument
    """Test _export_data_to_csv for URL"""
    url_with_query_str = 'http://example.com/api?key1=value1'
    with pytest.raises(FXCodedException) as exc_info:
        export_data_to_csv(fx_task.id, url_with_query_str, {}, {}, 'test.csv')
    assert str(exc_info.value) == f'CSV Export: Unable to process URL with query params: {url_with_query_str}'


@override_settings(
    AWS_STORAGE_BUCKET_NAME='fake-bucket',
    AWS_ACCESS_KEY_ID='fake-id',
    AWS_SECRET_ACCESS_KEY='fake-access-key'
)
@pytest.mark.parametrize('is_s3_instance, expected_return_value, usecase', [
    (True, 'http://fake-s3-url.com/signed-fake-path', 'S3 storage use case failed'),
    (False, 'http://default_storage_url/fake-path', 'Other storage use case failed'),
])
@patch('futurex_openedx_extensions.helpers.export_csv.default_storage')
@patch('futurex_openedx_extensions.helpers.export_csv.isinstance')
def test_generate_file_url_for_return_value(
    mocked_is_instance, mocked_default_storage, is_s3_instance, expected_return_value, usecase
):
    """
    test the behavior of `generate_file_url` function
    for both S3-based storage and non-S3 storage backends.

    Test cases:
    1. When the default storage is an instance of S3Boto3Storage:
       - The function should return the signed URL generated by `generate_presigned_url`.
    2. When the default storage is not an instance of S3Boto3Storage:
       - The function should return the URL provided by the `default_storage.url()` method.
    """
    dummy_file_path = 'fake-path'
    mocked_is_instance.return_value = is_s3_instance
    mocked_default_storage.url.return_value = 'http://default_storage_url/fake-path'
    assert generate_file_url(dummy_file_path) == expected_return_value, usecase


@override_settings(
    AWS_STORAGE_BUCKET_NAME='fake-bucket',
    AWS_ACCESS_KEY_ID='fake-id',
    AWS_SECRET_ACCESS_KEY='fake-access-key'
)
@patch('futurex_openedx_extensions.helpers.export_csv.isinstance', return_value=True)
@patch('boto3.client')
def test_generate_file_url_for_s3_storage(
    mocked_boto3_client, mocked_is_instance
):  # pylint: disable=unused-argument
    """
    test generate_file_url functionality for s3 storage that
    needed s3 storage fucntions are called with correct arguments
    """
    dummy_file_path = 'fake/file.csv'
    generate_file_url(dummy_file_path)
    mocked_boto3_client.assert_called_once_with(
        's3', aws_access_key_id='fake-id', aws_secret_access_key='fake-access-key'
    )
    mocked_boto3_client.return_value.generate_presigned_url.assert_called_once_with(
        'get_object',
        Params={'Bucket': 'fake-bucket', 'Key': dummy_file_path},
        HttpMethod='GET',
        ExpiresIn=3600
    )


@pytest.fixture
def mock_default_storage():
    """Fixture for default storage."""
    with patch('futurex_openedx_extensions.helpers.export_csv.default_storage') as mock_storage:
        yield mock_storage


@pytest.fixture
def mock_upload_file_to_storage():
    """Fixture for upload file to storage."""
    with patch('futurex_openedx_extensions.helpers.export_csv._upload_file_to_storage') as mock_upload:
        yield mock_upload


@pytest.fixture
def mock_get_storage_dir():
    """Fixture for get storage dir."""
    with patch('futurex_openedx_extensions.helpers.export_csv._get_storage_dir') as mock_storage_dir:
        yield mock_storage_dir


@pytest.fixture
def mock_data_export_task():
    """Fixture for data export task."""
    with patch('futurex_openedx_extensions.helpers.export_csv.DataExportTask.get_task') as mock_get_task:
        mock_task = MagicMock()
        mock_task.tenant.id = 123
        mock_get_task.return_value = mock_task
        yield mock_get_task


@patch('futurex_openedx_extensions.helpers.export_csv.os.remove')
@pytest.mark.parametrize('os_rm_failure', [True, False])
def test_combine_partial_files_success(
    mock_os_remove,
    os_rm_failure,
    mock_default_storage,
    mock_get_storage_dir,
    mock_upload_file_to_storage,
    mock_data_export_task,
    caplog,
):  # pylint: disable=too-many-arguments, redefined-outer-name, unused-argument
    """Verify the outcome of _combine_partial_files."""
    caplog.set_level(logging.INFO)

    mock_get_storage_dir.return_value = '/mock/storage/dir'
    mock_default_storage.listdir.return_value = ([], ['part1.csv', 'part2.csv'])
    mock_open_file = mock_open(read_data='file1_content')
    mock_open_file.return_value.read.side_effect = [b'file1_content', b'file2_content']
    mock_default_storage.open.side_effect = mock_open_file

    if os_rm_failure:
        mock_os_remove.side_effect = Exception('Some exception')

    with tempfile.NamedTemporaryFile(mode='w', newline='', encoding='utf-8', delete=False) as temp_file:
        with patch(
            'futurex_openedx_extensions.helpers.export_csv.tempfile.NamedTemporaryFile',
            return_value=temp_file,
        ) as mock_tmp_file:
            _combine_partial_files(task_id=1, filename='export.csv', tenant_id=123)

            mock_get_storage_dir.assert_called_once_with('123')
            mock_default_storage.listdir.assert_called_once_with(
                os.path.join('/mock/storage/dir', 'export.csv_parts')
            )
            mock_default_storage.open.assert_any_call(
                os.path.join('/mock/storage/dir', 'export.csv_parts', 'part1.csv')
            )
            mock_default_storage.open.assert_any_call(
                os.path.join('/mock/storage/dir', 'export.csv_parts', 'part2.csv')
            )
            mock_upload_file_to_storage.assert_called_once_with(
                mock_tmp_file.return_value.name, 'export.csv', 123,
            )
            for part_file in ['part1.csv', 'part2.csv']:
                mock_default_storage.delete.assert_any_call(
                    os.path.join('/mock/storage/dir', 'export.csv_parts', part_file)
                )
            mock_default_storage.delete.assert_any_call(
                os.path.join('/mock/storage/dir', 'export.csv_parts')
            )
            mock_os_remove.assert_called_once_with(temp_file.name)

    assert not os_rm_failure or 'CSV Export: failed to remove temporary combined file for task' in caplog.text
