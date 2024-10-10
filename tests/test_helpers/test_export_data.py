"""Test export csv"""
from unittest.mock import PropertyMock, patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory

from futurex_openedx_extensions.helpers.export_data import ExportCSVMixin
from futurex_openedx_extensions.helpers.models import DataExportTask


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
    request.fx_permission_info = {'user': user}
    view_instance.request = request  # pylint: disable=attribute-defined-outside-init
    return view_instance


def test_filename(export_csv_mixin):  # pylint: disable=redefined-outer-name
    """Test the filename property."""
    fake_time = '20241002_120000_123456'
    with patch('futurex_openedx_extensions.helpers.export_data.datetime') as mock_datetime_class:
        mock_datetime_class.now.return_value.strftime.return_value = fake_time
        filename = export_csv_mixin.filename
        expected_filename = f'test_export_{fake_time}.csv'
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


def test_get_serialized_fx_permission_info(export_csv_mixin, user):  # pylint: disable=redefined-outer-name
    """Test get_serialized_fx_permission_info for user"""
    assert isinstance(export_csv_mixin.request.fx_permission_info.get('user'), get_user_model()) is True
    serialized_fx_info = export_csv_mixin.get_serialized_fx_permission_info()
    expected_serialized_fx_info = {'user_id': user.id, 'user': None}
    assert serialized_fx_info == expected_serialized_fx_info


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.export_data.export_data_to_csv_task.delay')
@patch('futurex_openedx_extensions.helpers.export_data.ExportCSVMixin.get_view_request_url')
@patch('futurex_openedx_extensions.helpers.export_data.ExportCSVMixin.get_filtered_query_params')
def test_generate_csv_url_response(
    mocked_get_query_params_func,
    mocked_get_view_request_url,
    mocked_export_data_to_csv_task,
    export_csv_mixin,
    user
):  # pylint: disable=redefined-outer-name
    """Test the generate_csv_url_response method."""
    filename = 'mocked_file.csv'
    fake_url = 'http://example.com/view'
    export_csv_mixin.request.query_params = {'download': 'csv'}
    serialized_fx_permission_info = {'user_id': user.id, 'user': None}
    fake_query_params = {}
    view_params = {'query_params': fake_query_params, 'kwargs': export_csv_mixin.kwargs, 'path': '/'}
    with patch(
        'futurex_openedx_extensions.helpers.export_data.ExportCSVMixin.filename',
        new_callable=PropertyMock
    ) as mocked_filename_property:
        mocked_get_view_request_url.return_value = fake_url
        mocked_filename_property.return_value = filename
        mocked_get_query_params_func.return_value = fake_query_params
        response = export_csv_mixin.generate_csv_url_response()
        fx_task = DataExportTask.objects.get(filename=filename)
        mocked_export_data_to_csv_task.assert_called_once_with(
            fx_task.id, fake_url, view_params, serialized_fx_permission_info, filename
        )
        expected_response = {'success': f'Task innititated successfully with id: {fx_task.id}'}
        assert response == expected_response


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.export_data.export_data_to_csv_task.delay')
@patch('futurex_openedx_extensions.helpers.export_data.ExportCSVMixin.get_view_request_url')
@patch('futurex_openedx_extensions.helpers.export_data.ExportCSVMixin.get_filtered_query_params')
def test_list_with_csv_download(
    mocked_get_query_params_func,
    mocked_get_view_request_url,
    mocked_export_data_to_csv_task,
    export_csv_mixin,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Test the list method with dowload csv query param."""
    filename = 'mocked_file.csv'
    fake_url = 'http://example.com/view'
    export_csv_mixin.request.query_params = {'download': 'csv'}
    with patch(
        'futurex_openedx_extensions.helpers.export_data.ExportCSVMixin.filename',
        new_callable=PropertyMock
    ) as mocked_filename_property:
        mocked_get_view_request_url.return_value = fake_url
        mocked_filename_property.return_value = filename
        mocked_get_query_params_func.return_value = {}
        response = export_csv_mixin.list(export_csv_mixin.request)
        fx_task = DataExportTask.objects.get(filename=filename)
        expected_response = {'success': f'Task innititated successfully with id: {fx_task.id}'}
        assert response.status_code == 200
        assert response.data == expected_response
