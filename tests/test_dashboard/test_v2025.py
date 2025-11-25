import copy
# pylint: disable=too-many-lines
from typing import OrderedDict
from unittest.mock import patch

import ddt
import pytest
from common.djangoapps.student.models import CourseAccessRole, CourseEnrollment
from deepdiff import DeepDiff
from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from eox_nelp.course_experience.models import FeedbackCourse
from eox_tenant.models import Route, TenantConfig
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from rest_framework import status as http_status
from rest_framework.test import APIRequestFactory, APITestCase
from rest_framework.utils.serializer_helpers import ReturnList

from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.models import (
    ConfigAccessControl,
)
from tests.fixture_helpers import get_user1_fx_permission_info


class BaseTestViewMixin(APITestCase):
    """Base test view mixin"""
    VIEW_NAME = 'view name is not set!'

    def setUp(self):
        """Setup"""
        self.view_name = self.VIEW_NAME
        self.url_args = []
        self.staff_user = 2

    @property
    def url(self):
        """Get the URL"""
        return reverse(self.view_name, args=self.url_args)

    def login_user(self, user_id):
        """Helper to login user"""
        self.client.force_login(get_user_model().objects.get(id=user_id))

    def _get_request(self):
        """Helper to get the request"""
        factory = APIRequestFactory()
        request = factory.get(self.url)
        request.query_params = {}
        request.user = get_user_model().objects.get(id=self.staff_user)
        request.fx_permission_info = get_user1_fx_permission_info()
        request.fx_permission_info['user'] = request.user
        return request


@pytest.mark.usefixtures('base_data')
@ddt.ddt
class TestCategoriesView(BaseTestViewMixin):
    """Tests for CategoriesView"""
    VIEW_NAME = 'fx_dashboard:courses-categories'

    default_test_data = {
        'category1': {'label': {}, 'courses': []},
        'category3': {'label': {}, 'courses': []},
        'category4': {'label': {}, 'courses': []},
    }
    default_test_data_list = [
        {'id': 'category1', 'label': {}, 'courses': [], 'courses_display_names': {}},
        {'id': 'category4', 'label': {}, 'courses': [], 'courses_display_names': {}},
        {'id': 'category3', 'label': {}, 'courses': [], 'courses_display_names': {}},
    ]
    default_test_data_sorting = ['category1', 'category4', 'category3']
    default_post_payload = {
        'tenant_id': 1,
        'label': {'en': 'New Category'},
    }

    @classmethod
    def setUpTestData(cls):
        """Initialize the test case"""
        super().setUpTestData()
        tenant = TenantConfig.objects.get(id=1)
        tenant.lms_configs[settings.FX_COURSE_CATEGORY_CONFIG_KEY] = {
            'categories': copy.deepcopy(cls.default_test_data),
            'sorting': copy.deepcopy(cls.default_test_data_sorting),
        }
        tenant.save()
        ConfigAccessControl.objects.create(
            key_name=settings.FX_COURSE_CATEGORY_CONFIG_KEY,
            path=settings.FX_COURSE_CATEGORY_CONFIG_KEY,
            writable=True,
        )

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    @patch('futurex_openedx_extensions.dashboard.v2025.CategoriesView.verify_one_tenant_id_provided')
    def test_get_success(self, mock_verify_one_tenant):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        mock_verify_one_tenant.return_value = 1

        response = self.client.get(self.url, data={'optional_field_tags': 'courses'})
        self.assertEqual(response.status_code, http_status.HTTP_200_OK, response.data)

        assert not DeepDiff(
            response.data,
            self.default_test_data_list,
            ignore_type_in_groups=[(dict, OrderedDict),(list, ReturnList)],
            ignore_order=False,
        )
        mock_verify_one_tenant.assert_called_once()

    def test_post_success(self):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        expected_result = copy.deepcopy(self.default_post_payload.copy())
        expected_result['id'] = 'category2'

        response = self.client.post(self.url, data=self.default_post_payload, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data, expected_result)

    @ddt.data('label', 'tenant_id')
    def test_post_not_valid_missing_payload_field(self, required_field_name):
        """Verify that post returns 400 when a required field is missing"""
        self.login_user(self.staff_user)

        payload = copy.deepcopy(self.default_post_payload.copy())
        payload.pop(required_field_name)
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(str(response.data[required_field_name][0]), 'This field is required.')

    def test_post_invalid_label_empty_dict(self):
        """Verify that post returns 400 when label is an empty dictionary"""
        self.login_user(self.staff_user)
        payload = copy.deepcopy(self.default_post_payload)
        payload['label'] = {}

        response = self.client.post(self.url, data=payload, format='json')

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST, response.data)
        assert 'label' in response.data
        assert str(response.data['label'][0]) == 'Label must be a non-empty dictionary.'

    @patch('futurex_openedx_extensions.dashboard.s2025.CourseCategories')
    def test_post_fx_coded_exception(self, mock_course_categories):
        """Verify that post returns 400 and formatted error when FXCodedException is raised"""
        self.login_user(self.staff_user)

        error_code = FXExceptionCodes.UNKNOWN_ERROR.value if hasattr(FXExceptionCodes, 'UNKNOWN_ERROR') else 'E000'
        mock_manager = mock_course_categories.return_value
        mock_manager.add_category.side_effect = FXCodedException(error_code, 'Some error')

        response = self.client.post(self.url, data=self.default_post_payload, format='json')

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST, response.data)
        assert isinstance(response.data, dict)
        reason = response.data.get('reason') or response.data.get('detail') or ''
        assert '(' in reason and ')' in reason
        assert 'Some error' in reason


