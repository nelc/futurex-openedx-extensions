"""
This module contains utils for tasks.
"""
import csv
import os
from typing import Any, List, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
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


def export_data_to_csv(url: str, view_data: dict, fx_permission_info: dict, filename: str) -> str:
    """
    Mock view with given view params and write JSON response to CSV

    :param url: view url
    :param view_data: required data for mocking
    :param fx_permission_info: contains role and permission info
    :param filename: filename for generated CSV

    :return: generated filename
    """
    user_id = fx_permission_info.get('user')
    user = _get_user(user_id)

    # fx_permisssion info expect user instead of user id
    fx_permission_info.update({'user': user})
    view_instance = _get_view_class_instance(view_data.get('path', ''))
    mocked_request = _get_mocked_request(url, user, fx_permission_info, view_data.get('query_params', {}))
    data = _get_response_data(mocked_request, view_data.get('kwargs', {}), view_instance)

    # Ensure the filename ends with .csv
    if not filename.endswith('.csv'):
        filename += '.csv'

    csv_file_path = os.path.join(settings.MEDIA_ROOT, filename)
    with open(csv_file_path, mode='w', newline='', encoding='utf-8') as file:
        if len(data):
            writer = csv.DictWriter(file, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
    return filename
