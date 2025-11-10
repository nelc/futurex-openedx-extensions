"""
This module contains utils for tasks.
"""
import csv
import logging
import os
import tempfile
from datetime import datetime
from typing import Any, Generator, Optional, Tuple
from urllib.parse import urlencode, urlparse

import boto3
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core.files.storage import default_storage
from django.urls import resolve
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from storages.backends.s3boto3 import S3Boto3Storage

from futurex_openedx_extensions.helpers.constants import CSV_EXPORT_UPLOAD_DIR
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.models import DataExportTask
from futurex_openedx_extensions.helpers.upload import get_storage_dir, upload_file

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


def _get_mocked_request(url_with_query_str: str, fx_info: dict, site: Site) -> Request:
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
    mocked_request.site = site
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


def _is_long_running_process(start_time: datetime) -> bool:
    """Check if the process is running for more than the limit."""
    return (datetime.now() - start_time).total_seconds() > settings.FX_TASK_MINUTES_LIMIT * 60


def _paginated_response_generator(
    fx_info: dict, view_data: dict, view_instance: Any
) -> Generator:
    """Generator to yield paginated responses."""
    page = view_data['start_page']
    kwargs = view_data.get('kwargs', {})
    processed_records = (page - 1) * view_data['page_size']
    url = f'{view_data["url"]}'
    start_time = datetime.now()
    while url and not view_data['end_page']:
        mocked_request = _get_mocked_request(url, fx_info, view_data['site'])
        response = view_instance(mocked_request, **kwargs)
        data, total_records = _get_response_data(response)
        processed_records += len(data)

        progress = round(processed_records / total_records, 2) if total_records else 0
        yield data, progress, processed_records
        if _is_long_running_process(start_time):
            view_data['end_page'] = page
        page += 1
        url = response.data.get('next')


def _upload_file_to_storage(local_file_path: str, filename: str, tenant_id: int, partial_tag: int = 0) -> str:
    """
    Upload a file to the default storage (e.g., S3).

    :param local_file_path: Path to the local file to upload
    :type local_file_path: str
    :param filename: filename for generated CSV
    :type filename: str
    :param tenant_id: The tenant ID.
    :type tenant_id: int
    :param partial_tag: The partial file number.
    :type partial_tag: int
    :return: The path of the uploaded file
    :rtype: str
    """
    if partial_tag:
        filename = f'{filename}_parts/{filename}_{partial_tag:06d}'
    storage_path = os.path.join(get_storage_dir(tenant_id, CSV_EXPORT_UPLOAD_DIR), filename)
    upload_file(storage_path, local_file_path, is_private=True)
    return storage_path


def _combine_partial_files(task_id: int, filename: str, tenant_id: int) -> None:
    """
    Combine partial files into a single file.

    :param task_id: The task ID.
    :type task_id: int
    :param filename: The filename of the partial files.
    :type filename: str
    :param tenant_id: The tenant ID.
    :type tenant_id: int
    """
    storage_dir = get_storage_dir(tenant_id, CSV_EXPORT_UPLOAD_DIR)
    parts_dir = os.path.join(storage_dir, f'{filename}_parts')
    partial_files = default_storage.listdir(parts_dir)[1]

    log.info('CSV Export: combining partial files for task %s...', task_id)
    try:
        with tempfile.NamedTemporaryFile(mode='w', newline='', encoding='utf-8', delete=False) as tmp_file:
            for partial_file in sorted(partial_files):
                with default_storage.open(os.path.join(parts_dir, partial_file)) as file:
                    tmp_file.write(file.read().decode('utf-8'))
        log.info('CSV Export: uploading combined file for task %s...', task_id)
        _upload_file_to_storage(
            tmp_file.name, filename, DataExportTask.get_task(task_id=task_id).tenant.id,
        )
        log.info('CSV Export: file uploaded successfully for task %s...', task_id)
        log.info('CSV Export: deleting partial files for task %s...', task_id)
        for partial_file in partial_files:
            default_storage.delete(os.path.join(parts_dir, partial_file))
        log.info('CSV Export: deleting partial files directory for task %s...', task_id)
        default_storage.delete(parts_dir)
        log.info('CSV Export: partial files directory deleted successfully for task %s...', task_id)

    finally:
        try:
            os.remove(tmp_file.name)
            log.info('CSV Export: temporary combined file removed for task %s...', task_id)
        except Exception as exc:
            log.info('CSV Export: failed to remove temporary combined file for task %s: %s', task_id, str(exc))


