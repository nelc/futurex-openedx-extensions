"""Upload tests"""
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from futurex_openedx_extensions.helpers.upload import rewrite_legacy_cloudfront_asset_urls, upload_file


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


@override_settings(LMS_ROOT_URL='https://lms.example.com')
def test_rewrite_legacy_cloudfront_asset_urls():
    """Legacy dashboard asset URLs are served from the LMS. Other URLs stay put."""
    legacy = (
        'https://d3ihhyw2bnk9f1.cloudfront.net/fx_dashboard/399/config_files/'
        '_default_image_logo_image-484ffd3e.png'
    )
    values = {
        'logo_image_url': legacy,
        'theme': {'favicon_url': legacy + '?v=1'},
        'keep': 'https://dmm8r1zm81d17.cloudfront.net/maintenance.html',
    }

    rewritten = rewrite_legacy_cloudfront_asset_urls(values)

    serve = 'https://lms.example.com/api/fx/assets/v1/serve/399/_default_image_logo_image-484ffd3e.png'
    assert rewritten['logo_image_url'] == serve
    assert rewritten['theme']['favicon_url'] == serve
    assert rewritten['keep'] == values['keep']
