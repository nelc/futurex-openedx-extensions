"""Test views for the dashboard app"""
import json
from unittest.mock import Mock, patch

import pytest
from common.djangoapps.student.models import CourseAccessRole
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.urls import resolve, reverse
from django.utils.timezone import now, timedelta
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from rest_framework.test import APIRequestFactory, APITestCase

from futurex_openedx_extensions.dashboard import serializers
from futurex_openedx_extensions.helpers.constants import COURSE_STATUSES
from futurex_openedx_extensions.helpers.filters import DefaultOrderingFilter
from futurex_openedx_extensions.helpers.permissions import HasTenantAccess, IsSystemStaff
from tests.base_test_data import expected_statistics


class BaseTestViewMixin(APITestCase):
    """Base test view mixin"""
    VIEW_NAME = 'view name is not set!'

    def setUp(self):
        """Setup"""
        self.url_args = []
        self.staff_user = 2

    @property
    def url(self):
        """Get the URL"""
        return reverse(self.VIEW_NAME, args=self.url_args)

    def login_user(self, user_id):
        """Helper to login user"""
        self.client.force_login(get_user_model().objects.get(id=user_id))

    def _get_request_view_class(self):
        """Helper to get the view class and a request"""
        view_func, _, _ = resolve(self.url)
        view_class = view_func.view_class
        factory = APIRequestFactory()
        request = factory.get(self.url)
        request.query_params = {}
        request.user = get_user_model().objects.get(id=self.staff_user)

        return request, view_class


@pytest.mark.usefixtures('base_data')
class TestTotalCountsView(BaseTestViewMixin):
    """Tests for TotalCountsView"""
    VIEW_NAME = 'fx_dashboard:total-counts'

    def test_unauthorized(self):
        """Test unauthorized access"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_invalid_stats(self):
        """Test invalid stats"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url + '?stats=invalid')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {'reason': 'Invalid stats type', 'details': {'invalid': ['invalid']}})

    def test_all_stats(self):
        """Test get method"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url + '?stats=certificates,courses,learners')
        self.assertTrue(isinstance(response, JsonResponse))
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(json.loads(response.content), expected_statistics)

    def test_selected_tenants(self):
        """Test get method with selected tenants"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url + '?stats=certificates,courses,learners&tenant_ids=1,2')
        self.assertTrue(isinstance(response, JsonResponse))
        self.assertEqual(response.status_code, 200)
        expected_response = {
            '1': {'certificates_count': 14, 'courses_count': 12, 'learners_count': 17},
            '2': {'certificates_count': 9, 'courses_count': 5, 'learners_count': 21},
            'total_certificates_count': 23,
            'total_courses_count': 17,
            'total_learners_count': 38
        }
        self.assertDictEqual(json.loads(response.content), expected_response)


@pytest.mark.usefixtures('base_data')
class TestLearnersView(BaseTestViewMixin):
    """Tests for LearnersView"""
    VIEW_NAME = 'fx_dashboard:learners'

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_no_tenants(self):
        """Verify that the view returns the result for all accessible tenants when no tenant IDs are provided"""
        self.login_user(self.staff_user)
        with patch('futurex_openedx_extensions.dashboard.views.get_learners_queryset') as mock_queryset:
            self.client.get(self.url)
            mock_queryset.assert_called_once_with(tenant_ids=[1, 2, 3, 7, 8], search_text=None)

    def test_search(self):
        """Verify that the view filters the learners by search text"""
        self.login_user(self.staff_user)
        with patch('futurex_openedx_extensions.dashboard.views.get_learners_queryset') as mock_queryset:
            self.client.get(self.url + '?tenant_ids=1&search_text=user')
            mock_queryset.assert_called_once_with(tenant_ids=[1], search_text='user')

    def test_success(self):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 46)
        self.assertGreater(len(response.data['results']), 0)


