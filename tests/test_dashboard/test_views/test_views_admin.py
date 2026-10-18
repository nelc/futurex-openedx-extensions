"""Test views for the dashboard app - admin"""
# pylint: disable=duplicate-code
import hashlib
import hmac
import json
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from django.urls import resolve
from rest_framework import status as http_status

from futurex_openedx_extensions.dashboard import urls
from futurex_openedx_extensions.dashboard.views.admin import anonymous_lookup_key
from futurex_openedx_extensions.helpers.exceptions import FXExceptionCodes
from futurex_openedx_extensions.helpers.models import DataExportTask
from futurex_openedx_extensions.helpers.permissions import (
    FXHasTenantCourseAccess,
    IsAnonymousOrSystemStaff,
    IsSystemStaff,
)
from futurex_openedx_extensions.helpers.throttles import AnonymousLookupThrottle
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


@pytest.mark.usefixtures('base_data', 'cache_testing')
class TestAccessibleTenantsInfoThrottleAndLog(BaseTestViewMixin):
    """ADR 0009 addendum F2, option A: the anonymous lookup keeps its answer, and gains a rate limit and a log"""
    VIEW_NAME = 'fx_dashboard:accessible-info'

    def test_view_is_throttled_and_its_rate_comes_from_the_setting(self):
        """The throttle class is wired, and reads FX_ANONYMOUS_LOOKUP_THROTTLE_RATE"""
        view_class = resolve(self.url)[0].view_class
        assert view_class.throttle_classes == [AnonymousLookupThrottle]
        with override_settings(FX_ANONYMOUS_LOOKUP_THROTTLE_RATE='7/hour'):
            assert AnonymousLookupThrottle().get_rate() == '7/hour'

    @override_settings(FX_ANONYMOUS_LOOKUP_THROTTLE_RATE='3/minute')
    def test_anonymous_callers_are_limited_per_client_address(self):
        """The fourth call of one address within the window is 429 and logged; another address is unaffected"""
        statuses = [self.client.get(self.url, data={'username_or_email': 'dummy'}).status_code for _ in range(3)]
        assert statuses == [http_status.HTTP_200_OK] * 3
        with self.assertLogs('futurex_openedx_extensions.anonymous_lookup', level='WARNING') as logs:
            refused = self.client.get(self.url, data={'username_or_email': 'dummy'})
        assert refused.status_code == http_status.HTTP_429_TOO_MANY_REQUESTS
        assert 'client=127.0.0.1' in logs.output[0] and 'dummy' not in logs.output[0]
        other = self.client.get(self.url, data={'username_or_email': 'dummy'}, REMOTE_ADDR='10.1.2.3')
        assert other.status_code == http_status.HTTP_200_OK

    @override_settings(FX_ANONYMOUS_LOOKUP_THROTTLE_RATE='1/minute')
    def test_system_staff_is_not_limited(self):
        """Only anonymous callers are limited"""
        self.login_user(self.staff_user)
        for _ in range(3):
            assert self.client.get(self.url, data={'username_or_email': 'dummy'}).status_code == http_status.HTTP_200_OK

    @patch('futurex_openedx_extensions.dashboard.views.admin.get_user_by_username_or_email')
    def test_the_answer_is_unchanged_and_the_lookup_is_logged_without_the_value(self, mock_get_user):
        """Same body as before; one record with a hash of the key, the tenant count and no username or email"""
        mock_get_user.return_value = get_user_model().objects.get(username='user4')
        with self.assertLogs('futurex_openedx_extensions.accessible_info_access', level='INFO') as logs:
            response = self.client.get(self.url, data={'username_or_email': 'user4@example.com'})
        assert response.status_code == http_status.HTTP_200_OK
        assert sorted(response.json()) == ['1', '2', '7']
        assert len(logs.output) == 1
        assert 'tenants=3' in logs.output[0] and 'anonymous=True' in logs.output[0]
        assert 'user4' not in logs.output[0] and 'example.com' not in logs.output[0]

    def test_an_unknown_user_is_logged_too_and_answers_empty(self):
        """The record for a miss says tenants=0, and the answer is the same empty object"""
        with self.assertLogs('futurex_openedx_extensions.accessible_info_access', level='INFO') as logs:
            response = self.client.get(self.url)
        assert response.json() == {}
        assert 'tenants=0' in logs.output[0]

    def test_the_logged_key_is_keyed_so_a_candidate_list_cannot_confirm_a_guess(self):
        """N2: the key is an HMAC under the environment's secret, not a bare hash of the value"""
        value = 'Someone@Example.com'
        plain = hashlib.sha256(b'someone@example.com').hexdigest()[:12]
        expected = hmac.new(b'test-only-lookup-salt', b'someone@example.com', hashlib.sha256).hexdigest()[:12]
        assert anonymous_lookup_key(' Someone@example.COM ') == anonymous_lookup_key(value) == expected != plain
        with override_settings(FX_ANONYMOUS_LOOKUP_LOG_SALT='another-environment'):
            assert anonymous_lookup_key(value) not in (expected, plain)
        assert anonymous_lookup_key(None) == anonymous_lookup_key('')
        with self.assertLogs('futurex_openedx_extensions.accessible_info_access', level='INFO') as logs:
            self.client.get(self.url, data={'username_or_email': value})
        assert f'key={expected} ' in logs.output[0] and plain not in logs.output[0]

    @patch('futurex_openedx_extensions.dashboard.views.admin.get_user_by_username_or_email')
    def test_an_unset_salt_fails_loudly_before_anything_is_looked_up(self, mock_get_user):
        """No default secret (R-FALLBACK-1): unset or empty refuses the lookup, discloses nothing and logs nothing"""
        for salt in (None, ''):
            with override_settings(FX_ANONYMOUS_LOOKUP_LOG_SALT=salt):
                with self.assertNoLogs('futurex_openedx_extensions.accessible_info_access', level='INFO'):
                    with pytest.raises(ImproperlyConfigured, match='FX_ANONYMOUS_LOOKUP_LOG_SALT'):
                        self.client.get(self.url, data={'username_or_email': 'user4@example.com'})
        with override_settings():
            del settings.FX_ANONYMOUS_LOOKUP_LOG_SALT
            with pytest.raises(ImproperlyConfigured):
                anonymous_lookup_key('x')
        mock_get_user.assert_not_called()


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
