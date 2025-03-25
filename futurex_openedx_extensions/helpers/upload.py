"""Upload helpers"""
import os
import uuid
from typing import Any

from django.conf import settings
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from storages.backends.s3boto3 import S3Boto3Storage

from futurex_openedx_extensions.helpers.constants import CONFIG_FILES_UPLOAD_DIR


def get_storage_dir(tenant_id: int, dir_name: str) -> str:
    """Return storage dir"""
    return os.path.join(settings.FX_DASHBOARD_STORAGE_DIR, f'{str(tenant_id)}/{dir_name}')


def upload_file(storage_path: str, file: str | File, is_private: bool = False) -> str:
    """
    Uploads a file to storage and returns the storage path.

    :param storage_path: The path to save the file in the storage system.
    :param file: The file to upload. Can be either a local file path or a file object from a request.
    :param is_private: Whether the file should be uploaded as private (default: False).
    :returns uploaded file URL
    """
    if isinstance(file, str):
        # local file to upload
        with open(file, 'rb') as f:
            content_file = ContentFile(f.read())
            default_storage.save(storage_path, content_file)
    else:
        # file object to upload
        directory = os.path.dirname(storage_path)
        if not default_storage.exists(directory):
            default_storage.save(directory + '/.empty', ContentFile(''))
        with default_storage.open(storage_path, 'wb') as f:
            for chunk in file.chunks():
                f.write(chunk)
        default_storage.delete(directory + '/.empty')

    if is_private and isinstance(default_storage, S3Boto3Storage):
        default_storage.bucket.Object(storage_path).Acl().put(ACL='private')

    return default_storage.url(storage_path)


def get_tenant_asset_dir(tenant_asset: Any, filename: str) -> str:
    """Custom upload path for tenant asset files"""
    file_extension = os.path.splitext(filename)[1]
    short_uuid = uuid.uuid4().hex[:8]
    file_name = f'{tenant_asset.slug}-{short_uuid}{file_extension}'
    return os.path.join(get_storage_dir(tenant_asset.tenant_id, CONFIG_FILES_UPLOAD_DIR), file_name)