@pytest.mark.usefixtures('base_data')
class TestCoursesView(BaseTestViewMixin):
    """Tests for CoursesView"""
    VIEW_NAME = 'fx_dashboard:courses'

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_no_tenants(self):
        """Verify that the view returns the result for all accessible tenants when no tenant IDs are provided"""
        self.login_user(self.staff_user)
        with patch('futurex_openedx_extensions.dashboard.views.get_courses_queryset') as mock_queryset:
            self.client.get(self.url)
            mock_queryset.assert_called_once_with(tenant_ids=[1, 2, 3, 7, 8], search_text=None)

    def test_search(self):
        """Verify that the view filters the courses by search text"""
        self.login_user(self.staff_user)
        with patch('futurex_openedx_extensions.dashboard.views.get_courses_queryset') as mock_queryset:
            self.client.get(self.url + '?tenant_ids=1&search_text=course')
            mock_queryset.assert_called_once_with(tenant_ids=[1], search_text='course')

    def helper_test_success(self, response):
        """Verify that the view returns the correct response"""
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 18)
        self.assertGreater(len(response.data['results']), 0)
        self.assertEqual(response.data['results'][0]['id'], 'course-v1:ORG1+1+1')

    def test_success(self):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.helper_test_success(response=response)
        self.assertEqual(response.data['results'][0]['status'], COURSE_STATUSES['upcoming'])

    def test_status_archived(self):
        """Verify that the view sets the correct status when the course is archived"""
        CourseOverview.objects.filter(id='course-v1:ORG1+1+1').update(end=now() - timedelta(days=1))

        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.helper_test_success(response=response)
        self.assertEqual(response.data['results'][0]['status'], 'archived')

    def test_status_upcoming(self):
        """Verify that the view sets the correct status when the course is upcoming"""
        CourseOverview.objects.filter(id='course-v1:ORG1+1+1').update(start=now() + timedelta(days=1))

        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.helper_test_success(response=response)
        self.assertEqual(response.data['results'][0]['status'], 'upcoming')

    def test_sorting(self):
        """Verify that the view soring filter is set correctly"""
        view_func, _, _ = resolve(self.url)
        view_class = view_func.view_class
        self.assertEqual(view_class.filter_backends, [DefaultOrderingFilter])


@pytest.mark.usefixtures('base_data')
class TestCourseCourseStatusesView(BaseTestViewMixin):
    """Tests for CourseStatusesView"""
    VIEW_NAME = 'fx_dashboard:course-statuses'

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_no_tenants(self):
        """Verify that the view returns the result for all accessible tenants when no tenant IDs are provided"""
        self.login_user(self.staff_user)
        with patch('futurex_openedx_extensions.dashboard.views.get_courses_count_by_status') as mock_queryset:
            self.client.get(self.url)
            mock_queryset.assert_called_once_with(tenant_ids=[1, 2, 3, 7, 8])

    def test_success(self):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertDictEqual(data, {
            "active": 12,
            "archived": 3,
            "upcoming": 2,
            "self_active": 1,
            "self_archived": 0,
            "self_upcoming": 0,
        })


class PermissionsTestOfLearnerInfoViewMixin:
    """Tests for CourseStatusesView"""
    def setUp(self):
        """Setup"""
        super().setUp()
        self.url_args = ['user10']

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        view_func, _, _ = resolve(self.url)
        view_class = view_func.view_class
        self.assertEqual(view_class.permission_classes, [HasTenantAccess])

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_user_not_found(self):
        """Verify that the view returns 404 when the user is not found"""
        user_name = 'user10x'
        self.url_args = [user_name]
        assert not get_user_model().objects.filter(username=user_name).exists(), 'bad test data'

        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data, {'reason': 'User not found user10x', 'details': {}})

    def _get_test_users(self, org3_admin_id, org3_learner_id):
        """Helper to get test users for the test_not_staff_user test"""
        admin_user = get_user_model().objects.get(id=org3_admin_id)
        learner_user = get_user_model().objects.get(id=org3_learner_id)

        self.assertFalse(admin_user.is_staff, msg='bad test data')
        self.assertFalse(admin_user.is_superuser, msg='bad test data')
        self.assertFalse(learner_user.is_staff, msg='bad test data')
        self.assertFalse(learner_user.is_superuser, msg='bad test data')
        self.assertFalse(CourseAccessRole.objects.filter(user_id=org3_learner_id).exists(), msg='bad test data')

        self.login_user(org3_admin_id)

    def test_org_admin_user_with_allowed_learner(self):
        """Verify that the view returns 200 when the user is an admin on the learner's organization"""
        self._get_test_users(4, 45)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_org_admin_user_with_not_allowed_learner(self):
        """Verify that the view returns 404 when the user is an org admin but the learner belongs to another org"""
        self._get_test_users(9, 45)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)


