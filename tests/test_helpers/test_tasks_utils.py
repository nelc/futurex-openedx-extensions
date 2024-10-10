"""Test export csv"""
import csv
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage

from futurex_openedx_extensions.helpers.exceptions import FXCodedException
from futurex_openedx_extensions.helpers.models import DataExportTask
from futurex_openedx_extensions.helpers.tasks_utils import (
    _generate_csv_with_tracked_progress,
    _get_mocked_request,
    _get_response_data,
    _get_user,
    _get_view_class_instance,
    _paginated_response_generator,
    _upload_file_to_storage,
    export_data_to_csv,
)

_FILENAME = 'test.csv'


@pytest.fixture
def user(db):  # pylint: disable=unused-argument
    return get_user_model().objects.create_user(username='testuser', password='password')


@pytest.fixture
def fx_task(db):  # pylint: disable=unused-argument
    return DataExportTask.objects.create(filename=_FILENAME)


@pytest.mark.django_db
@pytest.mark.parametrize('user_id', [
    ('0'),
    (0),
    ('INVALID'),
    (None)
])
def test_export_data_to_csv_invalid_user(fx_task, user_id):  # pylint: disable=redefined-outer-name
    """Test export_data_to_csv with invalid user id."""
    with pytest.raises(FXCodedException) as exc_info:
        export_data_to_csv(fx_task.id, 'url', {}, {'user_id': user_id}, 'test_filename')
    assert str(exc_info.value) == f'CSV Export: Invalid user id: {user_id}'


def test_get_user_valid_id(user):  # pylint: disable=redefined-outer-name
    """Test _get_user with a valid user_id."""
    assert _get_user(user.id) == user


def test_get_view_class_instance():
    """Test _get_view_class_instance with a valid path."""
    with patch('futurex_openedx_extensions.helpers.tasks_utils.resolve') as mocked_resolve:
        mocked_resolve.return_value.func = 'abc'
        assert _get_view_class_instance('/api/path') == 'abc'


@pytest.mark.django_db
@pytest.mark.parametrize('path', [
    (''),
    (None),
])
def test_export_data_to_csv_invalid_path(path):
    """Test export_data_to_csv with invalid user id."""
    with pytest.raises(FXCodedException) as exc_info:
        _get_view_class_instance(path)
    assert str(exc_info.value) == f'CSV Export: Missing required params "path" {path}'


def test_get_mocked_request(user):  # pylint: disable=redefined-outer-name
    """Test _get_mocked_request creates a mocked request properly."""
    fx_info = {'role': 'admin', 'user': user}
    url = '/test-url/?test=123'
    request = _get_mocked_request(url, fx_info)
    assert request.method == 'GET'
    assert request.user == user
    assert request.fx_permission_info == fx_info


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


@patch('futurex_openedx_extensions.helpers.tasks_utils._get_response_data')
def test_paginated_response_generator(mock_get_response_data):
    """Test _paginated_response_generator"""
    url = 'http://example.com/api/data'
    fx_info = {'role': 'admin', 'user': user}
    page_size = 2
    view_data = {'url': f'{url}?test=value&page_size={page_size}'}
    mocked_response_1 = MagicMock()
    mocked_response_1.status_code = 200
    mocked_response_1.data = {
        'next': f'{url}?test=value&page_size={page_size}&page=2',
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
        (mocked_response_2.data['results'], 3)
    ]
    view_instance = MagicMock()
    view_instance.side_effect = [
        mocked_response_1,
        mocked_response_2
    ]
    generator = _paginated_response_generator(fx_info, view_data, view_instance)
    results = list(generator)
    assert len(results) == 2
    assert results[0] == ([{'id': 1}, {'id': 2}], 0.67, 2)
    assert results[1] == ([{'id': 3}], 1.0, 3)
    # view_instace should be called twice
    view_instance.assert_called()
    assert view_instance.call_count == 2


@patch('futurex_openedx_extensions.helpers.tasks_utils._get_response_data')
def test_paginated_response_generator_for_empty_response_data(mock_get_response_data):
    """Test _paginated_response_generator for empty response when there are no records"""
    fx_info = {'role': 'admin', 'user': user}
    view_data = {'url': 'http://example.com/api/data?test=value&page_size=2'}
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


