"""Test export csv"""
import csv
import os
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status as http_status
from rest_framework.test import APIRequestFactory

from futurex_openedx_extensions.helpers.exceptions import FXCodedException
from futurex_openedx_extensions.helpers.export_data import (
    ExportCSVMixin,
    _get_mocked_request,
    _get_response_data,
    _get_user,
    _get_view_class_instance,
    export_data_to_csv,
)


class TestView(ExportCSVMixin):
    fx_view_name = 'test_export'
    kwargs = {}


@pytest.fixture
def user(db):  # pylint: disable=unused-argument
    return get_user_model().objects.create_user(username='testuser', password='password')


@pytest.fixture
def export_csv_mixin(user):  # pylint: disable=redefined-outer-name
    """Create an instance of the ExportCSVMixin for testing."""
    view_instance = TestView()
    request = APIRequestFactory().get('/')
    request.user = user
    request.fx_permission_info = {}
    view_instance.request = request  # pylint: disable=attribute-defined-outside-init
    return view_instance


def test_filename(export_csv_mixin):  # pylint: disable=redefined-outer-name
    """Test the filename property."""
    fake_time = '20241002_120000_123456'
    with patch('futurex_openedx_extensions.helpers.export_data.datetime') as mock_datetime_class:
        mock_datetime_class.now.return_value.strftime.return_value = fake_time
        filename = export_csv_mixin.filename
        expected_filename = f'test_export_{fake_time}'
        assert filename == expected_filename


@pytest.mark.parametrize('filename', [
    ('test.csv'),
    (None),
    ('')
])
def test_build_download_url(export_csv_mixin, filename):  # pylint: disable=redefined-outer-name
    """Test the build_download_url method."""
    expected_url = ''
    if filename:
        expected_url = f'{export_csv_mixin.request.build_absolute_uri()}media/{filename}'
    url = export_csv_mixin.build_download_url(filename)
    assert url == expected_url


def test_get_view_request_url(export_csv_mixin):  # pylint: disable=redefined-outer-name
    """Test the get_view_request_url method."""
    query_params = {'key1': 'value1', 'key2': 'value2'}
    expected_url = 'http://testserver/?key1=value1&key2=value2'
    assert export_csv_mixin.get_view_request_url(query_params) == expected_url


def test_get_filtered_query_params(export_csv_mixin):  # pylint: disable=redefined-outer-name
    """Test the get_filtered_query_params method."""
    export_csv_mixin.request.GET = {'download': 'csv', 'page_size': '10', 'page': '1', 'other_key': 'value'}
    expected_params = {'other_key': 'value'}
    assert export_csv_mixin.get_filtered_query_params() == expected_params


def test_generate_csv_url_response(export_csv_mixin):  # pylint: disable=redefined-outer-name
    """Test the generate_csv_url_response method."""
    filename = 'mocked_file.csv'
    export_csv_mixin.request.query_params = {'download': 'csv'}
    with patch('futurex_openedx_extensions.helpers.export_data.export_data_to_csv') as mocked_export_data_to_csv:
        mocked_export_data_to_csv.return_value = filename
        expected_response = {'download_url': export_csv_mixin.build_download_url(filename)}
        response = export_csv_mixin.generate_csv_url_response()
        assert response == expected_response


def test_list_with_csv_download(export_csv_mixin):  # pylint: disable=redefined-outer-name
    """Test the list method with CSV download."""
    export_csv_mixin.request.query_params = {'download': 'csv'}
    filename = 'mocked_file.csv'

    with patch('futurex_openedx_extensions.helpers.export_data.export_data_to_csv') as mocked_export_data_to_csv:
        mocked_export_data_to_csv.return_value = filename
        response = export_csv_mixin.list(export_csv_mixin.request)
        expected_response = {'download_url': export_csv_mixin.build_download_url(filename)}
        assert response.status_code == http_status.HTTP_200_OK
        assert response.data == expected_response


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
        export_data_to_csv('url', {'user_id': user_id}, {}, 'test_filename')
    assert str(exc_info.value) == f'CSV Export: Invalid user id: {user_id}'


def test_get_user_valid_id(user):  # pylint: disable=redefined-outer-name
    """Test _get_user with a valid user_id."""
    assert _get_user(user.id) == user


def test_get_view_class_instance():
    """Test _get_view_class_instance with a valid path."""
    with patch('futurex_openedx_extensions.helpers.export_data.resolve') as mocked_resolve:
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
    mocked_request = _get_mocked_request(url, user, fx_info, query_params)

    assert mocked_request.method == 'GET'
    assert mocked_request.user == user
    assert mocked_request.fx_permission_info == fx_info
    assert mocked_request.query_params == query_params


def test_get_response_data_success(export_csv_mixin):  # pylint: disable=redefined-outer-name
    """Test _get_response_data with a successful mocked request."""
    expected_data = {'results': [{'id': 1, 'name': 'Test'}]}
    with patch('futurex_openedx_extensions.helpers.export_data._get_view_class_instance') as mocked_view_instance:
        mocked_view_instance.return_value.status_code = 200
        mocked_view_instance.return_value.data = expected_data
        data = _get_response_data(export_csv_mixin.request, {}, mocked_view_instance)
        assert data == expected_data['results']


