"""Tests for futurex_openedx_extensions.dashboard.views.files"""
import shutil

import ddt
import pytest
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status as http_status

from futurex_openedx_extensions.helpers import constants as cs
from tests.test_dashboard.test_mixins import BaseTestViewMixin


@ddt.ddt
@pytest.mark.usefixtures('base_data')
class TestTenantAssetServeView(BaseTestViewMixin):
    """Tests for TenantAssetServeView"""
    VIEW_NAME = 'fx_dashboard:tenant-asset-serve'

    def setUp(self):
        super().setUp()
        self.tenant_id = 1
        self.filename = 'asset-12345678.png'
        self.file_content = b'png-bytes-here'
        self.storage_path = '/'.join([
            settings.FX_DASHBOARD_STORAGE_DIR.rstrip('/'),
            str(self.tenant_id),
            cs.CONFIG_FILES_UPLOAD_DIR,
            self.filename,
        ])
        default_storage.save(self.storage_path, SimpleUploadedFile(self.filename, self.file_content))

    def tearDown(self):
        shutil.rmtree(settings.FX_DASHBOARD_STORAGE_DIR, ignore_errors=True)

    def _url(self, tenant_id, filename):
        """Reverse the serve URL for the given tenant and filename"""
        return reverse(self.VIEW_NAME, kwargs={'tenant_id': tenant_id, 'filename': filename})

    def test_serves_existing_file_anonymous(self):
        """Anonymous request gets the file content with cache headers and no auth required"""
        response = self.client.get(self._url(self.tenant_id, self.filename))
        assert response.status_code == http_status.HTTP_200_OK
        assert b''.join(response.streaming_content) == self.file_content
        assert response['Content-Type'] == 'image/png'
        assert response['Cache-Control'] == 'public, max-age=86400'

    def test_404_when_file_missing(self):
        """Missing file under the valid config_files prefix returns 404"""
        response = self.client.get(self._url(self.tenant_id, 'does-not-exist.png'))
        assert response.status_code == http_status.HTTP_404_NOT_FOUND

    def test_csv_export_path_not_servable(self):
        """A CSV in the export dir must not be reachable; URL pattern hard-codes config_files/"""
        csv_path = '/'.join([
            settings.FX_DASHBOARD_STORAGE_DIR.rstrip('/'),
            str(self.tenant_id),
            cs.CSV_EXPORT_UPLOAD_DIR,
            'leak.csv',
        ])
        default_storage.save(csv_path, SimpleUploadedFile('leak.csv', b'secret data'))
        response = self.client.get(self._url(self.tenant_id, 'leak.csv'))
        assert response.status_code == http_status.HTTP_404_NOT_FOUND

    @ddt.data('.', '..')
    def test_dot_filename_rejected(self, filename):
        """Literal `.` or `..` as filename slips past the regex; view's invariant guard catches it"""
        response = self.client.get(self._url(self.tenant_id, filename))
        assert response.status_code == http_status.HTTP_404_NOT_FOUND

    def test_non_integer_tenant_id_404(self):
        """URL regex requires \\d+ for tenant_id; non-digit yields a routing 404"""
        response = self.client.get('/api/fx/assets/v1/serve/abc/asset.png')
        assert response.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.usefixtures('base_data')
class TestTenantAssetUploadAndServeIntegration(BaseTestViewMixin):
    """Round-trip: upload a tenant asset, then fetch it via the serve endpoint."""
    upload_view_name = 'fx_dashboard:tenant-assets-list'

    def tearDown(self):
        shutil.rmtree(settings.FX_DASHBOARD_STORAGE_DIR, ignore_errors=True)

    def test_upload_then_serve_round_trip(self):
        """file_url returned by the upload view must resolve via the serve view to the same bytes"""
        self.login_user(self.staff_user)
        file_content = b'round-trip-bytes'
        upload = self.client.post(
            reverse(self.upload_view_name),
            data={
                'file': SimpleUploadedFile('mylogo.png', file_content, content_type='image/png'),
                'slug': 'mylogo',
                'tenant_id': 1,
            },
            format='multipart',
        )
        assert upload.status_code == http_status.HTTP_201_CREATED

        file_url = upload.data['file_url']
        assert file_url.startswith('/api/fx/assets/v1/serve/1/mylogo-')
        assert file_url.endswith('.png')

        self.client.logout()
        served = self.client.get(file_url)
        assert served.status_code == http_status.HTTP_200_OK
        assert b''.join(served.streaming_content) == file_content
        assert served['Content-Type'] == 'image/png'

    def test_reupload_same_slug_yields_new_cachebust_url(self):
        """Re-uploading under the same slug produces a new URL with a new uuid suffix"""
        self.login_user(self.staff_user)

        def upload(content):
            return self.client.post(
                reverse(self.upload_view_name),
                data={
                    'file': SimpleUploadedFile('logo.png', content, content_type='image/png'),
                    'slug': 'logo',
                    'tenant_id': 1,
                },
                format='multipart',
            )

        first = upload(b'v1')
        second = upload(b'v2')
        assert first.status_code == http_status.HTTP_201_CREATED
        assert second.status_code == http_status.HTTP_201_CREATED
        assert second.data['file_url'] != first.data['file_url']

        self.client.logout()
        served = self.client.get(second.data['file_url'])
        assert served.status_code == http_status.HTTP_200_OK
        assert b''.join(served.streaming_content) == b'v2'
