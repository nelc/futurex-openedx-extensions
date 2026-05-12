"""Test views for the dashboard app - categories"""
# pylint: disable=duplicate-code
import copy
from collections import OrderedDict
from unittest.mock import patch

import ddt
import pytest
from deepdiff import DeepDiff
from django.conf import settings
from eox_tenant.models import TenantConfig
from rest_framework import status as http_status
from rest_framework.utils.serializer_helpers import ReturnList

from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.models import ConfigAccessControl
from tests.test_dashboard.test_mixins import BaseTestViewMixin, MockPatcherMixin


@ddt.ddt
class TestCategoriesView(MockPatcherMixin, BaseTestViewMixin):
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

    patching_config = {
        'one_tenant': (
            'futurex_openedx_extensions.dashboard.views.categories.FXViewRoleInfoMixin.verify_one_tenant_id_provided', {
                'return_value': 1,
            }
        ),
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

    @ddt.data('0', '1')
    def test_get_success(self, verify_course_ids):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)

        response = self.client.get(
            self.url, data={'optional_field_tags': 'courses', 'verify_course_ids': verify_course_ids},
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK, response.data)

        assert not DeepDiff(
            response.data,
            self.default_test_data_list,
            ignore_type_in_groups=[(dict, OrderedDict), (list, ReturnList)],
            ignore_order=False,
        )
        self.mocks['one_tenant'].assert_called_once()

    @ddt.data(
        ('0', http_status.HTTP_200_OK),
        ('1', http_status.HTTP_400_BAD_REQUEST),
    )
    @ddt.unpack
    def test_get_with_non_existing_courses(self, verify_course_ids, expected_status):
        """Verify that GET returns the correct category representation"""
        self.login_user(self.staff_user)

        tenant = TenantConfig.objects.get(id=1)
        tenant.lms_configs[settings.FX_COURSE_CATEGORY_CONFIG_KEY]['categories']['category1']['courses'] = [
            'course-v1:ORG1+3+3',
            'course-v1:ORG1+99+99',
        ]
        tenant.save()

        response = self.client.get(
            self.url, data={'optional_field_tags': 'courses', 'verify_course_ids': verify_course_ids},
        )
        self.assertEqual(response.status_code, expected_status, response.data)

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

    @patch('futurex_openedx_extensions.dashboard.serializers.CourseCategories')
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
        assert reason == '(0) Some error'