@pytest.mark.parametrize('status_code, data, exception_msg', [
    (400, {}, 'CSV Export: View returned status code: 400'),
    (200, {}, 'CSV Export: Unable to process view response.'),
    (200, {'other_than_results': []}, 'CSV Export: The "results" key is missing or is not a list.'),
    (200, {'results': 'not list'}, 'CSV Export: The "results" key is missing or is not a list.')
])
def test_get_response_data_failure(
    export_csv_mixin, status_code, data, exception_msg
):  # pylint: disable=redefined-outer-name
    """Test _get_response_data with failure of response or unexpected response"""
    with patch('futurex_openedx_extensions.helpers.export_data._get_view_class_instance') as mocked_view_instance:
        mocked_view_instance.return_value.status_code = status_code
        mocked_view_instance.return_value.data = data
        with pytest.raises(FXCodedException) as exc_info:
            _get_response_data(export_csv_mixin.request, {}, mocked_view_instance)
        assert str(exc_info.value) == exception_msg


def test_export_data_to_csv_creates_csv_file(user):  # pylint: disable=redefined-outer-name
    """ test export_data_to_csv_method for csv creation"""
    url = 'http://example.com/api/data'
    view_data = {
        'user_id': user.id,
        'path': '/api/data',
        'query_params': {},
        'kwargs': {}
    }
    fx_permission_info = {'role': 'admin', 'permissions': ['read', 'write']}
    filename = 'test_file.csv'
    test_data = [{'column1': 'value1', 'column2': 'value2'}, {'column1': 'value3', 'column2': 'value4'}]

    with patch(
        'futurex_openedx_extensions.helpers.export_data._get_view_class_instance'
    ) as mocked_get_view_class_instance:
        with patch(
            'futurex_openedx_extensions.helpers.export_data._get_response_data'
        ) as mocked_get_response_data:
            with patch(
                'futurex_openedx_extensions.helpers.export_data._get_mocked_request'
            ) as mocked_get_mocked_request:
                mocked_get_view_class_instance.return_value = MagicMock()
                mocked_get_mocked_request.return_value = MagicMock()
                mocked_get_response_data.return_value = test_data
                generated_filename = export_data_to_csv(url, view_data, fx_permission_info, filename)
                assert generated_filename == filename
                csv_file_path = os.path.join(settings.MEDIA_ROOT, filename)
                # Verify that the file was created
                assert os.path.isfile(csv_file_path) is True
                # Verify the contents of the CSV file
                with open(csv_file_path, mode='r', encoding='utf-8') as file:
                    reader = csv.DictReader(file)
                    rows = list(reader)
                    assert len(rows) == 2
                    assert rows[0]['column1'] == 'value1'
                    assert rows[0]['column2'] == 'value2'
                    assert rows[1]['column1'] == 'value3'
                    assert rows[1]['column2'] == 'value4'
                os.remove(csv_file_path)


def test_export_data_to_csv_for_empty_data(user):  # pylint: disable=redefined-outer-name
    """test export_data_to_csv_method when for empty data"""
    url = 'http://example.com/api/data'
    view_data = {
        'user_id': user.id,
        'path': '/api/data',
        'query_params': {},
        'kwargs': {}
    }
    fx_permission_info = {'role': 'admin', 'permissions': ['read', 'write']}
    filename = 'test_file.csv'
    test_data = []
    with patch(
        'futurex_openedx_extensions.helpers.export_data._get_view_class_instance'
    ) as mocked_get_view_class_instance:
        with patch(
            'futurex_openedx_extensions.helpers.export_data._get_response_data'
        ) as mocked_get_response_data:
            with patch(
                'futurex_openedx_extensions.helpers.export_data._get_mocked_request'
            ) as mocked_get_mocked_request:
                mocked_get_view_class_instance.return_value = MagicMock()
                mocked_get_mocked_request.return_value = MagicMock()
                mocked_get_response_data.return_value = test_data
                generated_filename = export_data_to_csv(url, view_data, fx_permission_info, filename)
                assert generated_filename == filename
                csv_file_path = os.path.join(settings.MEDIA_ROOT, filename)
                # Verify that the file was created
                assert os.path.isfile(csv_file_path) is True
                # Verify the contents of the CSV file
                with open(csv_file_path, mode='r', encoding='utf-8') as file:
                    reader = csv.DictReader(file)
                    rows = list(reader)
                    assert len(rows) == 0
                os.remove(csv_file_path)


def test_export_data_to_csv_for_filename_without_csv_ext(user):  # pylint: disable=redefined-outer-name
    """ test export_data_to_csv_method for file extension"""
    url = 'http://example.com/api/data'
    view_data = {
        'user_id': user.id,
        'path': '/api/data',
        'query_params': {},
        'kwargs': {}
    }
    fx_permission_info = {'role': 'admin', 'permissions': ['read', 'write']}
    test_data = []
    filename = 'test_file'
    expected_filename = 'test_file.csv'
    with patch(
        'futurex_openedx_extensions.helpers.export_data._get_view_class_instance'
    ) as mocked_get_view_class_instance:
        with patch(
            'futurex_openedx_extensions.helpers.export_data._get_response_data'
        ) as mocked_get_response_data:
            with patch(
                'futurex_openedx_extensions.helpers.export_data._get_mocked_request'
            ) as mocked_get_mocked_request:
                mocked_get_view_class_instance.return_value = MagicMock()
                mocked_get_mocked_request.return_value = MagicMock()
                mocked_get_response_data.return_value = test_data
                generated_filename = export_data_to_csv(url, view_data, fx_permission_info, filename)
                assert generated_filename == expected_filename
                csv_file_path = os.path.join(settings.MEDIA_ROOT, expected_filename)
                os.remove(csv_file_path)
