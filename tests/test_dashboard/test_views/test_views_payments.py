"""Test views for the dashboard app - payments"""
# pylint: disable=duplicate-code
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import resolve, reverse
from django.utils import timezone
from eox_tenant.models import TenantConfig
from rest_framework import status as http_status
from zeitlabs_payments.models import Cart, CartItem, CatalogueItem, Invoice, InvoiceItem, Transaction

from futurex_openedx_extensions.dashboard.serializers import PaymentInvoiceSerializer
from futurex_openedx_extensions.helpers.converters import dt_to_str
from futurex_openedx_extensions.helpers.payments import PAYMENTS_SETTINGS_KEY
from futurex_openedx_extensions.helpers.permissions import (
    FXHasTenantAllCoursesAccess,
    FXHasTenantCourseAccess,
    IsSystemStaff,
)
from tests.test_dashboard.test_mixins import BaseTestViewMixin
from tests.test_helpers.test_payments import COMPLETE_HYPERPAY, COMPLETE_SETTINGS, _configured


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
            'total', 'currency', 'paid_at', 'invoice_id', 'invoice_url', 'transaction_id',
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

    @patch('futurex_openedx_extensions.dashboard.views.payments.get_courses_orders_queryset')
    def test_transaction_id(self, mock_get_qs):
        """Verify transaction_id: the gateway id, null for a manual payment, null without an invoice."""
        user = get_user_model().objects.get(id=self.staff_user)
        cart_gateway = Cart.objects.create(user=user, status='paid')
        transaction = Transaction.objects.create(cart=cart_gateway, gateway='hyperpay', gateway_transaction_id='HP-1')
        Invoice.objects.create(
            cart=cart_gateway, invoice_number='DEV-11', total=1, currency='SAR', related_transaction=transaction,
        )
        cart_manual = Cart.objects.create(user=user, status='paid')
        Invoice.objects.create(cart=cart_manual, invoice_number='DEV-12', total=1, currency='SAR')
        cart_none = Cart.objects.create(user=user, status='processing')
        mock_get_qs.return_value = Cart.objects.filter(
            id__in=[cart_gateway.id, cart_manual.id, cart_none.id],
        ).order_by('id')

        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        assert [row['transaction_id'] for row in response.data['results']] == ['HP-1', None, None]


def create_invoice(  # pylint: disable=too-many-arguments
    invoice_number, course_id='course-v1:ORG4+1+1', user_id=2, sku=None, with_transaction=True, paid_at=None,
):
    """Create a paid cart with one course item and its invoice"""
    cart = Cart.objects.create(user_id=user_id, status='paid')
    catalogue_item, _ = CatalogueItem.objects.get_or_create(
        sku=sku or f'sku-{invoice_number}',
        defaults={'type': 'paid_course', 'title': 'Course title', 'item_ref_id': course_id, 'price': 100},
    )
    cart_item = CartItem.objects.create(
        cart=cart, catalogue_item=catalogue_item, original_price=100, tax_amount=15, final_price=115,
    )
    transaction = Transaction.objects.create(
        cart=cart, gateway='hyperpay', gateway_transaction_id=f'HP-{invoice_number}', method='VISA',
    ) if with_transaction else None
    invoice = Invoice.objects.create(
        cart=cart, invoice_number=invoice_number, gross_total=115, tax_total=15, total=115, currency='SAR',
        paid_at=paid_at or timezone.now(), related_transaction=transaction,
    )
    InvoiceItem.objects.create(
        invoice=invoice, cart_item=cart_item, original_price=100, tax_amount=15, price=115,
    )
    return invoice


def set_tenant_payments_settings(tenant_id, **settings):
    """Set ZEITLABS_PAYMENTS_SETTINGS on a tenant"""
    tenant = TenantConfig.objects.get(id=tenant_id)
    tenant.lms_configs[PAYMENTS_SETTINGS_KEY] = settings
    tenant.save()


