"""Test views for the dashboard app - payments"""
# pylint: disable=duplicate-code
from unittest.mock import MagicMock, Mock, patch

import pytest
from django.urls import resolve
from rest_framework import status as http_status

from futurex_openedx_extensions.helpers.permissions import FXHasTenantCourseAccess
from tests.test_dashboard.test_mixins import BaseTestViewMixin


@pytest.mark.usefixtures('base_data')
class TestPaymentOrdersView(BaseTestViewMixin):
    """Tests for PaymentOrdersView"""
    VIEW_NAME = 'fx_dashboard:payments-orders'

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        view_func, _, _ = resolve(self.url)
        view_class = view_func.view_class
        self.assertEqual(view_class.permission_classes, [FXHasTenantCourseAccess])

    @patch('futurex_openedx_extensions.dashboard.views.payments.Cart.valid_statuses')
    def test_invalid_status(self, cart_valid_statuses):
        """Verify that the view returns the correct response"""
        cart_valid_statuses.return_value = ['paid']
        self.login_user(self.staff_user)
        response = self.client.get(f'{self.url}?status=invalid')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)

    @patch('futurex_openedx_extensions.dashboard.views.payments.CatalogueItem.valid_item_types')
    def test_invalid_item_type(self, item_valid_types):
        """Verify that the view returns the correct response"""
        item_valid_types.return_value = ['paid_course']
        self.login_user(self.staff_user)
        response = self.client.get(f'{self.url}?item_type=invalid')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)

    @patch('futurex_openedx_extensions.dashboard.views.payments.get_courses_orders_queryset')
    def test_success_without_cached_course_map(self, mock_qs):
        """Verify that the view returns the correct response"""
        mock_qs.return_value = []
        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

    @patch('futurex_openedx_extensions.dashboard.views.payments.get_courses_orders_queryset')
    def test_success_with_cached_course_map(self, mock_get_qs):
        """Verify that the view returns the correct response"""
        mock_cart1 = Mock(id=1, user_id=10, status='paid')
        mock_cart2 = Mock(id=2, user_id=20, status='processing')
        mock_cart_list = [mock_cart1, mock_cart2]
        mock_qs = MagicMock(name='MockedQueryset')
        mock_qs.__iter__.return_value = iter(mock_cart_list)
        mock_qs.__getitem__.side_effect = mock_cart_list.__getitem__
        mock_qs.__len__.return_value = len(mock_cart_list)
        mock_qs.all.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.courses_map = {
            'course-v1:Demo+T101+2025': {'title': 'Demo Course'}
        }
        mock_get_qs.return_value = mock_qs

        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

    def test_invalid_date(self):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        response = self.client.get(f'{self.url}?date_from=invalid-date')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data['detail'],
            'Invalid dates. date_from and date_to must be formated as YYYY-MM-DD when provided.',
        )
