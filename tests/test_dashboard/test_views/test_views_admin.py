"""Test views for the dashboard app - admin"""
# pylint: disable=duplicate-code
import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import resolve
from rest_framework import status as http_status

from futurex_openedx_extensions.dashboard import urls
from futurex_openedx_extensions.helpers.exceptions import FXExceptionCodes
from futurex_openedx_extensions.helpers.models import DataExportTask
from futurex_openedx_extensions.helpers.permissions import (
    FXHasTenantCourseAccess,
    IsAnonymousOrSystemStaff,
    IsSystemStaff,
)
from tests.test_dashboard.test_mixins import BaseTestViewMixin


class TestVersionInfoView(BaseTestViewMixin):
    """Tests for VersionInfoView"""
    VIEW_NAME = 'fx_dashboard:version-info'

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        view_func, _, _ = resolve(self.url)
        view_class = view_func.view_class
        self.assertEqual(view_class.permission_classes, [IsSystemStaff])

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_success(self):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        with patch('futurex_openedx_extensions.__version__', new='0.1.dummy'):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(json.loads(response.content), {'version': '0.1.dummy'})


class TestDataExportTasksView(BaseTestViewMixin):
    """Tests for DataExportTasksView"""
    view_actions = ['detail', 'list']

    def set_action(self, action, task_id=1):
        """Set the viewname and client method"""
        self.view_name = f'fx_dashboard:data-export-tasks-{action}'
        self.url_args = []
        if action == 'detail':
            self.url_args = [task_id]

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        registry = {}
        for _, viewset, basename in urls.export_router.registry:
            registry[basename] = viewset

        for action in self.view_actions:
            self.set_action(action)
            view_class = registry['data-export-tasks']
            self.assertEqual(view_class.permission_classes, [FXHasTenantCourseAccess])

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        for action in self.view_actions:
            self.set_action(action)
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_non_staff_user(self):
        """Verify that user without required role can not access view."""
        for action in self.view_actions:
            self.set_action(action)
            learner_user = get_user_model().objects.get(id=45)
            self.login_user(learner_user.id)
            response = self.client.get(self.url, {})
            self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_list_success(self):
        """Verify view for list"""
        self.set_action('list')
        request = self._get_request()
        self.login_user(request.user.id)
        task = DataExportTask.objects.create(
            user=request.user,
            status=DataExportTask.STATUS_COMPLETED,
            view_name='exported_files_data',
            filename='test.csv',
            progress=1.0,
            tenant_id=1
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], task.id)

    def test_list_user_can_only_view_own_tasks(self):
        """Verify view for list - that the user can only view his tasks"""
        self.set_action('list')
        user1 = get_user_model().objects.get(id=4)
        user2 = get_user_model().objects.get(id=10)
        self.login_user(user1.id)
        user1_task1 = DataExportTask.objects.create(
            user=user1,
            status=DataExportTask.STATUS_COMPLETED,
            view_name='exported_files_data',
            filename='test1.csv',
            progress=1.0,
            tenant_id=1
        )
        user1_task2 = DataExportTask.objects.create(
            user=user1,
            status=DataExportTask.STATUS_COMPLETED,
            view_name='exported_files_data',
            filename='test2.csv',
            progress=1.0,
            tenant_id=1
        )
        # user1 shouldnt have access to the following task as it is created by user2
        DataExportTask.objects.create(
            user=user2,
            status=DataExportTask.STATUS_COMPLETED,
            view_name='exported_files_data',
            filename='test3.csv',
            progress=1.0,
            tenant_id=1
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
        self.assertEqual(response.data['results'][0]['id'], user1_task2.id)
        self.assertEqual(response.data['results'][1]['id'], user1_task1.id)

    def test_patch_success(self):
        """Verify view for update"""
        user = get_user_model().objects.get(id=4)
        self.login_user(user.id)
        task = DataExportTask.objects.create(
            user=user,
            status=DataExportTask.STATUS_COMPLETED,
            view_name='exported_files_data',
            filename='test.csv',
            progress=1.0,
            notes='dummy',
            tenant_id=1
        )
        self.set_action('detail', task.id)
        new_notes = 'dummy new'
        response = self.client.patch(
            self.url,
            data={'notes': new_notes},
            format='json',
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        task.refresh_from_db()
        self.assertEqual(task.notes, new_notes)
        self.assertEqual(response.data['id'], task.id)
        self.assertEqual(response.data['notes'], new_notes)

    def test_patch_user_can_only_edit_own_tasks(self):
        """Verify that the user can only update his tasks"""
        user1 = get_user_model().objects.get(id=4)
        user2 = get_user_model().objects.get(id=10)
        self.login_user(user1.id)
        user1_task = DataExportTask.objects.create(
            user=user1,
            status=DataExportTask.STATUS_COMPLETED,
            view_name='exported_files_data',
            filename='test1.csv',
            progress=1.0,
            tenant_id=1
        )
        self.assertEqual(user1_task.notes, '')
        self.set_action('detail', user1_task.id)
        response = self.client.patch(
            self.url,
            data={'notes': 'new notes'},
            format='json',
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        user1_task.refresh_from_db()
        self.assertEqual(user1_task.notes, 'new notes')

        # user1 shouldnt be able to update following as it is created by user2
        user2_task = DataExportTask.objects.create(
            user=user2,
            status=DataExportTask.STATUS_COMPLETED,
            view_name='exported_files_data',
            filename='test3.csv',
            progress=1.0,
            tenant_id=1
        )
        self.set_action('detail', user2_task.id)
        response = self.client.patch(
            self.url,
            data={'notes': 'new notes update'},
            format='json',
        )
        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)

    def test_patch_for_non_writable_fields(self):
        """Verify view for non writable fields."""
        user = get_user_model().objects.get(id=4)
        self.login_user(user.id)
        task = DataExportTask.objects.create(
            user=user,
            status=DataExportTask.STATUS_COMPLETED,
            view_name='exported_files_data',
            filename='test.csv',
            progress=1.0,
            notes='dummy',
            tenant_id=1
        )
        self.set_action('detail', task.id)
        response = self.client.patch(
            self.url,
            data={'filename': 'newname.csv', 'user': 45},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], task.id)
        # verify filename and user didn't update.
        self.assertEqual(response.data['filename'], 'test.csv')
        self.assertEqual(response.data['user_id'], user.id)

    def test_retrieve_success(self):
        """Verify view for retrieve"""
        user = get_user_model().objects.get(id=4)
        self.login_user(user.id)
        task = DataExportTask.objects.create(
            user=user,
            status=DataExportTask.STATUS_COMPLETED,
            view_name='exported_files_data',
            filename='test.csv',
            progress=1.0,
            notes='dummy',
            tenant_id=1
        )
        self.set_action('detail', task.id)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['id'], task.id)

    def test_not_allowed_methods(self):
        """Verify view for not allowed methods."""
        user = get_user_model().objects.get(id=4)
        self.login_user(user.id)
        task = DataExportTask.objects.create(
            user=user,
            status=DataExportTask.STATUS_COMPLETED,
            view_name='exported_files_data',
            filename='test.csv',
            progress=1.0,
            notes='dummy',
            tenant_id=1
        )
        self.set_action('detail', task.id)
        response = self.client.put(
            self.url,
            data={'notes': 'new'},
            format='json',
        )
        self.assertEqual(response.status_code, 405)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 405)
        self.set_action('list', task.id)
        response = self.client.post(self.url, data={
            'user': 1,
            'view_name': 'fake',
            'filename': 'fake.csv',
            'notes': 'fake notes',
            'tenant_id': 1
        })
        self.assertEqual(response.status_code, 405)


