"""Test views for the dashboard app - misc"""
# pylint: disable=duplicate-code
import os
from unittest.mock import Mock, patch

import pytest
from deepdiff import DeepDiff
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from eox_tenant.models import TenantConfig
from rest_framework import status as http_status

from futurex_openedx_extensions.dashboard import urls
from futurex_openedx_extensions.helpers.constants import ALLOWED_FILE_EXTENSIONS
from futurex_openedx_extensions.helpers.exceptions import FXCodedException
from futurex_openedx_extensions.helpers.models import TenantAsset
from futurex_openedx_extensions.helpers.permissions import FXHasTenantAllCoursesAccess
from tests.test_dashboard.test_mixins import BaseTestViewMixin


@pytest.mark.usefixtures('base_data')
class TestTenantInfoView(BaseTestViewMixin):
    """Tests for TenantInfoView"""
    VIEW_NAME = 'fx_dashboard:tenant-info'

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        self.url_args = ['1']
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_no_permission(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        self.url_args = ['1']
        self.login_user(11)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_success(self):
        """Verify that the view returns the correct response"""
        self.url_args = ['1']
        self.login_user(3)
        expected_result = {
            'tenant_id': 1,
            'lms_root_url': 'https://s1.sample.com',
            'studio_root_url': 'https://studio.example.com',
            'platform_name': 's1 platform name',
            'logo_image_url': '',
        }
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertFalse(DeepDiff(response.json(), expected_result))


@pytest.mark.usefixtures('base_data')
class FileUploadView(BaseTestViewMixin):
    """Tests for FileUploadView"""
    VIEW_NAME = 'fx_dashboard:file-upload'

    @patch('futurex_openedx_extensions.dashboard.views.misc.uuid.uuid4')
    @patch('futurex_openedx_extensions.dashboard.views.misc.get_storage_dir')
    def test_success(self, mocked_storage_dir, mocked_uuid4):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        mocked_storage_dir.return_value = 'some-dummy-dir'
        mocked_uuid4.return_value = Mock(hex='12345678abcdef12')
        test_file = SimpleUploadedFile('test.png', b'file_content', content_type='image/png')
        data = {
            'file': test_file,
            'slug': 'test-slug',
            'tenant_id': 1
        }
        expected_file_name = 'test-slug-12345678.png'
        expected_storage_path = f'some-dummy-dir/{expected_file_name}'
        response = self.client.post('/api/fx/file/v1/upload/', data, format='multipart')
        assert response.status_code == http_status.HTTP_201_CREATED
        assert response.json()['uuid'] == '12345678'
        assert response.json()['url'] == default_storage.url(expected_storage_path)
        assert default_storage.exists(expected_storage_path)
        default_storage.delete(expected_storage_path)

    @patch('futurex_openedx_extensions.dashboard.views.misc.get_storage_dir')
    def test_failure(self, mocked_storage_dir):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        response = self.client.post(
            '/api/fx/file/v1/upload/',
            data={
                'file': SimpleUploadedFile('test.png', b'file_content', content_type='image/png'),
                'slug': 'test-slug',
                'tenant_id': 10000000
            },
            format='multipart'
        )
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(str(response.data['tenant_id'][0]), 'Tenant with ID 10000000 does not exist.')

        mocked_storage_dir.side_effect = FXCodedException(code=0, message='Some error in file saving.')
        response = self.client.post(
            '/api/fx/file/v1/upload/',
            data={
                'file': SimpleUploadedFile('test.png', b'file_content', content_type='image/png'),
                'slug': 'test-slug',
                'tenant_id': 1
            },
            format='multipart'
        )
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['reason'], 'Some error in file saving.')

        response = self.client.post(
            '/api/fx/file/v1/upload/',
            data={
                'file': SimpleUploadedFile(
                    'file-with-invalid-extension.invalid', b'file_content', content_type='image/png'
                ),
                'slug': 'test-slug',
                'tenant_id': 1
            },
            format='multipart'
        )
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['reason'], f'Invalid file type. Allowed types are {ALLOWED_FILE_EXTENSIONS}.')

    @patch('futurex_openedx_extensions.dashboard.views.misc.uuid.uuid4')
    @patch('futurex_openedx_extensions.dashboard.views.misc.get_storage_dir')
    def test_file_upload_for_tenant_permission(self, mocked_storage_dir, mocked_uuid4):
        """Verify that the view returns the correct response"""
        self.login_user(1)
        mocked_storage_dir.return_value = 'some-dummy-dir'
        mocked_uuid4.return_value = Mock(hex='12345678abcdef12')
        test_file = SimpleUploadedFile('test.png', b'this is a test image content', content_type='image/png')
        expected_storage_path = 'some-dummy-dir/test-slug-12345678.png'
        data = {
            'file': test_file,
            'slug': 'test-slug',
        }

        data['tenant_id'] = 1
        response = self.client.post(self.url, data, format='multipart')
        assert response.status_code == http_status.HTTP_201_CREATED
        assert response.json()['url'] == default_storage.url(expected_storage_path)
        default_storage.delete(expected_storage_path)

        data['tenant_id'] = 6
        response = self.client.post(self.url, data, format='multipart')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(str(response.data['tenant_id'][0]), 'User does not have have required access for tenant (6).')


