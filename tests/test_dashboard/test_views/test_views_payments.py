"""Test views for the dashboard app - payments"""
# pylint: disable=duplicate-code
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import resolve
from django.utils import timezone
from rest_framework import status as http_status
from zeitlabs_payments.models import Cart, Invoice

from futurex_openedx_extensions.helpers.converters import dt_to_str
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


@pytest.mark.usefixtures('base_data')
class TestPaymentOrdersViewV2(BaseTestViewMixin):
    """Tests for PaymentOrdersViewV2"""
    VIEW_NAME = 'fx_dashboard:payments-orders-v2'

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        assert response.status_code == http_status.HTTP_403_FORBIDDEN

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        view_func, _, _ = resolve(self.url)
        view_class = view_func.view_class
        assert view_class.permission_classes == [FXHasTenantCourseAccess]

    @patch('futurex_openedx_extensions.dashboard.views.payments.Cart.valid_statuses')
    def test_invalid_status(self, cart_valid_statuses):
        """Verify that the view returns 400 for invalid status"""
        cart_valid_statuses.return_value = ['paid']
        self.login_user(self.staff_user)
        response = self.client.get(f'{self.url}?status=invalid')
        assert response.status_code == http_status.HTTP_400_BAD_REQUEST

    @patch('futurex_openedx_extensions.dashboard.views.payments.CatalogueItem.valid_item_types')
    def test_invalid_item_type(self, item_valid_types):
        """Verify that the view returns 400 for invalid item_type"""
        item_valid_types.return_value = ['paid_course']
        self.login_user(self.staff_user)
        response = self.client.get(f'{self.url}?item_type=invalid')
        assert response.status_code == http_status.HTTP_400_BAD_REQUEST

    def test_invalid_date(self):
        """Verify that the view returns 400 for invalid date"""
        self.login_user(self.staff_user)
        response = self.client.get(f'{self.url}?date_from=invalid-date')
        assert response.status_code == http_status.HTTP_400_BAD_REQUEST
        assert response.data['detail'] == (
            'Invalid dates. date_from and date_to must be formated as YYYY-MM-DD when provided.'
        )

    @patch('futurex_openedx_extensions.dashboard.views.payments.get_courses_orders_queryset')
    def test_success_empty(self, mock_qs):
        """Verify that an empty list serializes successfully"""
        mock_qs.return_value = []
        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        assert response.status_code == http_status.HTTP_200_OK
        assert response.data['results'] == []

    @patch('futurex_openedx_extensions.dashboard.views.payments.get_courses_orders_queryset')
    def test_v2_forces_include_flags(self, mock_get_qs):
        """v2 always passes include_invoice=True and include_user_details=True."""
        mock_get_qs.return_value = []
        self.login_user(self.staff_user)
        self.client.get(self.url)
        _, kwargs = mock_get_qs.call_args
        assert kwargs['include_invoice'] is True
        assert kwargs['include_user_details'] is True

    @patch('futurex_openedx_extensions.dashboard.views.payments.get_courses_orders_queryset')
    def test_flat_response_shape(self, mock_get_qs):
        """Verify the v2 response has the flat shape including invoice_url."""
        user = get_user_model().objects.get(id=self.staff_user)

        cart_paid = Cart.objects.create(user=user, status='paid')
        paid_at = timezone.now()
        Invoice.objects.create(
            cart=cart_paid, invoice_number='DEV-100001', total=750.0, currency='SAR', paid_at=paid_at,
        )
        cart_unpaid = Cart.objects.create(user=user, status='processing')

        mock_get_qs.return_value = Cart.objects.filter(
            id__in=[cart_paid.id, cart_unpaid.id],
        ).order_by('id')

        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        assert response.status_code == http_status.HTTP_200_OK

        results = response.data['results']
        assert len(results) == 2
        expected_keys = {
            'id', 'user_id', 'full_name', 'alternative_full_name', 'username',
            'national_id', 'email', 'mobile_no', 'status', 'created_at',
            'total', 'currency', 'paid_at', 'invoice_id', 'invoice_url',
        }
        assert set(results[0].keys()) == expected_keys

        assert results[0]['id'] == cart_paid.id
        assert results[0]['status'] == 'paid'
        assert results[0]['user_id'] == user.id
        assert results[0]['username'] == user.username
        assert results[0]['email'] == user.email
        assert results[0]['total'] == 750.0
        assert results[0]['currency'] == 'SAR'
        assert results[0]['invoice_id'] == 'DEV-100001'
        assert results[0]['invoice_url'] == '/payment/v1/invoice/DEV-100001/'
        assert results[0]['paid_at'] == dt_to_str(paid_at)

        assert results[1]['id'] == cart_unpaid.id
        assert results[1]['currency'] is None
        assert results[1]['invoice_id'] is None
        assert results[1]['invoice_url'] is None
        assert results[1]['paid_at'] is None

    @patch('futurex_openedx_extensions.dashboard.views.payments.get_courses_orders_queryset')
    def test_date_filter_uses_paid_at(self, mock_get_qs):
        """date_from/date_to filter on the invoice's paid_at, not the cart's created_at."""
        user = get_user_model().objects.get(id=self.staff_user)

        cart_in_range = Cart.objects.create(user=user, status='paid')
        Invoice.objects.create(
            cart=cart_in_range, invoice_number='DEV-1', total=100.0, currency='SAR',
            paid_at=timezone.make_aware(datetime(2025, 1, 15, 12, 0, 0)),
        )
        cart_out_of_range = Cart.objects.create(user=user, status='paid')
        Invoice.objects.create(
            cart=cart_out_of_range, invoice_number='DEV-2', total=100.0, currency='SAR',
            paid_at=timezone.make_aware(datetime(2025, 3, 15, 12, 0, 0)),
        )
        cart_no_invoice = Cart.objects.create(user=user, status='processing')

        mock_get_qs.return_value = Cart.objects.filter(
            id__in=[cart_in_range.id, cart_out_of_range.id, cart_no_invoice.id],
        ).order_by('id')

        self.login_user(self.staff_user)
        response = self.client.get(f'{self.url}?date_from=2025-01-01&date_to=2025-01-31')
        assert response.status_code == http_status.HTTP_200_OK

        # Only the order whose invoice was paid in January is returned; created_at (now) is ignored,
        # and the order with no invoice is excluded since it has no paid_at.
        ids = [result['id'] for result in response.data['results']]
        assert ids == [cart_in_range.id]