def _generate_csv_with_tracked_progress(  # pylint: disable=too-many-branches
    task_id: int, fx_permission_info: dict, view_data: dict, filename: str, view_instance: Any
) -> bool:
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
    :return: True if export fully completed, False if partially completed
    :rtype: bool
    """
    fully_completed = True
    page_size = view_data['page_size']
    batch_count = view_data.get('processed_batches', 0)
    writer = None
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
                    round(progress * 100, 2),
                )
                if data:
                    log.info('CSV Export: writing batch %s of task %s...', batch_count, task_id)
                    if not writer:
                        writer = csv.DictWriter(
                            tmp_file, fieldnames=data[0].keys(), quotechar='"', quoting=csv.QUOTE_NONNUMERIC,
                        )
                    if processed_records <= page_size:
                        # Write header only for page 1
                        writer.writeheader()
                    writer.writerows(data)

                    # Allow the possibility of %1 records added to/dropped from the view during the export
                    # The %1 margin is just an estimate, there is no proved calculation for it
                    if view_data['end_page'] is None and 1.01 >= progress >= 0.99:
                        progress = 1.0

                    # update task progress
                    DataExportTask.set_progress(task_id, progress)
                else:
                    log.warning('CSV Export: batch %s of task %s is empty!', batch_count, task_id)

        view_data['processed_batches'] = batch_count

        if view_data['start_page'] == 1 and view_data['end_page'] is None:
            log.info('CSV Export: uploading file for task %s (no partial files).', task_id)
            partial_tag = 0
        else:
            log.info('CSV Export: uploading partial file for task %s.', task_id)
            partial_tag = view_data['start_page']
        _upload_file_to_storage(
            tmp_file.name, filename, DataExportTask.get_task(task_id=task_id).tenant.id, partial_tag=partial_tag,
        )

        if view_data['start_page'] == 1 and view_data['end_page'] is None:
            log.info('CSV Export: file uploaded successfully for task %s (no partial files).', task_id)
        elif view_data['end_page']:
            log.info('CSV Export: partial file uploaded successfully for task %s.', task_id)
            view_data['start_page'] = view_data['end_page'] + 1
            view_data['end_page'] = None
            fully_completed = False
        else:
            _combine_partial_files(task_id, filename, DataExportTask.get_task(task_id=task_id).tenant.id)

    finally:
        try:
            os.remove(tmp_file.name)
            log.info('CSV Export: temporary file removed for task %s...', task_id)
        except Exception as exc:
            log.info('CSV Export: failed to remove temporary file for task %s: %s', task_id, str(exc))

    return fully_completed


def export_data_to_csv(
    task_id: int, url: str, view_data: dict, fx_permission_info: dict, filename: str
) -> bool:
    """
    Mock view with given view params and write JSON response to CSV

    :param task_id: task id will be used to update progress
    :type task_id: int
    :param url: view url will be used to mock view and get response
    :type url: str
    :param view_data: required data for mocking
    :type view_data: dict
    :param fx_permission_info: contains role and permission info
    :type fx_permission_info: dict
    :param filename: filename for generated CSV
    :type filename: str

    :return: True if export fully completed, False if partially completed
    :rtype: bool
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
    query_params['page'] = view_data['start_page']
    view_instance = _get_view_class_instance(view_data.get('path', ''))
    page_size = 100
    view_pagination_class = view_instance.view_class.pagination_class

    if view_pagination_class and hasattr(view_pagination_class, 'max_page_size'):
        page_size = view_pagination_class.max_page_size or page_size

    query_params['page_size'] = page_size
    url_with_query_str = f'{url}?{urlencode(query_params)}'

    # Ensure the filename ends with .csv
    if not filename.endswith('.csv'):
        filename += '.csv'

    view_data.update({
        'url': url_with_query_str,
        'page_size': page_size,
        'view_instance': view_instance,
        'site': Site.objects.get(domain=view_data['site_domain'])
    })

    return _generate_csv_with_tracked_progress(
        task_id, fx_permission_info, view_data, filename, view_instance
    )


def generate_file_url(storage_path: str) -> str:
    """
    Generate a signed URL if default storage is S3, otherwise return the normal URL.

    :param storage_path: The path to the file in storage.
    :type storage_path: str

    :return: Signed or normal URL.
    """
    if not isinstance(default_storage, S3Boto3Storage):
        return default_storage.url(storage_path)

    s3_client = boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )
    return s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': settings.AWS_STORAGE_BUCKET_NAME, 'Key': storage_path},
        HttpMethod='GET',
        ExpiresIn=3600
    )


def get_exported_file_url(fx_task: DataExportTask) -> Optional[str]:
    """Get file URL"""
    if fx_task.status == fx_task.STATUS_COMPLETED:
        storage_path = os.path.join(get_storage_dir(fx_task.tenant.id, CSV_EXPORT_UPLOAD_DIR), fx_task.filename)
        if default_storage.exists(storage_path):
            return generate_file_url(storage_path)
        log.warning('CSV Export: file not found for completed task %s: %s', fx_task.id, storage_path)
    return None


def log_export_task(fx_task_id: int, async_task: Any, continue_job: bool = False) -> None:
    """Log export task details"""
    msg = 'continuation' if continue_job else 'initial'
    if async_task.status != 'FAILURE':
        log.info(
            'CSV Export: %s task %s scheduled as celery task %s. Now [%s]',
            msg,
            fx_task_id,
            async_task.id,
            async_task.status,
        )
    else:
        log.error(
            'CSV Export: %s task %s scheduling failed as celery task %s. Error: %s',
            msg,
            fx_task_id,
            async_task.id,
            str(async_task.result),
        )