@pytest.mark.usefixtures('base_data')
class TestLearnerInfoView(PermissionsTestOfLearnerInfoViewMixin, BaseTestViewMixin):
    """Tests for CourseStatusesView"""
    VIEW_NAME = 'fx_dashboard:learner-info'

    def test_success(self):
        """Verify that the view returns the correct response"""
        user = get_user_model().objects.get(username='user10')
        user.courses_count = 3
        user.certificates_count = 1
        self.url_args = [user.username]
        self.assertFalse(())

        self.login_user(self.staff_user)
        with patch('futurex_openedx_extensions.dashboard.views.get_learner_info_queryset') as mock_get_info:
            mock_get_info.return_value = Mock(first=Mock(return_value=user))
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertDictEqual(data, serializers.LearnerDetailsExtendedSerializer(user).data)

    @patch('futurex_openedx_extensions.dashboard.views.serializers.LearnerDetailsExtendedSerializer')
    def test_request_in_context(self, mock_serializer):
        """Verify that the view calls the serializer with the correct context"""
        request, view_class = self._get_request_view_class()
        mock_serializer.return_value = Mock(data={})

        with patch('futurex_openedx_extensions.dashboard.views.get_learner_info_queryset') as mock_get_info:
            mock_get_info.return_value = Mock()
            view_class.get(self, request, 'user10')

        mock_serializer.assert_called_once_with(
            mock_get_info.return_value.first(),
            context={'request': request},
        )


@patch.object(
    serializers.LearnerCoursesDetailsSerializer,
    'get_grade',
    lambda self, obj: {"letter_grade": "Pass", "percent": 0.7, "is_passing": True}
)
@pytest.mark.usefixtures('base_data')
class TestLearnerCoursesDetailsView(PermissionsTestOfLearnerInfoViewMixin, BaseTestViewMixin):
    """Tests for CourseStatusesView"""
    VIEW_NAME = 'fx_dashboard:learner-courses'

    def test_success(self):
        """Verify that the view returns the correct response"""
        user = get_user_model().objects.get(username='user10')
        self.url_args = [user.username]

        courses = CourseOverview.objects.filter(courseenrollment__user=user)
        for course in courses:
            course.enrollment_date = now() - timedelta(days=10)
            course.last_activity = now() - timedelta(days=2)
            course.related_user_id = user.id
            course.save()

        self.login_user(self.staff_user)
        with patch('futurex_openedx_extensions.dashboard.views.get_learner_courses_info_queryset') as mock_get_info:
            mock_get_info.return_value = courses
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(len(data), 2)
        self.assertEqual(list(data), list(serializers.LearnerCoursesDetailsSerializer(courses, many=True).data))

    @patch('futurex_openedx_extensions.dashboard.views.serializers.LearnerCoursesDetailsSerializer')
    def test_request_in_context(self, mock_serializer):
        """Verify that the view uses the correct serializer"""
        request, view_class = self._get_request_view_class()

        with patch('futurex_openedx_extensions.dashboard.views.get_learner_courses_info_queryset') as mock_get_info:
            mock_get_info.return_value = Mock()
            view_class.get(self, request, 'user10')

        mock_serializer.assert_called_once_with(
            mock_get_info.return_value,
            context={'request': request},
            many=True,
        )


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
        self.assertEqual(response.status_code, 403)

    def test_success(self):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        with patch('futurex_openedx_extensions.__version__', new='0.1.dummy'):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {'version': '0.1.dummy'})