@pytest.mark.usefixtures('base_data')
class TestPaymentInvoicesView(BaseTestViewMixin):
    """Tests for PaymentInvoicesView"""
    VIEW_NAME = 'fx_dashboard:payments-invoices'

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        view_func, _, _ = resolve(self.url)
        assert view_func.view_class.permission_classes == [FXHasTenantCourseAccess]

    def test_invalid_date(self):
        """Verify that the view returns 400 for an invalid date"""
        self.login_user(self.staff_user)
        response = self.client.get(f'{self.url}?date_from=invalid-date')
        assert response.status_code == http_status.HTTP_400_BAD_REQUEST

    def test_list_filters_and_shape(self):
        """Verify the course filter, the paid_at filter, the order, and the response shape"""
        set_tenant_payments_settings(3, organization='Org 3', customer_number='300000000000003')
        create_invoice('ORG-100001', paid_at=timezone.make_aware(datetime(2025, 1, 15, 12, 0, 0)))
        create_invoice('ORG-100002', paid_at=timezone.make_aware(datetime(2025, 3, 15, 12, 0, 0)))
        create_invoice('ORG-100003', course_id='course-v1:ORG3+1+1')
        self.login_user(self.staff_user)

        response = self.client.get(f'{self.url}?course_ids=course-v1:ORG4%2B1%2B1')
        assert response.status_code == http_status.HTTP_200_OK
        assert [row['invoice_number'] for row in response.data['results']] == ['ORG-100002', 'ORG-100001']
        row = response.data['results'][1]
        assert row['tenant_id'] == 3
        assert row['seller'] == {'organization': 'Org 3', 'tax_number': '300000000000003'}
        assert row['buyer']['user_id'] == 2
        assert row['buyer']['username'] == 'user2'
        assert row['items'] == [{
            'sku': 'sku-ORG-100001', 'title': 'Course title', 'course_id': 'course-v1:ORG4+1+1',
            'original_price': 100.0, 'discount_amount': 0.0, 'tax_amount': 15.0, 'price': 115.0, 'quantity': 1,
        }]
        assert row['payment'] == {'gateway': 'hyperpay', 'method': 'VISA', 'transaction_id': 'HP-ORG-100001'}
        assert row['total'] == 115.0
        assert row['invoice_url'] == '/payment/v1/invoice/ORG-100001/'

        response = self.client.get(
            f'{self.url}?course_ids=course-v1:ORG4%2B1%2B1&date_from=2025-01-01&date_to=2025-01-31',
        )
        assert [row['invoice_number'] for row in response.data['results']] == ['ORG-100001']

    def test_scoped_to_caller(self):
        """Verify that a tenant admin sees only the invoices of their tenant's courses"""
        create_invoice('ORG-100004')
        create_invoice('ORG-100005', course_id='course-v1:ORG1+3+3')
        self.login_user(3)
        response = self.client.get(self.url)
        assert response.status_code == http_status.HTTP_200_OK
        assert [row['invoice_number'] for row in response.data['results']] == ['ORG-100005']


@pytest.mark.usefixtures('base_data')
class TestPaymentInvoiceDetailView(BaseTestViewMixin):
    """Tests for PaymentInvoiceDetailView"""
    VIEW_NAME = 'fx_dashboard:payments-invoice-detail'

    @property
    def url(self):
        """Get the URL of one invoice"""
        return reverse(self.VIEW_NAME, kwargs={'invoice_number': 'ORG-100006'})

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        view_func, _, _ = resolve(self.url)
        assert view_func.view_class.permission_classes == [FXHasTenantCourseAccess]

    def test_success_manual_payment(self):
        """Verify one invoice of a manual payment"""
        create_invoice('ORG-100006', with_transaction=False)
        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        assert response.status_code == http_status.HTTP_200_OK
        assert response.data['invoice_number'] == 'ORG-100006'
        assert response.data['payment'] == {'gateway': 'manual', 'method': None, 'transaction_id': None}

    def test_not_found_and_out_of_scope(self):
        """Verify 404 for a missing invoice and for an invoice outside the caller's tenants"""
        self.login_user(self.staff_user)
        assert self.client.get(self.url).status_code == http_status.HTTP_404_NOT_FOUND
        create_invoice('ORG-100006')
        self.login_user(3)
        assert self.client.get(self.url).status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.usefixtures('base_data')
