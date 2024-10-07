"""
This module contains utils for tasks.
"""
import csv
import os
import tempfile
from typing import Any, List, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.urls import resolve
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes

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


def _get_mocked_request(url: str, user: Any, fx_info: dict, query_params: dict) -> Request:
    """Create mocked request"""
    factory = APIRequestFactory()
    mocked_request = factory.get(url)
    mocked_request.user = user
    mocked_request.fx_permission_info = fx_info
    mocked_request.query_params = query_params
    return mocked_request


def _get_response_data(mocked_request: Any, kwargs: dict, view_instance: Any) -> List[dict]:
    """Get response with mocked request"""
    response = view_instance(mocked_request, **kwargs)
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
    return data


def _upload_file_to_storage(local_file_path: str, storage_path: str) -> str:
    """
    Upload a file to the default storage (e.g., S3).

    :param local_file_path: Path to the local file to upload
    :param storage_path: Path in the storage where the file should be saved
    :return: The path of the uploaded file
    """
    with open(local_file_path, 'rb') as file:
        content_file = ContentFile(file.read())
        default_storage.save(storage_path, content_file)
    return storage_path


def export_data_to_csv(url: str, view_data: dict, fx_permission_info: dict, filename: str) -> str:
    """
    Mock view with given view params and write JSON response to CSV

    :param url: view url
    :param view_data: required data for mocking
    :param fx_permission_info: contains role and permission info
    :param filename: filename for generated CSV

    :return: generated filename
    """
    user_id = fx_permission_info.get('user_id')
    user = _get_user(user_id)
    # restore user in fx_permission_info
    fx_permission_info.update({'user': user})

    view_instance = _get_view_class_instance(view_data.get('path', ''))
    mocked_request = _get_mocked_request(url, user, fx_permission_info, view_data.get('query_params', {}))
    data = _get_response_data(mocked_request, view_data.get('kwargs', {}), view_instance)

    # Ensure the filename ends with .csv
    if not filename.endswith('.csv'):
        filename += '.csv'

    # Create a temporary file
    with tempfile.NamedTemporaryFile(mode='w', newline='', encoding='utf-8', delete=False) as tmp_file:
        if len(data):
            writer = csv.DictWriter(tmp_file, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)

    storage_path = os.path.join(settings.FX_DATA_EXPORT_DIR_NAME, filename)
    _upload_file_to_storage(tmp_file.name, storage_path)

    # Clean up the temporary file
    os.remove(tmp_file.name)
    return storage_path