def test_upload_file_to_storage():
    """Test uploading a file to the default storage."""
    dummy_content = b'Test content'
    # create dummy temp file
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(dummy_content)
        temp_file_path = temp_file.name
    storage_path = f'{settings.FX_DATA_EXPORT_DIR_NAME}/{_FILENAME}'
    result = _upload_file_to_storage(temp_file_path, _FILENAME)
    assert result == storage_path
    # verify file created on default storage with right content
    with default_storage.open(storage_path, 'rb') as storage_file:
        uploaded_content = storage_file.read()
        assert uploaded_content == dummy_content
    os.remove(temp_file_path)
    default_storage.delete(storage_path)
    os.rmdir(settings.FX_DATA_EXPORT_DIR_NAME)


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.tasks_utils._paginated_response_generator')
def test_generate_csv_with_tracked_progress(mock_generator):
    """Test _generate_csv_with_tracked_progress."""
    task = MagicMock()
    fake_storage_path = f'{settings.FX_DATA_EXPORT_DIR_NAME}/{_FILENAME}'
    fx_permission_info = {'user': user, 'role': 'admin'}
    view_data = {
        'page_size': 2,
        'url': 'http://example.com',
        'kwargs': {}
    }
    mock_generator.return_value = iter([
        ([{'id': 1}, {'id': 2}], 0.67, 2),
        ([{'id': 3}], 1.0, 3)
    ])
    result = _generate_csv_with_tracked_progress(
        task, fx_permission_info, view_data, _FILENAME, MagicMock()
    )
    assert result == fake_storage_path
    task.save.assert_called()
    assert task.save.call_count == 2
    assert task.progress == 1.0
    with open(fake_storage_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 3
        assert rows[0] == {'id': '1'}
        assert rows[1] == {'id': '2'}
        assert rows[2] == {'id': '3'}

    default_storage.delete(fake_storage_path)
    os.rmdir(settings.FX_DATA_EXPORT_DIR_NAME)


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.tasks_utils._paginated_response_generator')
def test_generate_csv_with_tracked_progress_for_empty_records(
    mock_generator, fx_task
):  # pylint: disable=redefined-outer-name
    """_generate_csv_with_tracked_progress for empty records"""
    fake_storage_path = f'test_dir/{_FILENAME}'
    fx_permission_info = {'user': user, 'role': 'admin'}
    view_data = {
        'page_size': 2,
        'url': 'http://example.com',
        'kwargs': {}
    }
    mock_generator.return_value = iter([([], 0, 0)])
    result = _generate_csv_with_tracked_progress(
        fx_task, fx_permission_info, view_data, _FILENAME, MagicMock()
    )
    assert result == fake_storage_path
    assert fx_task.progress == 0
    with open(fake_storage_path, 'r', newline='', encoding='utf-8') as f:
        assert f.read() == ''
    default_storage.delete(fake_storage_path)
    os.rmdir(settings.FX_DATA_EXPORT_DIR_NAME)


@patch('futurex_openedx_extensions.helpers.tasks_utils._get_view_class_instance')
@patch('futurex_openedx_extensions.helpers.tasks_utils._generate_csv_with_tracked_progress')
def test_export_data_to_csv(
    mock_generate_csv, mock_get_view, fx_task, user
):  # pylint: disable=redefined-outer-name
    """Test _export_data_to_csv"""
    mock_view_instance = MagicMock()
    mock_view_instance.view_class.max_page_size = 50
    mock_get_view.return_value = mock_view_instance
    url = 'http://example.com/api/data'
    view_data = {
        'path': 'some/path',
        'query_params': {}
    }
    fx_permission_info = {'user_id': user.id, 'role': 'admin'}
    fake_storage_path = f'{settings.FX_DATA_EXPORT_DIR_NAME}/{_FILENAME}'
    mock_generate_csv.return_value = fake_storage_path
    expected_url = f'{url}?page_size=50'
    result = export_data_to_csv(fx_task.id, url, view_data, fx_permission_info, _FILENAME)
    assert result == fake_storage_path
    assert fx_permission_info['user'] == user
    assert view_data['url'] == expected_url
    assert view_data['page_size'] == 50
    assert view_data['view_instance'] == mock_view_instance
    mock_generate_csv.assert_called_once_with(
        fx_task, fx_permission_info, view_data, _FILENAME, mock_view_instance
    )
    mock_get_view.assert_called_once_with(view_data['path'])


@patch('futurex_openedx_extensions.helpers.tasks_utils._get_view_class_instance')
@patch('futurex_openedx_extensions.helpers.tasks_utils._generate_csv_with_tracked_progress')
def test_export_data_to_csv_for_default_page_size(
    mock_generate_csv, mock_get_view, fx_task, user
):  # pylint: disable=redefined-outer-name
    """Test _export_data_to_csv"""
    fake_storage_path = f'{settings.FX_DATA_EXPORT_DIR_NAME}/{_FILENAME}'
    mocked_view_instance = MagicMock()
    mocked_view_instance.view_class.max_page_size = None
    mock_get_view.return_value = mocked_view_instance
    url = 'http://example.com/api/data'
    view_data = {
        'path': 'some/path',
        'query_params': {}
    }
    fx_permission_info = {'user_id': user.id, 'role': 'admin'}
    mock_generate_csv.return_value = fake_storage_path
    expected_url = f'{url}?page_size=100'
    result = export_data_to_csv(fx_task.id, url, view_data, fx_permission_info, _FILENAME)
    assert result == fake_storage_path
    assert view_data['url'] == expected_url
    assert view_data['page_size'] == 100


@patch('futurex_openedx_extensions.helpers.tasks_utils._get_view_class_instance')
@patch('futurex_openedx_extensions.helpers.tasks_utils._generate_csv_with_tracked_progress')
def test_export_data_to_csv_for_filename_extension(
    mock_generate_csv, mock_get_view, fx_task, user
):  # pylint: disable=redefined-outer-name
    """Test _export_data_to_csv"""
    filename = 'test'
    mock_view_instance = MagicMock()
    mock_get_view.return_value = mock_view_instance
    view_data = {
        'path': 'some/path',
        'query_params': {}
    }
    fx_permission_info = {'user_id': user.id, 'role': 'admin'}
    mock_generate_csv.return_value = 'randome/path/test.csv'
    export_data_to_csv(fx_task.id, 'http://example.com/api', view_data, fx_permission_info, 'test.csv')
    mock_generate_csv.assert_called_once_with(
        fx_task, fx_permission_info, view_data, f'{filename}.csv', mock_view_instance
    )
