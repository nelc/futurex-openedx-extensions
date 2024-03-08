"""Test views for the dashboard app"""
import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.urls import reverse
from rest_framework.test import APITestCase

from tests.base_test_data import expected_statistics


@pytest.mark.usefixtures('base_data')
class TestTotalCountsView(APITestCase):
    """Tests for TotalCountsView"""
    def setUp(self):
        self.url = reverse('fx_dashboard:total-counts')
        self.staff_user = 2

    def login_user(self, user_id):
        """Helper to login user"""
        self.client.force_login(get_user_model().objects.get(id=user_id))

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
class TestLearnersView(APITestCase):
    """Tests for LearnersView"""
    def setUp(self):
        self.url = reverse('fx_dashboard:learners')
        self.staff_user = 2

    def login_user(self, user_id):
        """Helper to login user"""
        self.client.force_login(get_user_model().objects.get(id=user_id))

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