class TestPaymentInvoiceSerializerTenant(BaseTestViewMixin):
    """Tests for the issuing-tenant resolution of PaymentInvoiceSerializer"""
    VIEW_NAME = 'fx_dashboard:payments-invoices'

    @patch('futurex_openedx_extensions.dashboard.serializers.get_tenants_by_org', return_value=[1, 4])
    def test_prefix_match_among_shared_tenants(self, _):  # pylint: disable=no-self-use
        """ORG1 belongs to tenants 1 and 4; the invoice prefix picks tenant 4"""
        set_tenant_payments_settings(4, invoice_prefix='T4', organization='Tenant 4')
        data = PaymentInvoiceSerializer(create_invoice('T4-100001', course_id='course-v1:ORG1+3+3')).data
        assert data['tenant_id'] == 4
        assert data['seller']['organization'] == 'Tenant 4'

    @patch('futurex_openedx_extensions.dashboard.serializers.get_tenants_by_org', return_value=[1, 4])
    def test_undecidable_tenant(self, _):  # pylint: disable=no-self-use
        """Shared org and no prefix match: no tenant and a blank seller"""
        data = PaymentInvoiceSerializer(create_invoice('XX-100001', course_id='course-v1:ORG1+3+3')).data
        assert data['tenant_id'] is None
        assert data['seller'] == {'organization': None, 'tax_number': None}

    def test_no_item_and_bad_course_id(self):  # pylint: disable=no-self-use
        """No invoice item, or an item whose course id is not a course key: no tenant"""
        invoice = create_invoice('YY-100001')
        invoice.items.update(cart_item=None)
        data = PaymentInvoiceSerializer(Invoice.objects.get(id=invoice.id)).data
        assert data['tenant_id'] is None
        assert data['items'][0]['sku'] is None
        invoice = create_invoice('YY-100002', course_id='not-a-course-key')
        assert PaymentInvoiceSerializer(invoice).data['tenant_id'] is None


@pytest.mark.usefixtures('base_data')
class TestTenantPaymentsStatusView(BaseTestViewMixin):
    """Tests for TenantPaymentsStatusView"""
    VIEW_NAME = 'fx_dashboard:payments-tenants'

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        view_func, _, _ = resolve(self.url)
        assert view_func.view_class.permission_classes == [FXHasTenantAllCoursesAccess]

    def test_status_for_accessible_tenants(self):
        """Verify the status rows, filtered by tenant_ids"""
        tenant = TenantConfig.objects.get(id=1)
        tenant.lms_configs.update(_configured())
        tenant.save()
        self.login_user(self.staff_user)
        response = self.client.get(f'{self.url}?tenant_ids=1,2')
        assert response.status_code == http_status.HTTP_200_OK
        assert response.data == [
            {
                'tenant_id': 1, 'domain': 's1.sample.com', 'enabled': True, 'active': True,
                'configured': True, 'mada_available': False, 'test_mode': False,
            },
            {
                'tenant_id': 2, 'domain': 's2.sample.com', 'enabled': False, 'active': False,
                'configured': False, 'mada_available': False, 'test_mode': False,
            },
        ]
        assert 'token5678' not in str(response.data)

    def test_tenant_admin_sees_own_tenant(self):
        """Verify that a tenant admin gets their own tenant only"""
        self.login_user(3)
        response = self.client.get(self.url)
        assert response.status_code == http_status.HTTP_200_OK
        assert [row['tenant_id'] for row in response.data] == [1]


