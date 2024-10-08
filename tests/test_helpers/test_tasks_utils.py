"""Test export csv"""
import csv
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from rest_framework.test import APIRequestFactory

from futurex_openedx_extensions.helpers.exceptions import FXCodedException
from futurex_openedx_extensions.helpers.tasks_utils import (
    _get_mocked_request,
    _get_response_data,
    _get_user,
    _get_view_class_instance,
    _upload_file_to_storage,
    export_data_to_csv,
)


@pytest.fixture
def user(db):  # pylint: disable=unused-argument
    return get_user_model().objects.create_user(username='testuser', password='password')


@pytest.fixture
def mocked_request(user):  # pylint: disable=redefined-outer-name
    """Create an instance of the ExportCSVMixin for testing."""
    request = APIRequestFactory().get('/')
    request.user = user
    request.fx_permission_info = {}
    return request


@pytest.mark.django_db
@pytest.mark.parametrize('user_id', [
    ('0'),
    (0),
    ('INVALID'),
    (None)
])
def test_export_data_to_csv_invalid_user(user_id):
    """Test export_data_to_csv with invalid user id."""
    with pytest.raises(FXCodedException) as exc_info:
        export_data_to_csv('url', {}, {'user': user_id}, 'test_filename')
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
    fx_info = {'role': 'admin'}
    query_params = {'param1': 'value1'}

    url = '/test-url/'
    request = _get_mocked_request(url, user, fx_info, query_params)

    assert request.method == 'GET'
    assert request.user == user
    assert request.fx_permission_info == fx_info
    assert request.query_params == query_params


def test_get_response_data_success(mocked_request):  # pylint: disable=redefined-outer-name
    """Test _get_response_data with a successful mocked request."""
    expected_data = {'results': [{'id': 1, 'name': 'Test'}]}
    with patch('futurex_openedx_extensions.helpers.tasks_utils._get_view_class_instance') as mocked_view_instance:
        mocked_view_instance.return_value.status_code = 200
        mocked_view_instance.return_value.data = expected_data
        data = _get_response_data(mocked_request, {}, mocked_view_instance)
        assert data == expected_data['results']


@pytest.mark.parametrize('status_code, data, exception_msg', [
    (400, {}, 'CSV Export: View returned status code: 400'),
    (200, {}, 'CSV Export: Unable to process view response.'),
    (200, {'other_than_results': []}, 'CSV Export: The "results" key is missing or is not a list.'),
    (200, {'results': 'not list'}, 'CSV Export: The "results" key is missing or is not a list.')
])
def test_get_response_data_failure(
    mocked_request, status_code, data, exception_msg
):  # pylint: disable=redefined-outer-name
    """Test _get_response_data with failure of response or unexpected response"""
    with patch('futurex_openedx_extensions.helpers.tasks_utils._get_view_class_instance') as mocked_view_instance:
        mocked_view_instance.return_value.status_code = status_code
        mocked_view_instance.return_value.data = data
        with pytest.raises(FXCodedException) as exc_info:
            _get_response_data(mocked_request, {}, mocked_view_instance)
        assert str(exc_info.value) == exception_msg


@patch('futurex_openedx_extensions.helpers.tasks_utils._get_view_class_instance')
@patch('futurex_openedx_extensions.helpers.tasks_utils._get_response_data')
@patch('futurex_openedx_extensions.helpers.tasks_utils._get_mocked_request')
def test_export_data_to_csv_creates_csv_file(
    mocked_get_mocked_request, mocked_get_response_data, mocked_get_view_class_instance, user
):    # pylint: disable=redefined-outer-name
    """ test export_data_to_csv_method for csv creation"""
    url = 'http://example.com/api/data'
    view_data = {
        'path': '/api/data',
        'query_params': {},
        'kwargs': {}
    }
    fx_permission_info = {'role': 'admin', 'permissions': ['read', 'write'], 'user': user.id}
    filename = 'test_file.csv'
    test_data = [{'column1': 'value1', 'column2': 'value2'}, {'column1': 'value3', 'column2': 'value4'}]
    mocked_get_view_class_instance.return_value = MagicMock()
    mocked_get_mocked_request.return_value = MagicMock()
    mocked_get_response_data.return_value = test_data
    generated_file = export_data_to_csv(url, view_data, fx_permission_info, filename)
    assert generated_file == f'{settings.FX_DATA_EXPORT_DIR_NAME }/{filename}'
    # Verify that the file was created
    assert os.path.isfile(generated_file) is True
    # Verify the contents of the CSV file
    with open(generated_file, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]['column1'] == 'value1'
        assert rows[0]['column2'] == 'value2'
        assert rows[1]['column1'] == 'value3'
        assert rows[1]['column2'] == 'value4'
    os.remove(generated_file)
    os.rmdir(settings.FX_DATA_EXPORT_DIR_NAME)