@pytest.mark.usefixtures('base_data')
@ddt.ddt
class TestCategoryDetailView(BaseTestViewMixin):
    """Tests for CategoryDetailView"""
    VIEW_NAME = 'fx_dashboard:courses-category-detail'

    default_test_data = {
        'category1': {'label': {}, 'courses': []},
        'category3': {'label': {}, 'courses': []},
        'category4': {'label': {}, 'courses': []},
    }
    default_test_data_sorting = ['category1', 'category4', 'category3']

    @classmethod
    def setUpTestData(cls):
        """Initialize the test case"""
        super().setUpTestData()
        tenant = TenantConfig.objects.get(id=1)
        tenant.lms_configs[settings.FX_COURSE_CATEGORY_CONFIG_KEY] = {
            'categories': copy.deepcopy(cls.default_test_data),
            'sorting': copy.deepcopy(cls.default_test_data_sorting),
        }
        tenant.save()
        ConfigAccessControl.objects.create(
            key_name=settings.FX_COURSE_CATEGORY_CONFIG_KEY,
            path=settings.FX_COURSE_CATEGORY_CONFIG_KEY,
            writable=True,
        )

    def setUp(self):
        """Ensure URL points to a specific category"""
        super().setUp()
        self.url_args = ['category1']

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    @patch('futurex_openedx_extensions.dashboard.v2025.CategoryDetailView.verify_one_tenant_id_provided')
    def test_get_success(self, mock_verify_one_tenant):
        """Verify that GET returns the correct category representation"""
        self.login_user(self.staff_user)
        mock_verify_one_tenant.return_value = 1

        # request courses/display names to ensure method fields included
        response = self.client.get(self.url, data={'optional_field_tags': 'courses'})
        self.assertEqual(response.status_code, http_status.HTTP_200_OK, response.data)

        expected = {
            'id': 'category1',
            'label': {},
            'courses': [],
            'courses_display_names': {},
        }
        self.assertEqual(response.data, expected)
        mock_verify_one_tenant.assert_called_once()

    @patch('futurex_openedx_extensions.dashboard.v2025.CategoryDetailView.verify_one_tenant_id_provided')
    @patch('futurex_openedx_extensions.dashboard.v2025.CourseCategories')
    def test_get_fx_coded_exception(self, mock_course_categories, mock_verify_one_tenant):
        """Verify that GET surfaces FXCodedException in a formatted way"""
        self.login_user(self.staff_user)
        mock_verify_one_tenant.return_value = 1

        error_code = FXExceptionCodes.UNKNOWN_ERROR.value if hasattr(FXExceptionCodes, 'UNKNOWN_ERROR') else 'E000'
        mock_manager = mock_course_categories.return_value
        mock_manager.verify_category_name_exists.side_effect = FXCodedException(error_code, 'Category not found')

        response = self.client.get(self.url, data={'optional_field_tags': 'courses'})

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        assert isinstance(response.data, dict)
        reason = response.data.get('reason') or response.data.get('detail') or ''
        assert '(' in reason and ')' in reason
        assert 'Category not found' in reason

    @patch('futurex_openedx_extensions.dashboard.v2025.CategoryDetailView.verify_one_tenant_id_provided')
    @patch('futurex_openedx_extensions.dashboard.v2025.CourseCategories')
    def test_patch_success(self, mock_course_categories, mock_verify_one_tenant):
        """Verify that PATCH updates the category label successfully"""
        self.login_user(self.staff_user)
        mock_verify_one_tenant.return_value = 1

        mock_manager = mock_course_categories.return_value
        mock_manager.verify_category_name_exists.return_value = None

        payload = {'label': {'en': 'Updated'}}
        response = self.client.patch(self.url, data=payload, format='json')

        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)
        mock_manager.verify_category_name_exists.assert_called_once_with('category1')
        mock_manager.save.assert_called_once()

    @patch('futurex_openedx_extensions.dashboard.v2025.CategoryDetailView.verify_one_tenant_id_provided')
    def test_patch_invalid_label_empty_dict(self, mock_verify_one_tenant):
        """Verify that PATCH with empty label returns validation error"""
        self.login_user(self.staff_user)
        mock_verify_one_tenant.return_value = 1
        payload = {'label': {}}
        response = self.client.patch(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        assert 'label' in response.data
        assert str(response.data['label'][0]) == 'Label must be a non-empty dictionary.'

    @patch('futurex_openedx_extensions.dashboard.v2025.CategoryDetailView.verify_one_tenant_id_provided')
    @patch('futurex_openedx_extensions.dashboard.v2025.CourseCategories')
    def test_patch_fx_coded_exception(self, mock_course_categories, mock_verify_one_tenant):
        """Verify that PATCH surfaces FXCodedException in a formatted way"""
        self.login_user(self.staff_user)
        mock_verify_one_tenant.return_value = 1

        error_code = FXExceptionCodes.UNKNOWN_ERROR.value if hasattr(FXExceptionCodes, 'UNKNOWN_ERROR') else 'E000'
        mock_manager = mock_course_categories.return_value
        mock_manager.verify_category_name_exists.return_value = None
        mock_manager.set_courses_for_category.side_effect = FXCodedException(error_code, 'Some error')

        payload = {'courses': ['course-v1:ORG1+3+3']}
        response = self.client.patch(self.url, data=payload, format='json')

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        assert isinstance(response.data, dict)
        reason = response.data.get('reason') or response.data.get('detail') or ''
        assert '(' in reason and ')' in reason, response.data
        assert 'Some error' in reason

    @patch('futurex_openedx_extensions.dashboard.v2025.CategoryDetailView.verify_one_tenant_id_provided')
    @patch('futurex_openedx_extensions.dashboard.v2025.CourseCategories')
    def test_delete_success(self, mock_course_categories, mock_verify_one_tenant):
        """Verify that DELETE removes the category successfully"""
        self.login_user(self.staff_user)
        mock_verify_one_tenant.return_value = 1

        mock_manager = mock_course_categories.return_value
        mock_manager.remove_category.return_value = None

        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)
        mock_manager.remove_category.assert_called_once_with('category1')
        mock_manager.save.assert_called_once()

    @patch('futurex_openedx_extensions.dashboard.v2025.CategoryDetailView.verify_one_tenant_id_provided')
    @patch('futurex_openedx_extensions.dashboard.v2025.CourseCategories')
    def test_delete_fx_coded_exception(self, mock_course_categories, mock_verify_one_tenant):
        """Verify that DELETE surfaces FXCodedException in a formatted way"""
        self.login_user(self.staff_user)
        mock_verify_one_tenant.return_value = 1

        error_code = FXExceptionCodes.UNKNOWN_ERROR.value if hasattr(FXExceptionCodes, 'UNKNOWN_ERROR') else 'E000'
        mock_manager = mock_course_categories.return_value
        mock_manager.remove_category.side_effect = FXCodedException(error_code, 'Some error')

        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        assert isinstance(response.data, dict)
        reason = response.data.get('reason') or response.data.get('detail') or ''
        assert '(' in reason and ')' in reason
        assert 'Some error' in reason