@pytest.mark.usefixtures('base_data')
class TestTenantPaymentsSettingsView(BaseTestViewMixin):
    """Tests for TenantPaymentsSettingsView"""
    VIEW_NAME = 'fx_dashboard:payments-tenant-settings'

    def url_for(self, tenant_id):
        """Get the URL of a tenant"""
        return reverse(self.VIEW_NAME, kwargs={'tenant_id': tenant_id})

    @property
    def url(self):
        """Get the URL of tenant 1"""
        return self.url_for(1)

    def test_permission_classes(self):
        """Verify that the view is system staff only"""
        view_func, _, _ = resolve(self.url)
        assert view_func.view_class.permission_classes == [IsSystemStaff]

    def test_tenant_admin_forbidden(self):
        """Verify that a tenant admin cannot read or change the settings of their own tenant"""
        self.login_user(3)
        assert self.client.get(self.url).status_code == http_status.HTTP_403_FORBIDDEN
        response = self.client.patch(self.url, data={'enabled': False}, format='json')
        assert response.status_code == http_status.HTTP_403_FORBIDDEN

    def test_get_not_found(self):
        """Verify 404 for an unknown tenant"""
        self.login_user(self.staff_user)
        assert self.client.get(self.url_for(9999)).status_code == http_status.HTTP_404_NOT_FOUND
        response = self.client.patch(self.url_for(9999), data={'enabled': False}, format='json')
        assert response.status_code == http_status.HTTP_404_NOT_FOUND

    def test_patch_then_get(self):
        """Verify enabling a tenant, then reading it back with masked secrets"""
        self.login_user(self.staff_user)
        response = self.client.patch(
            self.url,
            data={'enabled': True, 'settings': COMPLETE_SETTINGS, 'hyperpay': COMPLETE_HYPERPAY},
            format='json',
        )
        assert response.status_code == http_status.HTTP_200_OK, response.data
        assert response.data['active'] is True
        assert response.data['settings']['hyperpay']['ACCESS_TOKEN'] == {'is_set': True, 'last4': '5678'}
        assert 'token5678' not in str(response.data)

        response = self.client.get(self.url)
        assert response.status_code == http_status.HTTP_200_OK
        assert response.data['tenant_id'] == 1
        assert response.data['domain'] == 's1.sample.com'
        assert response.data['enabled'] is True
        assert 'token5678' not in str(response.data)

    def test_patch_invalid(self):
        """Verify 400 with the reason for an invalid payload"""
        self.login_user(self.staff_user)
        response = self.client.patch(self.url, data={'enabled': True}, format='json')
        assert response.status_code == http_status.HTTP_400_BAD_REQUEST
        assert 'Payments cannot be enabled until' in response.data['reason']


@pytest.mark.usefixtures('base_data')
class TestCoursePriceView(BaseTestViewMixin):
    """Tests for CoursePriceView"""
    VIEW_NAME = 'fx_dashboard:payments-course-price'

    def url_for(self, course_id):
        """Get the URL of a course"""
        return reverse(self.VIEW_NAME, kwargs={'course_id': course_id})

    @property
    def url(self):
        """Get the URL of a course of tenant 3"""
        return self.url_for('course-v1:ORG4+1+1')

    def _activate_tenant_3(self):  # pylint: disable=no-self-use
        """Switch payments on for tenant 3"""
        tenant = TenantConfig.objects.get(id=3)
        tenant.lms_configs.update(_configured())
        tenant.save()

    def test_permission_classes(self):
        """Verify that the view is system staff only"""
        view_func, _, _ = resolve(self.url)
        assert view_func.view_class.permission_classes == [IsSystemStaff]

    def test_tenant_admin_forbidden(self):
        """Verify that a tenant admin cannot set a price"""
        self.login_user(3)
        response = self.client.put(self.url_for('course-v1:ORG1+3+3'), data={'price': 100}, format='json')
        assert response.status_code == http_status.HTTP_403_FORBIDDEN

    def test_not_found(self):
        """Verify 404 for an unknown course"""
        self.login_user(self.staff_user)
        missing = self.url_for('course-v1:ORG4+99+99')
        assert self.client.get(missing).status_code == http_status.HTTP_404_NOT_FOUND
        assert self.client.put(missing, data={'price': 1}, format='json').status_code == 404

    def test_put_then_get(self):
        """Verify setting a price, then reading the readiness report"""
        self._activate_tenant_3()
        self.login_user(self.staff_user)
        response = self.client.put(self.url, data={'price': 500, 'sku': 'Pay101'}, format='json')
        assert response.status_code == http_status.HTTP_200_OK, response.data
        assert response.data['ready'] is True
        response = self.client.get(self.url)
        assert response.status_code == http_status.HTTP_200_OK
        assert (response.data['sku'], response.data['price'], response.data['ready']) == ('Pay101', 500.0, True)

    def test_put_errors(self):
        """Verify the 400 and 409 answers"""
        self.login_user(self.staff_user)
        assert self.client.put(self.url, data={}, format='json').status_code == http_status.HTTP_400_BAD_REQUEST
        response = self.client.put(self.url, data={'price': 100}, format='json')
        assert response.status_code == http_status.HTTP_400_BAD_REQUEST
        assert 'Payments are not active' in response.data['reason']
        self._activate_tenant_3()
        self.client.put(self.url, data={'price': 100, 'sku': 'Pay101'}, format='json')
        response = self.client.put(self.url, data={'price': 100, 'sku': 'Pay102'}, format='json')
        assert response.status_code == http_status.HTTP_409_CONFLICT