@pytest.mark.usefixtures('base_data')
class TestAccessibleTenantsInfoView(BaseTestViewMixin):
    """Tests for AccessibleTenantsInfoView"""
    VIEW_NAME = 'fx_dashboard:accessible-info'

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        view_func, _, _ = resolve(self.url)
        view_class = view_func.view_class
        self.assertEqual(view_class.permission_classes, [IsAnonymousOrSystemStaff])

    @patch('futurex_openedx_extensions.dashboard.views.admin.get_user_by_username_or_email')
    def test_success(self, mock_get_user):
        """Verify that the view returns the correct response"""
        mock_get_user.return_value = get_user_model().objects.get(username='user4')
        response = self.client.get(self.url, data={'username_or_email': 'dummy, the user loader function is mocked'})
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertDictEqual(json.loads(response.content), {
            '1': {
                'lms_root_url': 'https://s1.sample.com',
                'studio_root_url': 'https://studio.example.com',
                'platform_name': 's1 platform name',
                'logo_image_url': '',
            },
            '2': {
                'lms_root_url': 'https://s2.sample.com',
                'studio_root_url': 'https://studio.example.com',
                'platform_name': '', 'logo_image_url': ''
            },
            '7': {
                'lms_root_url': 'https://s7.sample.com',
                'studio_root_url': 'https://studio.example.com',
                'platform_name': '', 'logo_image_url': ''
            },
        })

    @patch('futurex_openedx_extensions.dashboard.views.admin.get_user_by_username_or_email')
    def test_no_username_or_email(self, mock_get_user):
        """Verify that the view returns the correct response"""
        mock_get_user.side_effect = get_user_model().DoesNotExist()
        response = self.client.get(self.url)
        mock_get_user.assert_called_once_with(None)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertDictEqual(json.loads(response.content), {})

    def test_not_existing_username_or_email(self):
        """Verify that the view returns the correct response"""
        response = self.client.get(self.url, data={'username_or_email': 'dummy'})
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertDictEqual(json.loads(response.content), {})