@pytest.mark.usefixtures('base_data')
class TestTenantAssetsManagementView(BaseTestViewMixin):
    """Tests for TenantAssetsManagementView"""
    view_actions = ['list']
    fake_storage_dir = 'some-dummy-dir'

    def set_action(self, action):
        """Set the viewname and client method"""
        self.view_name = f'fx_dashboard:tenant-assets-{action}'
        self.url_args = []

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        registry = {}
        for _, viewset, basename in urls.tenant_assets_router.registry:
            registry[basename] = viewset

        for action in self.view_actions:
            self.set_action(action)
            view_class = registry['tenant-assets']
            self.assertEqual(view_class.permission_classes, [FXHasTenantAllCoursesAccess])

    @patch('futurex_openedx_extensions.helpers.upload.uuid.uuid4')
    @patch('futurex_openedx_extensions.helpers.upload.get_storage_dir')
    def test_create_success(self, mocked_storage_dir, mocked_uuid4):
        """Verify that the view returns the correct response"""
        self.set_action('list')
        self.login_user(3)
        mocked_storage_dir.return_value = self.fake_storage_dir
        mocked_uuid4.return_value = Mock(hex='12345678abcdef12')
        test_file = SimpleUploadedFile('test.png', b'file_content', content_type='image/png')
        data = {
            'file': test_file,
            'slug': 'test-slug',
            'tenant_id': 1
        }
        expected_storage_path = f'{self.fake_storage_dir}/test-slug-12345678.png'
        response = self.client.post(self.url, data, format='multipart')
        created_asset = TenantAsset.objects.get(slug='test-slug', tenant=1)
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)
        self.assertEqual(response.data['file_url'], '/api/fx/assets/v1/serve/1/test-slug-12345678.png')
        self.assertEqual(response.data['slug'], 'test-slug')
        self.assertEqual(response.data['updated_by'], 3)
        self.assertEqual(response.data['tenant_id'], 1)
        self.assertEqual(response.data['id'], created_asset.id)
        self.assertTrue(default_storage.exists(expected_storage_path))

        another_file = SimpleUploadedFile('testanother.png', b'file_another_content', content_type='image/png')
        data = {
            'file': another_file,
            'slug': 'test-slug',
            'tenant_id': 1
        }
        mocked_uuid4.return_value = Mock(hex='11223344abcdef12')
        storage_path_file2 = f'{self.fake_storage_dir}/test-slug-11223344.png'
        response = self.client.post(self.url, data, format='multipart')
        self.assertEqual(
            response.data['id'],
            1,
            'Failed, adding another file with existing slug should not create a new db record.'
        )
        self.assertEqual(response.data['file_url'], '/api/fx/assets/v1/serve/1/test-slug-11223344.png')
        self.assertTrue(default_storage.exists(storage_path_file2))

    def test_create_failure(self):
        """Verify that the view returns 400 for user without access and for invlaid file"""
        self.set_action('list')
        self.login_user(3)
        response = self.client.post(
            self.url,
            data={
                'file': SimpleUploadedFile(
                    'file-with-invalid-extension.invalid', b'file_content', content_type='image/png'
                ),
                'slug': 'does-not-matter',
                'tenant': 1
            },
            format='multipart'
        )
        self.assertEqual(
            response.status_code,
            http_status.HTTP_400_BAD_REQUEST,
            'Failed, 400 response is expected as file type is invalid.'
        )
        self.assertEqual(
            str(response.data['file'][0]),
            f'Invalid file type. Allowed types are {ALLOWED_FILE_EXTENSIONS}.'
        )

        data = {
            'file': SimpleUploadedFile('abcd.png', b'does not matter', content_type='image/png'),
            'slug': 'does-not-matter',
            'tenant_id': 3
        }
        response = self.client.post(self.url, data, format='multipart')
        self.assertEqual(
            response.status_code,
            http_status.HTTP_400_BAD_REQUEST,
            'Failed, 400 response is expected as user does not have tenant access'
        )
        self.assertEqual(str(response.data['tenant_id'][0]), 'User does not have have required access for tenant (3).')

    @patch('futurex_openedx_extensions.helpers.upload.get_storage_dir')
    def test_list_success(self, mocked_storage_dir):
        """Verify that user can only view accessible tenant assets"""
        self.set_action('list')
        mocked_storage_dir.return_value = self.fake_storage_dir
        tenant1_sample1 = TenantAsset.objects.create(
            slug='tenant1-sample1',
            tenant_id=1,
            file=SimpleUploadedFile('sample11.png', b'dumy11', content_type='image/png'),
            updated_by_id=3
        )
        tenant1_sample2 = TenantAsset.objects.create(
            slug='tenant1-sample2',
            tenant_id=1,
            file=SimpleUploadedFile('sample12.png', b'dummy12', content_type='image/png'),
            updated_by_id=3
        )
        tenant1_sample3 = TenantAsset.objects.create(
            slug='tenant1-sample3-by-another-user',
            tenant_id=1,
            file=SimpleUploadedFile('sample13.png', b'dummy13', content_type='image/png'),
            updated_by_id=1
        )
        TenantAsset.objects.create(
            slug='tenant4-sample1',
            tenant_id=2,
            file=SimpleUploadedFile('sample41.png', b'dummy41', content_type='image/png'),
            updated_by_id=3
        )
        self.login_user(3)
        response = self.client.get(self.url)
        self.assertEqual(
            len(response.data['results']),
            3,
            'Failed, user should only have access to accessible tenants.',
        )
        self.assertEqual(response.data['results'][0]['id'], tenant1_sample3.id)
        self.assertEqual(response.data['results'][1]['id'], tenant1_sample2.id)
        self.assertEqual(response.data['results'][2]['id'], tenant1_sample1.id)

        tenant1_sample1.slug = '_private-tenant1-sample1'
        tenant1_sample1.save()
        response = self.client.get(self.url)
        self.assertEqual(
            len(response.data['results']),
            2,
            'Private asset records shouldn\'t be accessible by non system-staff users.',
        )

        self.login_user(1)
        response = self.client.get(self.url)
        self.assertEqual(
            len(response.data['results']),
            TenantAsset.objects.count(),
            'System-staff users should have access to all asset records.',
        )

    @patch('futurex_openedx_extensions.helpers.upload.get_storage_dir')
    def test_list_success_template_tenant(self, mocked_storage_dir):
        """Verify that only staff-users can view assets in the template tenant"""
        self.set_action('list')
        mocked_storage_dir.return_value = self.fake_storage_dir
        self.assertFalse(TenantConfig.objects.filter(external_key=settings.FX_TEMPLATE_TENANT_SITE).exists())
        template_tenant = TenantConfig.objects.create(external_key=settings.FX_TEMPLATE_TENANT_SITE)

        self.assertEqual(TenantAsset.objects.count(), 0, 'bad test data, no assets should exist yet')
        TenantAsset.objects.create(
            slug='sample',
            tenant_id=template_tenant.id,
            file=SimpleUploadedFile('sample.png', b'dummy data', content_type='image/png'),
            updated_by_id=self.staff_user,
        )

        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(
            len(response.data['results']),
            1,
            'Failed, staff user should be able to see the asset records in the template tenant!',
        )

    def tearDown(self):
        """Delete created files"""
        if default_storage.exists(self.fake_storage_dir):
            _, files = default_storage.listdir(self.fake_storage_dir)
            for file_name in files:
                default_storage.delete(os.path.join(self.fake_storage_dir, file_name))
            os.rmdir(self.fake_storage_dir)