@patch('futurex_openedx_extensions.helpers.tasks_utils._get_view_class_instance')
@patch('futurex_openedx_extensions.helpers.tasks_utils._get_response_data')
@patch('futurex_openedx_extensions.helpers.tasks_utils._get_mocked_request')
def test_export_data_to_csv_for_empty_data(
    mocked_get_mocked_request, mocked_get_response_data, mocked_get_view_class_instance, user
):  # pylint: disable=redefined-outer-name
    """test export_data_to_csv_method when for empty data"""
    url = 'http://example.com/api/data'
    view_data = {
        'user_id': user.id,
        'path': '/api/data',
        'query_params': {},
        'kwargs': {}
    }
    fx_permission_info = {'role': 'admin', 'permissions': ['read', 'write'], 'user': user.id}
    filename = 'test_file.csv'
    test_data = []
    mocked_get_view_class_instance.return_value = MagicMock()
    mocked_get_mocked_request.return_value = MagicMock()
    mocked_get_response_data.return_value = test_data
    generated_file = export_data_to_csv(url, view_data, fx_permission_info, filename)
    assert generated_file == f'{settings.FX_DATA_EXPORT_DIR_NAME }/{filename}'
    # Verify that the file was created
    assert os.path.isfile(generated_file) is True
    # Verify the contents of the CSV file
    with open(generated_file, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        assert len(rows) == 0
    os.remove(generated_file)
    os.rmdir(settings.FX_DATA_EXPORT_DIR_NAME)


@patch('futurex_openedx_extensions.helpers.tasks_utils._get_view_class_instance')
@patch('futurex_openedx_extensions.helpers.tasks_utils._get_response_data')
@patch('futurex_openedx_extensions.helpers.tasks_utils._get_mocked_request')
def test_export_data_to_csv_for_filename_without_csv_ext(
    mocked_get_mocked_request, mocked_get_response_data, mocked_get_view_class_instance, user
):  # pylint: disable=redefined-outer-name
    """ test export_data_to_csv_method for file extension"""
    url = 'http://example.com/api/data'
    view_data = {
        'user_id': user.id,
        'path': '/api/data',
        'query_params': {},
        'kwargs': {}
    }
    fx_permission_info = {'role': 'admin', 'permissions': ['read', 'write'], 'user': user.id}
    test_data = []
    filename = 'test_file'
    mocked_get_view_class_instance.return_value = MagicMock()
    mocked_get_mocked_request.return_value = MagicMock()
    mocked_get_response_data.return_value = test_data
    generated_filename = export_data_to_csv(url, view_data, fx_permission_info, filename)
    assert generated_filename == f'{settings.FX_DATA_EXPORT_DIR_NAME }/{filename}.csv'
    os.remove(generated_filename)
    os.rmdir(settings.FX_DATA_EXPORT_DIR_NAME)


def test_upload_file_to_storage():
    """Test uploading a file to the default storage."""
    dummy_content = b'Test content'
    # create dummy temp file
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(dummy_content)
        temp_file_path = temp_file.name
    storage_path = 'test_dir/test_file.txt'
    result = _upload_file_to_storage(temp_file_path, storage_path)
    assert result == storage_path
    # verify file created on default storage with right content
    with default_storage.open(storage_path, 'rb') as storage_file:
        uploaded_content = storage_file.read()
        assert uploaded_content == dummy_content
    os.remove(temp_file_path)
    default_storage.delete(storage_path)
    os.rmdir('test_dir')