@pytest.mark.usefixtures('base_data')
class TestAccessibleTenantsInfoViewV2(BaseTestViewMixin):
    """Tests for AccessibleTenantsInfoViewv2"""
    VIEW_NAME = 'fx_dashboard:accessible-info-v2'

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        view_func, _, _ = resolve(self.url)
        view_class = view_func.view_class
        self.assertEqual(view_class.permission_classes, [FXHasTenantCourseAccess])

    @patch('futurex_openedx_extensions.dashboard.views.admin.get_user_by_username_or_email')
    def test_success(self, mock_get_user):
        """Verify that the view returns the correct response"""
        mock_get_user.return_value = get_user_model().objects.get(username='user4')
        self.login_user(self.staff_user)
        response = self.client.get(self.url, data={'username_or_email': 'dummy, the user loader function is mocked'})
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertDictEqual(json.loads(response.content), {
            '1': {
                'lms_root_url': 'https://s1.sample.com',
                'studio_root_url': 'https://studio.example.com',
                'platform_name': 's1 platform name',
                'logo_image_url': '',
            },
            '2': {
                'lms_root_url': 'https://s2.sample.com',
                'studio_root_url': 'https://studio.example.com',
                'platform_name': '', 'logo_image_url': ''
            },
            '7': {
                'lms_root_url': 'https://s7.sample.com',
                'studio_root_url': 'https://studio.example.com',
                'platform_name': '', 'logo_image_url': ''
            },
        })

        self.login_user(5)
        response = self.client.get(self.url, data={'username_or_email': 'dummy'})
        self.assertEqual(
            response.status_code,
            http_status.HTTP_403_FORBIDDEN,
            f'Expected 403 for non staf users, but got {response.status_code}'
        )

    @patch('futurex_openedx_extensions.dashboard.views.admin.get_user_by_username_or_email')
    def test_no_username_or_email(self, mock_get_user):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        mock_get_user.side_effect = get_user_model().DoesNotExist()
        response = self.client.get(self.url)
        mock_get_user.assert_called_once_with(None)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertDictEqual(json.loads(response.content), {})

    def test_not_existing_username_or_email(self):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url, data={'username_or_email': 'dummy'})
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertDictEqual(json.loads(response.content), {})


class TestExcludedTenantsView(BaseTestViewMixin):
    """Tests for ExcludedTenantsView"""
    VIEW_NAME = 'fx_dashboard:excluded-tenants'

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        view_func, _, _ = resolve(self.url)
        view_class = view_func.view_class
        self.assertEqual(view_class.permission_classes, [IsSystemStaff])

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_success(self):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(json.loads(response.content), {
            '4': [FXExceptionCodes.TENANT_HAS_NO_LMS_BASE.value],
            '5': [FXExceptionCodes.TENANT_COURSE_ORG_FILTER_NOT_VALID.value],
            '6': [FXExceptionCodes.TENANT_HAS_NO_SITE.value],
        })
