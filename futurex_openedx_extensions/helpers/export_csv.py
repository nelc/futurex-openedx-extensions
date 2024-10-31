"""
This module contains utils for tasks.
"""
import csv
import logging
import os
import tempfile
from typing import Any, Generator, Optional, Tuple
from urllib.parse import urlencode, urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.urls import resolve
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.models import DataExportTask

log = logging.getLogger(__name__)
User = get_user_model()


def _get_user(user_id: Optional[int]) -> Any:
    """Get User from user_id"""
    if user_id and isinstance(user_id, int):
        return User.objects.get(id=user_id)
    raise FXCodedException(
        code=FXExceptionCodes.USER_NOT_FOUND,
        message=f'CSV Export: Invalid user id: {user_id}',
    )


def _get_view_class_instance(path: str) -> Any:
    """Create view class instance"""
    if path:
        view_func = resolve(path)
        return view_func.func
    raise FXCodedException(
        code=FXExceptionCodes.EXPORT_CSV_MISSING_REQUIRED_PARAMS,
        message=f'CSV Export: Missing required params "path" {path}',
    )


def _get_mocked_request(url_with_query_str: str, fx_info: dict) -> Request:
    """Create mocked request"""
    if not url_with_query_str.startswith('http'):
        raise FXCodedException(
            code=FXExceptionCodes.EXPORT_CSV_VIEW_INVALID_URL,
            message=f'CSV Export: invalid URL used when mocking the request: {url_with_query_str}',
        )

    factory = APIRequestFactory()
    mocked_request = factory.get(url_with_query_str, HTTP_HOST=urlparse(url_with_query_str).hostname)
    mocked_request.user = fx_info['user']
    mocked_request.fx_permission_info = fx_info
    return mocked_request


def _get_response_data(response: Any) -> Tuple:
    """Get response data"""
    if response.status_code != 200:
        raise FXCodedException(
            code=FXExceptionCodes.EXPORT_CSV_VIEW_RESPONSE_FAILURE,
            message=f'CSV Export: View returned status code: {response.status_code}',
        )
    if not response.data:
        raise FXCodedException(
            code=FXExceptionCodes.EXPORT_CSV_VIEW_RESPONSE_FAILURE,
            message='CSV Export: Unable to process view response.',
        )
    data = response.data.get('results')
    if data is None or not isinstance(data, list):
        raise FXCodedException(
            code=FXExceptionCodes.EXPORT_CSV_VIEW_RESPONSE_FAILURE,
            message='CSV Export: The "results" key is missing or is not a list.',
        )

    count = response.data.get('count')
    if count is None or not isinstance(count, int):
        raise FXCodedException(
            code=FXExceptionCodes.EXPORT_CSV_VIEW_RESPONSE_FAILURE,
            message='CSV Export: The "count" key is missing or is not an int.',
        )
    return data, count


def _paginated_response_generator(
    fx_info: dict, view_data: dict, view_instance: Any
) -> Generator:
    """Generator to yield paginated responses."""
    url = view_data['url']
    kwargs = view_data.get('kwargs', {})
    processed_records = 0
    while url:
        mocked_request = _get_mocked_request(url, fx_info)
        response = view_instance(mocked_request, **kwargs)
        data, total_records = _get_response_data(response)
        processed_records += len(data)
        progress = round(processed_records / total_records, 2) if total_records else 0
        yield data, progress, processed_records
        url = response.data.get('next')


def _get_storage_dir(dir_name: str) -> str:
    """Return storgae dir"""
    return os.path.join(settings.FX_DASHBOARD_STORAGE_DIR, f'{str(dir_name)}/exported_files',)


def _upload_file_to_storage(local_file_path: str, filename: str, tenant_id: int) -> str:
    """
    Upload a file to the default storage (e.g., S3).

    :param local_file_path: Path to the local file to upload
    :param filename: ilename for generated CSV
    :return: The path of the uploaded file
    """
    storage_path = os.path.join(_get_storage_dir(str(tenant_id)), filename)
    with open(local_file_path, 'rb') as file:
        content_file = ContentFile(file.read())
        default_storage.save(storage_path, content_file)
    return storage_path


