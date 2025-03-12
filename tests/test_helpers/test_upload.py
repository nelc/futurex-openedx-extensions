"""Upload tests"""
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile

from futurex_openedx_extensions.helpers.upload import upload_file


def test_upload_file_with_dir_creation():
    """
    Test the behavior of the `upload_file` function when handling directory creation
    and file uploads.

    This test verifies the following scenarios:
    1. If the specified directory does not exist, it is created along with the file upload.
    2. If the specified directory already exists, the file is uploaded without issues.
    """
    file_obj = SimpleUploadedFile('test1.txt', b'file content', content_type='text/plain')
    uploaded_url = upload_file('storage/file1.txt', file_obj)
    assert uploaded_url is not None, 'Dir does not exist, create new dir along with file.'

    file_obj = SimpleUploadedFile('test2.txt', b'file content', content_type='text/plain')
    uploaded_url = upload_file('storage/file2.txt', file_obj)
    assert uploaded_url is not None, 'Dir already exists, create new file.'
    assert default_storage.exists('storage/file1.txt')
    assert default_storage.exists('storage/file2.txt')

    default_storage.delete('storage/file1.txt')
    default_storage.delete('storage/file2.txt')
    default_storage.delete('storage')
