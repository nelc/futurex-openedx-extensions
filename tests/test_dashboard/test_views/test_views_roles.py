"""Test views for the dashboard app - roles"""
# pylint: disable=duplicate-code
import json
from unittest.mock import patch

import ddt
from deepdiff import DeepDiff
from django.contrib.auth import get_user_model
from django.urls import resolve
from rest_framework import status as http_status

from futurex_openedx_extensions.dashboard import urls
from futurex_openedx_extensions.dashboard.views.roles import UserRolesManagementView
from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.permissions import FXHasTenantAllCoursesAccess, FXHasTenantCourseAccess
from tests.fixture_helpers import get_test_data_dict
from tests.test_dashboard.test_mixins import BaseTestViewMixin


@ddt.ddt
class TestMyRolesView(BaseTestViewMixin):
    """Tests for MyRolesView"""
    VIEW_NAME = 'fx_dashboard:my-roles'

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        view_func, _, _ = resolve(self.url)
        view_class = view_func.view_class
        self.assertEqual(view_class.permission_classes, [FXHasTenantCourseAccess])

    def test_success(self):
        """Verify that the view returns the correct response"""
        self.login_user(3)
        expected_result = {
            'user_id': 3,
            'email': 'user3@example.com',
            'username': 'user3',
            'national_id': '11223344556677',
            'full_name': '',
            'alternative_full_name': '',
            'is_system_staff': False,
            'global_roles': [],
            'tenants': {
                '1': {
                    'tenant_roles': ['staff'],
                    'course_roles': {
                        'course-v1:ORG1+3+3': ['instructor'],
                        'course-v1:ORG1+4+4': ['instructor'],
                    },
                },
            },
        }
        response = self.client.get(self.url)
        data = json.loads(response.content)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertFalse(DeepDiff(data, expected_result))