@pytest.mark.usefixtures('base_data')
@ddt.ddt
class TestCategoryDetailView(MockPatcherMixin, BaseTestViewMixin):
    """Tests for CategoryDetailView"""
    VIEW_NAME = 'fx_dashboard:courses-category-detail'

    default_test_data = {
        'category1': {'label': {}, 'courses': []},
        'category3': {'label': {}, 'courses': []},
        'category4': {'label': {}, 'courses': []},
    }
    default_test_data_sorting = ['category1', 'category4', 'category3']

    patching_config = {
        'one_tenant': (
            'futurex_openedx_extensions.dashboard.views.categories.FXViewRoleInfoMixin.verify_one_tenant_id_provided', {
                'return_value': 1,
            }
        ),
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

    def setUp(self):
        """Ensure URL points to a specific category"""
        super().setUp()
        self.url_args = ['category1']

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    @ddt.data('0', '1')
    def test_get_success(self, verify_course_ids):
        """Verify that GET returns the correct category representation"""
        self.login_user(self.staff_user)

        response = self.client.get(self.url, data={
            'optional_field_tags': 'courses',
            'verify_course_ids': verify_course_ids,
        })
        self.assertEqual(response.status_code, http_status.HTTP_200_OK, response.data)

        expected = {
            'id': 'category1',
            'label': {},
            'courses': [],
            'courses_display_names': {},
        }
        self.assertEqual(response.data, expected)
        self.mocks['one_tenant'].assert_called_once()

    @ddt.data(
        ('0', http_status.HTTP_200_OK),
        ('1', http_status.HTTP_400_BAD_REQUEST),
    )
    @ddt.unpack
    def test_get_with_non_existing_courses(self, verify_course_ids, expected_status):
        """Verify that GET returns the correct category representation"""
        self.login_user(self.staff_user)

        tenant = TenantConfig.objects.get(id=1)
        tenant.lms_configs[settings.FX_COURSE_CATEGORY_CONFIG_KEY]['categories']['category1']['courses'] = [
            'course-v1:ORG1+3+3',
            'course-v1:ORG1+99+99',
        ]
        tenant.save()

        response = self.client.get(
            self.url, data={'optional_field_tags': 'courses', 'verify_course_ids': verify_course_ids},
        )
        self.assertEqual(response.status_code, expected_status, response.data)

    @patch('futurex_openedx_extensions.dashboard.views.categories.CourseCategories')
    def test_get_fx_coded_exception(self, mock_course_categories):
        """Verify that GET surfaces FXCodedException in a formatted way"""
        self.login_user(self.staff_user)

        error_code = FXExceptionCodes.UNKNOWN_ERROR.value if hasattr(FXExceptionCodes, 'UNKNOWN_ERROR') else 'E000'
        mock_manager = mock_course_categories.return_value
        mock_manager.verify_category_name_exists.side_effect = FXCodedException(error_code, 'Some error')

        response = self.client.get(self.url, data={'optional_field_tags': 'courses'})

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        assert isinstance(response.data, dict)
        reason = response.data.get('reason') or response.data.get('detail') or ''
        assert reason == '(0) Some error'

    @patch('futurex_openedx_extensions.dashboard.views.categories.CourseCategories')
    def test_patch_success(self, mock_course_categories):
        """Verify that PATCH updates the category label successfully"""
        self.login_user(self.staff_user)

        mock_manager = mock_course_categories.return_value
        mock_manager.verify_category_name_exists.return_value = None

        payload = {'label': {'en': 'Updated'}}
        response = self.client.patch(self.url, data=payload, format='json')

        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)
        mock_manager.verify_category_name_exists.assert_called_once_with('category1')
        mock_manager.save.assert_called_once()

    def test_patch_invalid_label_empty_dict(self):
        """Verify that PATCH with empty label returns validation error"""
        self.login_user(self.staff_user)
        payload = {'label': {}}
        response = self.client.patch(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        assert 'label' in response.data
        assert str(response.data['label'][0]) == 'Label must be a non-empty dictionary.'

    @patch('futurex_openedx_extensions.dashboard.views.categories.CourseCategories')
    def test_patch_fx_coded_exception(self, mock_course_categories):
        """Verify that PATCH surfaces FXCodedException in a formatted way"""
        self.login_user(self.staff_user)

        error_code = FXExceptionCodes.UNKNOWN_ERROR.value if hasattr(FXExceptionCodes, 'UNKNOWN_ERROR') else 'E000'
        mock_manager = mock_course_categories.return_value
        mock_manager.verify_category_name_exists.return_value = None
        mock_manager.set_courses_for_category.side_effect = FXCodedException(error_code, 'Some error')

        payload = {'courses': ['course-v1:ORG1+3+3']}
        response = self.client.patch(self.url, data=payload, format='json')

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        assert isinstance(response.data, dict)
        reason = response.data.get('reason') or response.data.get('detail') or ''
        assert reason == '(0) Some error', response.data

    def test_patch_invalid_courses(self):
        """Verify that PATCH with invalid courses returns validation error"""
        self.login_user(self.staff_user)
        non_existing_course_id = 'course-v1:ORG1+99+99'
        payload = {'courses': [non_existing_course_id]}
        response = self.client.patch(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        assert 'courses' in response.data
        assert str(response.data['courses'][0]).startswith('The following course IDs are invalid: ')

    @patch('futurex_openedx_extensions.dashboard.views.categories.CourseCategories')
    def test_delete_success(self, mock_course_categories):
        """Verify that DELETE removes the category successfully"""
        self.login_user(self.staff_user)

        mock_manager = mock_course_categories.return_value
        mock_manager.remove_category.return_value = None

        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)
        mock_manager.remove_category.assert_called_once_with('category1')
        mock_manager.save.assert_called_once()

    @patch('futurex_openedx_extensions.dashboard.views.categories.CourseCategories')
    def test_delete_fx_coded_exception(self, mock_course_categories):
        """Verify that DELETE surfaces FXCodedException in a formatted way"""
        self.login_user(self.staff_user)

        error_code = FXExceptionCodes.UNKNOWN_ERROR.value if hasattr(FXExceptionCodes, 'UNKNOWN_ERROR') else 'E000'
        mock_manager = mock_course_categories.return_value
        mock_manager.remove_category.side_effect = FXCodedException(error_code, 'Some error')

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        assert isinstance(response.data, dict)
        reason = response.data.get('reason') or response.data.get('detail') or ''
        assert reason == '(0) Some error'


@pytest.mark.usefixtures('base_data')
@ddt.ddt
class TestCategoriesOrderView(BaseTestViewMixin):
    """Tests for CategoriesOrderView"""
    VIEW_NAME = 'fx_dashboard:courses-categories-order'

    default_test_data = {
        'category1': {'label': {}, 'courses': []},
        'category3': {'label': {}, 'courses': []},
        'category4': {'label': {}, 'courses': []},
    }
    default_test_data_sorting = ['category1', 'category4', 'category3']
    default_post_payload = {
        'tenant_id': 1,
        'categories': ['category3', 'category1', 'category4'],
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
        response = self.client.post(self.url, data=self.default_post_payload, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    @patch('futurex_openedx_extensions.dashboard.views.categories.CourseCategories')
    def test_post_success(self, mock_course_categories):
        """Verify that POST updates the categories order successfully"""
        self.login_user(self.staff_user)

        mock_manager = mock_course_categories.return_value
        mock_manager.set_categories_sorting.return_value = None

        response = self.client.post(self.url, data=self.default_post_payload, format='json')

        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)
        mock_manager.set_categories_sorting.assert_called_once_with(['category3', 'category1', 'category4'])
        mock_manager.save.assert_called_once()

    @ddt.data('tenant_id', 'categories')
    def test_post_not_valid_missing_payload_field(self, required_field_name):
        """Verify that post returns 400 when a required field is missing"""
        self.login_user(self.staff_user)

        payload = copy.deepcopy(self.default_post_payload)
        payload.pop(required_field_name)
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(str(response.data[required_field_name][0]), 'This field is required.')

    def test_post_invalid_categories_empty_list(self):
        """Verify that post returns 400 when categories is an empty list"""
        self.login_user(self.staff_user)
        payload = copy.deepcopy(self.default_post_payload)
        payload['categories'] = []

        response = self.client.post(self.url, data=payload, format='json')

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST, response.data)
        assert 'categories' in response.data
        assert str(response.data['categories'][0]) == 'Categories must be a non-empty list.'

    @patch('futurex_openedx_extensions.dashboard.views.categories.CourseCategories')
    def test_post_fx_coded_exception(self, mock_course_categories):
        """Verify that POST surfaces FXCodedException in a formatted way"""
        self.login_user(self.staff_user)

        error_code = FXExceptionCodes.UNKNOWN_ERROR.value if hasattr(FXExceptionCodes, 'UNKNOWN_ERROR') else 'E000'
        mock_manager = mock_course_categories.return_value
        mock_manager.set_categories_sorting.side_effect = FXCodedException(error_code, 'Some error')

        response = self.client.post(self.url, data=self.default_post_payload, format='json')

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        assert isinstance(response.data, dict)
        reason = response.data.get('reason') or response.data.get('detail') or ''
        assert reason == '(0) Some error'


@pytest.mark.usefixtures('base_data')
@ddt.ddt
class TestCourseCategoriesView(BaseTestViewMixin):
    """Tests for CourseCategoriesView"""
    VIEW_NAME = 'fx_dashboard:courses-course-categories'

    default_test_data = {
        'category1': {'label': {}, 'courses': []},
        'category3': {'label': {}, 'courses': []},
        'category4': {'label': {}, 'courses': []},
    }
    default_test_data_sorting = ['category1', 'category4', 'category3']
    default_put_payload = {
        'categories': ['category1', 'category3'],
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

    def setUp(self):
        """Ensure URL points to a specific course"""
        super().setUp()
        self.url_args = ['course-v1:ORG1+3+3']

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.put(self.url, data=self.default_put_payload, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    @patch('futurex_openedx_extensions.dashboard.views.categories.CourseCategories')
    @patch('futurex_openedx_extensions.dashboard.views.categories.get_tenants_by_org')
    def test_put_success(self, mock_get_tenants_by_org, mock_course_categories):
        """Verify that PUT assigns categories to a course successfully"""
        self.login_user(self.staff_user)
        mock_get_tenants_by_org.return_value = [1]

        mock_manager = mock_course_categories.return_value
        mock_manager.set_categories_for_course.return_value = None

        response = self.client.put(self.url, data=self.default_put_payload, format='json')

        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)
        mock_manager.set_categories_for_course.assert_called_once_with('course-v1:ORG1+3+3', ['category1', 'category3'])
        mock_manager.save.assert_called_once()

    def test_put_course_not_found(self):
        """Verify that PUT returns 404 when course is not found or not accessible"""
        self.login_user(self.staff_user)
        self.url_args = ['course-v1:INVALID+999+999']

        response = self.client.put(self.url, data=self.default_put_payload, format='json')

        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)
        assert 'Course not found or access denied' in str(response.data.get('reason') or response.data.get('detail'))

    @patch('futurex_openedx_extensions.dashboard.views.categories.get_tenants_by_org')
    def test_put_multiple_tenants_error(self, mock_get_tenants_by_org):
        """Verify that PUT returns 400 when multiple tenants are found for the course"""
        self.login_user(self.staff_user)
        mock_get_tenants_by_org.return_value = [1, 2]

        response = self.client.put(self.url, data=self.default_put_payload, format='json')

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        assert 'Multiple tenants found' in str(response.data.get('reason') or response.data.get('detail'))

    def test_put_invalid_categories_missing(self):
        """Verify that PUT returns 400 when categories field is missing"""
        self.login_user(self.staff_user)

        response = self.client.put(self.url, data={}, format='json')

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        assert 'categories' in response.data
        assert str(response.data['categories'][0]) == 'This field is required.'

    @patch('futurex_openedx_extensions.dashboard.views.categories.CourseCategories')
    @patch('futurex_openedx_extensions.dashboard.views.categories.get_tenants_by_org')
    def test_put_fx_coded_exception(self, mock_get_tenants_by_org, mock_course_categories):
        """Verify that PUT surfaces FXCodedException in a formatted way"""
        self.login_user(self.staff_user)
        mock_get_tenants_by_org.return_value = [1]

        error_code = FXExceptionCodes.UNKNOWN_ERROR.value if hasattr(FXExceptionCodes, 'UNKNOWN_ERROR') else 'E000'
        mock_manager = mock_course_categories.return_value
        mock_manager.set_categories_for_course.side_effect = FXCodedException(error_code, 'Some error')

        response = self.client.put(self.url, data=self.default_put_payload, format='json')

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        assert isinstance(response.data, dict)
        reason = response.data.get('reason') or response.data.get('detail') or ''
        assert reason == '(0) Some error'
