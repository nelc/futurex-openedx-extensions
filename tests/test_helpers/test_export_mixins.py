"""Test export csv"""
from unittest.mock import PropertyMock, patch

import pytest
from django.contrib.auth import get_user_model
from eox_tenant.models import TenantConfig
from rest_framework import status as http_status
from rest_framework.test import APIRequestFactory

from futurex_openedx_extensions.helpers.export_mixins import ExportCSVMixin
from futurex_openedx_extensions.helpers.models import DataExportTask


class TestView(ExportCSVMixin):
    fx_view_name = 'test_export'
    kwargs = {}
    request = None


@pytest.fixture
def user(db):  # pylint: disable=unused-argument
    return get_user_model().objects.create(username='testuser', password='password')


@pytest.fixture
def tenant(db):  # pylint: disable=unused-argument
    return TenantConfig.objects.create(external_key='test')


@pytest.fixture
def export_csv_mixin(user, tenant):  # pylint: disable=redefined-outer-name
    """Create an instance of the ExportCSVMixin for testing."""
    view_instance = TestView()
    request = APIRequestFactory().get('/')
    request.user = user
    request.fx_permission_info = {'user': user, 'view_allowed_tenant_ids_any_access': [tenant.id]}
    view_instance.request = request
    return view_instance


def test_export_filename(export_csv_mixin):  # pylint: disable=redefined-outer-name
    """Test the export_filename property."""
    fake_time = '20241002_120000_123456'
    with patch('futurex_openedx_extensions.helpers.export_mixins.datetime') as mock_datetime_class:
        mock_datetime_class.now.return_value.strftime.return_value = fake_time
        filename = export_csv_mixin.export_filename
        expected_filename = f'test_export_{fake_time}.csv'
        assert filename == expected_filename


def test_get_view_request_url(export_csv_mixin):  # pylint: disable=redefined-outer-name
    """Test the get_view_request_url method."""
    expected_url = 'http://testserver/'
    assert export_csv_mixin.get_view_request_url() == expected_url


def test_get_filtered_query_params(export_csv_mixin):  # pylint: disable=redefined-outer-name
    """Test the get_filtered_query_params method."""
    export_csv_mixin.request.GET = {'download': 'csv', 'page_size': '10', 'page': '1', 'other_key': 'value'}
    expected_params = {'other_key': 'value'}
    assert export_csv_mixin.get_filtered_query_params() == expected_params