@ddt.ddt
class TestUserRolesManagementView(BaseTestViewMixin):
    """Tests for UserRolesManagementView for GET list"""
    def set_action(self, action):
        """Set the action"""
        self.view_name = f'fx_dashboard:user-roles-{action}'
        if action == 'detail':
            self.url_args = ['user4']

    def test_dispatch_is_non_atomic(self):
        """Verify that the view has the correct dispatch method"""
        dispatch_method = UserRolesManagementView.dispatch
        is_non_atomic = getattr(dispatch_method, '_non_atomic_requests', False)
        self.assertTrue(
            is_non_atomic,
            'dispatch method should be decorated with non_atomic_requests. atomic is used internally when needed'
        )

    @ddt.data('list', 'detail')
    def test_permission_classes(self, action):
        """Verify that the view has the correct permission classes"""
        self.set_action(action)

        registry = {}
        for _, viewset, basename in urls.roles_router.registry:
            registry[basename] = viewset
        view_class = registry['user-roles']
        self.assertEqual(view_class.permission_classes, [FXHasTenantAllCoursesAccess])

    @ddt.data('list', 'detail')
    def test_unauthorized(self, action):
        """Verify that the view returns 403 when the user is not authenticated"""
        self.set_action(action)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_bad_course_id(self):
        """Verify that the view returns 400 when the course ID is invalid"""
        self.set_action('list')

        self.login_user(self.staff_user)
        response = self.client.get(self.url, data={'only_course_ids': 'course-v1:ORG1+4+4,invalid-course-id'})
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertIn('Invalid course ID format: invalid-course-id', response.data['detail'])

    def test_success_list(self):
        """Verify that the view returns the correct response when list action is used"""
        self.set_action('list')

        self.login_user(self.staff_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        test_data = get_test_data_dict()
        assert len(response.data['results']) == len(test_data)
        for user_roles in response.data['results']:
            username = user_roles['username']
            assert username in test_data
            del test_data[username]

        assert not test_data

    def test_success_detail(self):
        """Verify that the view returns the correct response when detail action is used"""
        self.set_action('detail')

        self.login_user(self.staff_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        assert response.data['tenants'] == {
            1: {'tenant_roles': ['instructor'], 'course_roles': {'course-v1:ORG1+4+4': ['staff']}},
            2: {'tenant_roles': ['instructor'], 'course_roles': {'course-v1:ORG3+1+1': ['staff']}},
            7: {'tenant_roles': ['instructor'], 'course_roles': {'course-v1:ORG3+1+1': ['staff']}}
        }

    @patch('futurex_openedx_extensions.dashboard.views.roles.add_course_access_roles')
    def test_post_success(self, mock_add_users):
        """Verify that the view returns 201 for POST"""
        self.set_action('list')

        self.login_user(self.staff_user)
        mock_add_users.return_value = {
            'failed': [],
            'added': ['shadinaif', 'ahmad@gmail.com'],
            'updated': [10098765],
            'not_updated': [],
        }
        response = self.client.post(
            self.url,
            data={
                'tenant_ids': [9],
                'users': ['shadinaif', 'ahmad@gmail.com', 10098765],
                'role': 'staff',
                'tenant_wide': False,
                'course_ids': ['course-v1:ORG1+TOPIC+2024', 'course-v1:ORG1+TOPIC2+2024'],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(json.loads(response.content), mock_add_users.return_value)

    @patch('futurex_openedx_extensions.dashboard.views.roles.add_course_access_roles')
    @ddt.data(
        ('tenant_ids', 'not list', True, 'tenant_ids must be a list of integers'),
        ('tenant_ids', [1, 'not int'], True, 'tenant_ids must be a list of integers'),
        ('users', 'not list', True, 'users must be a list'),
        ('role', ['not str'], True, 'role must be a string'),
        ('tenant_wide', 'not int', True, 'tenant_wide must be an integer flag'),
        ('course_ids', 'not list', False, 'course_ids must be a list'),
    )
    @ddt.unpack
    def test_post_validation_error(
        self, key, value, is_required, error_message, mock_add_users
    ):  # pylint: disable=too-many-arguments
        """Verify that the view returns 400 for POST when the payload is invalid"""
        error_message = f'({FXExceptionCodes.INVALID_INPUT.value}) {error_message}'
        self.set_action('list')
        self.login_user(self.staff_user)
        data = {
            'tenant_ids': [9],
            'users': ['shadinaif', 'ahmad@gmail.com', 10098765],
            'role': 'staff',
            'tenant_wide': False,
            'course_ids': ['course-v1:ORG1+TOPIC+2024', 'course-v1:ORG1+TOPIC2+2024'],
        }

        data.pop(key)
        mock_add_users.return_value = {}
        response = self.client.post(self.url, data=data, format='json')
        if is_required:
            self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
            self.assertEqual(response.data, {
                'reason': f"Missing required parameter: '{key}'", 'details': {}
            })
        else:
            self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)

        data.update({key: value})
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {'reason': error_message, 'details': {}})

    @patch('futurex_openedx_extensions.dashboard.views.roles.add_course_access_roles')
    def test_post_add_validation_error(self, mock_add_users):
        """Verify that the view returns 400 for POST when the payload is invalid"""
        self.set_action('list')
        self.login_user(self.staff_user)
        data = {
            'tenant_ids': [9],
            'users': ['shadinaif', 'ahmad@gmail.com', 10098765],
            'role': 'staff',
            'tenant_wide': False,
            'course_ids': ['course-v1:ORG1+TOPIC+2024', 'course-v1:ORG1+TOPIC2+2024'],
        }

        mock_add_users.side_effect = FXCodedException(
            code=FXExceptionCodes.INVALID_INPUT,
            message='an internal validation error!'
        )
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data,
            {'reason': f'({FXExceptionCodes.INVALID_INPUT.value}) an internal validation error!', 'details': {}}
        )

    def test_put_bad_username(self):
        """Verify that the view returns 404 when the given username is invalid"""
        self.set_action('detail')
        self.url_args = ['invalid_username']

        self.login_user(self.staff_user)
        response = self.client.put(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data, {
            'reason': '(1001) User with username/email (invalid_username) does not exist!', 'details': {}
        })

    @patch('futurex_openedx_extensions.dashboard.views.roles.update_course_access_roles')
    @patch('futurex_openedx_extensions.dashboard.views.roles.UserRolesManagementView.verify_username')
    def test_put_failed(self, mock_verify_username, mock_update_users):
        """Verify that the view returns 400 when the fails for any reason"""
        self.set_action('detail')

        self.login_user(self.staff_user)
        mock_verify_username.return_value = {
            'user': get_user_model().objects.get(id=4),
            'key_type': cs.USER_KEY_TYPE_USERNAME,
            'error_code': None,
            'error_message': None,
        }
        mock_update_users.return_value = {
            'error_code': '999',
            'error_message': 'the error message',
        }
        response = self.client.put(self.url)

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {
            'reason': '(999) the error message', 'details': {}
        })

    @patch('futurex_openedx_extensions.dashboard.views.roles.update_course_access_roles')
    @patch('futurex_openedx_extensions.dashboard.views.roles.UserRolesManagementView.verify_username')
    def test_put_success(self, mock_verify_username, mock_update_users):
        """Verify that the view returns 204 for PUT"""
        self.set_action('detail')

        self.login_user(self.staff_user)
        mock_update_users.return_value = {
            'error_code': None,
            'error_message': None,
        }
        mock_verify_username.return_value = {
            'user': get_user_model().objects.get(id=4),
            'key_type': cs.USER_KEY_TYPE_USERNAME,
            'error_code': None,
            'error_message': None,
        }
        response = self.client.put(self.url, data={'the data': 'whatever, the function is mocked'})
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['user_id'], 4)

    @patch('futurex_openedx_extensions.dashboard.views.roles.get_user_by_key')
    def test_delete_bad_username(self, mock_get_user):
        """Verify that the view returns 400 when the user tries to delete their own roles"""
        self.set_action('detail')

        mock_get_user.return_value = {
            'user': None,
            'key_type': cs.USER_KEY_TYPE_NOT_ID,
            'error_code': '999',
            'error_message': 'the error message',
        }
        self.url_args = ['invalid_username']

        self.login_user(self.staff_user)
        response = self.client.delete(self.url + '?tenant_ids=1,2')
        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data, {'reason': '(999) the error message', 'details': {}})

    @patch('futurex_openedx_extensions.dashboard.views.roles.get_user_by_key')
    def test_delete_missing_required_parameter(self, _):
        """Verify that the view returns 400 when there is a missing required-parameter"""
        self.set_action('detail')

        self.login_user(self.staff_user)
        response = self.client.delete(self.url + '?tenant_ids_not_sent_in_query_params=x')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {'reason': "Missing required parameter: 'tenant_ids'", 'details': {}})

    @patch('futurex_openedx_extensions.dashboard.views.roles.get_user_by_key')
    @patch('futurex_openedx_extensions.dashboard.views.roles.delete_course_access_roles')
    def test_delete_success(self, mock_delete_user, mock_get_user):
        """Verify that the view returns 400 when the user tries to delete their own roles"""
        self.set_action('detail')

        mock_get_user.return_value = {
            'user': get_user_model().objects.get(id=4),
            'key_type': cs.USER_KEY_TYPE_ID,
            'error_code': None,
            'error_message': None,
        }

        self.login_user(self.staff_user)
        response = self.client.delete(self.url + '?tenant_ids=1,2')
        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)
        self.assertIsNone(response.data)
        mock_delete_user.call_args_list[0][1].pop('caller')
        mock_delete_user.assert_called_once_with(tenant_ids=[1, 2], user=mock_get_user.return_value['user'])

    @patch('futurex_openedx_extensions.dashboard.views.roles.get_user_by_key')
    @patch('futurex_openedx_extensions.dashboard.views.roles.delete_course_access_roles')
    def test_delete_no_roles_found_for_user(self, mock_delete_user, mock_get_user):
        """Verify that the view returns 404 when no roles are found for the user"""
        self.set_action('detail')

        mock_get_user.return_value = {
            'user': get_user_model().objects.get(id=3),
            'key_type': cs.USER_KEY_TYPE_ID,
            'error_code': None,
            'error_message': None,
        }
        mock_delete_user.side_effect = FXCodedException(999, 'the error message')
        self.login_user(self.staff_user)
        response = self.client.delete(self.url + '?tenant_ids=1')
        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)
        self.assertDictEqual(response.data, {'reason': 'the error message', 'details': {}})
