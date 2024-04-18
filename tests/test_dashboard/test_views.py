"""Test views for the dashboard app"""
import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.urls import resolve, reverse
from django.utils.timezone import now, timedelta
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from rest_framework.test import APITestCase

from futurex_openedx_extensions.helpers.constants import COURSE_STATUSES
from futurex_openedx_extensions.helpers.filters import DefaultOrderingFilter
from tests.base_test_data import expected_statistics


class BaseTextViewMixin(APITestCase):
    """Base test view mixin"""
    VIEW_NAME = 'view name is not set!'

    def setUp(self):
        self.url = reverse(self.VIEW_NAME)
        self.staff_user = 2

    def login_user(self, user_id):
        """Helper to login user"""
        self.client.force_login(get_user_model().objects.get(id=user_id))


@pytest.mark.usefixtures('base_data')
class TestTotalCountsView(BaseTextViewMixin):
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
class TestLearnersView(BaseTextViewMixin):
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
class TesttCoursesView(BaseTextViewMixin):
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
class TesttCourseRatingsView(BaseTextViewMixin):
    """Tests for CourseRatingsView"""
    VIEW_NAME = 'fx_dashboard:course-ratings'

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