def test_get_serialized_fx_permission_info(export_csv_mixin, user, tenant):  # pylint: disable=redefined-outer-name
    """Test get_serialized_fx_permission_info for user"""
    assert isinstance(export_csv_mixin.request.fx_permission_info.get('user'), get_user_model()) is True
    serialized_fx_info = export_csv_mixin.get_serialized_fx_permission_info()
    expected_serialized_fx_info = {
        'user_id': user.id, 'user': None, 'view_allowed_tenant_ids_any_access': [tenant.id]
    }
    assert serialized_fx_info == expected_serialized_fx_info


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.export_mixins.export_data_to_csv_task.delay')
@patch('futurex_openedx_extensions.helpers.export_mixins.ExportCSVMixin.get_view_request_url')
@patch('futurex_openedx_extensions.helpers.export_mixins.ExportCSVMixin.get_filtered_query_params')
def test_generate_csv_url_response(
    mocked_get_query_params_func,
    mocked_get_view_request_url,
    mocked_export_data_to_csv_task,
    export_csv_mixin,
    user,
    tenant
):  # pylint: disable=redefined-outer-name, too-many-arguments
    """Test the generate_csv_url_response method."""
    filename = 'mocked_file.csv'
    fake_url = 'http://example.com/view'
    export_csv_mixin.request.query_params = {'download': 'csv'}
    serialized_fx_permission_info = {
        'user_id': user.id, 'user': None, 'view_allowed_tenant_ids_any_access': [tenant.id]
    }
    fake_query_params = {}
    view_params = {'query_params': fake_query_params, 'kwargs': export_csv_mixin.kwargs, 'path': '/'}
    with patch(
        'futurex_openedx_extensions.helpers.export_mixins.ExportCSVMixin.export_filename',
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
        assert response['success'] == f'Task initiated successfully with id: {fx_task.id}'
        assert response['export_task_id'] == fx_task.id


@pytest.mark.django_db
def test_get_existing_incompleted_task_count(user, tenant, export_csv_mixin):  # pylint: disable=redefined-outer-name
    """Test the incomplete task count logic."""
    filename = 'text.csv'
    related_id = 'test-id-1'
    current_view = 'test_export'

    # Create tasks with different statuses
    # Add 2 valid tasks - should be counted
    DataExportTask.objects.create(
        filename=filename, view_name=current_view, user=user, tenant=tenant,
        related_id=related_id, progress=0.0, status=DataExportTask.STATUS_PROCESSING
    )
    DataExportTask.objects.create(
        filename=filename, view_name=current_view, user=user, tenant=tenant,
        related_id=related_id, progress=0.6, status=DataExportTask.STATUS_IN_QUEUE
    )
    # Add completed task - should not be counted
    DataExportTask.objects.create(
        filename=filename, view_name=current_view, user=user, tenant=tenant,
        related_id=related_id, progress=1.1, status=DataExportTask.STATUS_COMPLETED
    )
    assert export_csv_mixin.get_existing_incompleted_task_count() == 2

    # Add task from a different view - should not be counted
    DataExportTask.objects.create(
        filename=filename, view_name='another view', user=user, tenant=tenant,
        related_id=related_id, progress=0.6, status=DataExportTask.STATUS_IN_QUEUE
    )
    assert export_csv_mixin.get_existing_incompleted_task_count() == 2

    # Add another valid task - should be counted
    DataExportTask.objects.create(
        filename=filename, view_name=current_view, user=user, tenant=tenant,
        related_id=related_id, progress=0.6, status=DataExportTask.STATUS_IN_QUEUE
    )
    assert export_csv_mixin.get_existing_incompleted_task_count() == 3

    # Add failed task - should not be counted
    DataExportTask.objects.create(
        filename=filename, view_name=current_view, user=user, tenant=tenant,
        related_id=related_id, progress=0.5, error_message='some error', status=DataExportTask.STATUS_FAILED
    )
    # Add task from another user - should not be counted
    another_user = get_user_model().objects.get(id=1)
    DataExportTask.objects.create(
        filename=filename, view_name=current_view, user=another_user, tenant=tenant,
        related_id=related_id, progress=0.5, error_message='some error', status=DataExportTask.STATUS_FAILED
    )
    # count of incomplete tasks should remain same i.e 3
    assert export_csv_mixin.get_existing_incompleted_task_count() == 3


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.export_mixins.export_data_to_csv_task.delay')
@patch('futurex_openedx_extensions.helpers.export_mixins.ExportCSVMixin.get_view_request_url')
@patch('futurex_openedx_extensions.helpers.export_mixins.ExportCSVMixin.get_filtered_query_params')
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
        'futurex_openedx_extensions.helpers.export_mixins.ExportCSVMixin.export_filename',
        new_callable=PropertyMock
    ) as mocked_filename_property:
        mocked_get_view_request_url.return_value = fake_url
        mocked_filename_property.return_value = filename
        mocked_get_query_params_func.return_value = {}
        response = export_csv_mixin.list(export_csv_mixin.request)
        fx_task = DataExportTask.objects.get(filename=filename)
        expected_response = {
            'success': f'Task initiated successfully with id: {fx_task.id}',
            'export_task_id': fx_task.id
        }
        assert response.status_code == 200
        assert response.data == expected_response


@pytest.mark.django_db
def test_list_with_csv_download_for_multiple_tenants(export_csv_mixin):  # pylint: disable=redefined-outer-name
    """Test the list method for multiple tenants in fx permision info"""
    export_csv_mixin.request.fx_permission_info['view_allowed_tenant_ids_any_access'] = [1, 2]
    export_csv_mixin.request.query_params = {'download': 'csv'}
    response = export_csv_mixin.list(export_csv_mixin.request)
    assert response.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_list_with_csv_download_for_no_tenant(export_csv_mixin):  # pylint: disable=redefined-outer-name
    """Test the list method for no tenant in fx info permissions."""
    export_csv_mixin.request.fx_permission_info['view_allowed_tenant_ids_any_access'] = []
    export_csv_mixin.request.query_params = {'download': 'csv'}
    response = export_csv_mixin.list(export_csv_mixin.request)
    assert response.status_code == http_status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_list_with_csv_download_for_tasks_limit(export_csv_mixin, user, tenant):  # pylint: disable=redefined-outer-name
    """Test the list method for tasks limit per user."""
    filename = 'text.csv'
    related_id = 'test-id-1'
    current_view = 'test_export'
    export_csv_mixin.request.query_params = {'download': 'csv'}
    DataExportTask.objects.create(
        filename=filename, view_name=current_view, user=user, tenant=tenant,
        related_id=related_id, progress=0.0, status=DataExportTask.STATUS_PROCESSING
    )
    DataExportTask.objects.create(
        filename=filename, view_name=current_view, user=user, tenant=tenant,
        related_id=related_id, progress=0.6, status=DataExportTask.STATUS_IN_QUEUE
    )
    DataExportTask.objects.create(
        filename=filename, view_name=current_view, user=user, tenant=tenant,
        related_id=related_id, progress=0.6, status=DataExportTask.STATUS_IN_QUEUE
    )
    response = export_csv_mixin.list(export_csv_mixin.request)
    assert response.status_code == http_status.HTTP_429_TOO_MANY_REQUESTS