def _generate_csv_with_tracked_progress(
    task_id: int, fx_permission_info: dict, view_data: dict, filename: str, view_instance: Any
) -> str:
    """
    Generate response with progress and Write data to a CSV file.
    :param task_id: task id will be used to update progress
    :type task_id: int
    :param fx_permission_info: contains role and permission info
    :type fx_permission_info: dict
    :param view_data: required data for mocking
    :type view_data: dict
    :param filename: filename for generated CSV
    :type filename: str
    :param view_instance: view instance
    :type view_instance: Any
    :return: return default storage file path
    """
    page_size = view_data['page_size']
    storage_path = None
    batch_count = 0
    try:
        with tempfile.NamedTemporaryFile(mode='w', newline='', encoding='utf-8', delete=False) as tmp_file:
            for data, progress, processed_records in _paginated_response_generator(
                fx_permission_info, view_data, view_instance
            ):
                batch_count += 1
                log.info(
                    'CSV Export: processing batch %s (%s records) of task %s... %s%%',
                    batch_count,
                    processed_records,
                    task_id,
                    progress * 100,
                )
                if data:
                    log.info('CSV Export: writing batch %s of task %s...', batch_count, task_id)
                    if processed_records <= page_size:
                        # Write header only for page 1
                        writer = csv.DictWriter(
                            tmp_file, fieldnames=data[0].keys(), quotechar='"', quoting=csv.QUOTE_NONNUMERIC
                        )
                        writer.writeheader()
                    writer.writerows(data)
                    # update task progress
                    DataExportTask.set_progress(task_id, progress)
                else:
                    log.warning('CSV Export: batch %s of task %s is empty!', batch_count, task_id)

        log.info('CSV Export: uploading generated file for task %s...', task_id)
        storage_path = _upload_file_to_storage(
            tmp_file.name, filename, DataExportTask.get_task(task_id=task_id).tenant_id,
        )
        log.info('CSV Export: file uploaded successfully for task %s...', task_id)

    finally:
        try:
            os.remove(tmp_file.name)
            log.info('CSV Export: temporary file removed for task %s...', task_id)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.info('CSV Export: failed to remove temporary file for task %s: %s', task_id, str(exc))
    return storage_path


def export_data_to_csv(
    task_id: int, url: str, view_data: dict, fx_permission_info: dict, filename: str
) -> str:
    """
    Mock view with given view params and write JSON response to CSV

    :param task_id: task id will be used to update progress
    :param url: view url will be used to mock view and get response
    :param view_data: required data for mocking
    :param fx_permission_info: contains role and permission info
    :param filename: filename for generated CSV

    :return: generated filename
    """
    if urlparse(url).query:
        raise FXCodedException(
            code=FXExceptionCodes.EXPORT_CSV_BAD_URL,
            message=f'CSV Export: Unable to process URL with query params: {url}',
        )

    log.info('CSV Export: processing task %s...', task_id)
    DataExportTask.set_status(task_id=task_id, status=DataExportTask.STATUS_PROCESSING)

    user_id = fx_permission_info.get('user_id')
    user = _get_user(user_id)
    # restore user in fx_permission_info
    fx_permission_info.update({'user': user})

    query_params = view_data.get('query_params', {})
    view_instance = _get_view_class_instance(view_data.get('path', ''))
    page_size = 100
    view_pagination_class = view_instance.view_class.pagination_class

    if view_pagination_class and hasattr(view_pagination_class, 'max_page_size'):
        page_size = view_pagination_class.max_page_size or page_size

    query_params['page_size'] = page_size
    url_with_query_str = f'{url}?{urlencode(query_params)}' if query_params else url

    # Ensure the filename ends with .csv
    if not filename.endswith('.csv'):
        filename += '.csv'

    view_data.update({
        'url': url_with_query_str,
        'page_size': page_size,
        'view_instance': view_instance
    })

    return _generate_csv_with_tracked_progress(
        task_id, fx_permission_info, view_data, filename, view_instance
    )


def get_exported_file_url(fx_task: DataExportTask) -> Optional[str]:
    """Get file URL"""
    if fx_task.status == fx_task.STATUS_COMPLETED:
        storage_path = os.path.join(_get_storage_dir(str(fx_task.tenant_id)), fx_task.filename)
        if default_storage.exists(storage_path):
            return default_storage.url(storage_path)
        log.warning('CSV Export: file not found for completed task %s: %s', fx_task.id, storage_path)
    return None
