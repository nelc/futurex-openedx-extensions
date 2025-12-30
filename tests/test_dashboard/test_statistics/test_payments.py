"""Tests for payment statistics functions"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils.timezone import now
from zeitlabs_payments.models import Cart, CartItem, CatalogueItem

from futurex_openedx_extensions.dashboard.statistics.payments import get_payment_statistics
from tests.fixture_helpers import get_user1_fx_permission_info


@pytest.mark.django_db
# pylint: disable=too-many-instance-attributes,attribute-defined-outside-init
class TestPaymentStatistics:
    """Tests for get_payment_statistics"""

    @pytest.fixture(autouse=True)
    def setup_data(self, base_data):  # pylint: disable=unused-argument
        """Setup test data"""
        self.user = get_user_model().objects.get(id=1)
        self.fx_permission_info = get_user1_fx_permission_info()

        # Create catalogue items
        self.item1 = CatalogueItem.objects.create(
            sku='sku1',
            type='paid_course',
            title='Course 1',
            item_ref_id='course-v1:org1+course1',
            price=Decimal('100.00'),
            currency='USD'
        )
        self.item2 = CatalogueItem.objects.create(
            sku='sku2',
            type='paid_course',
            title='Course 2',
            item_ref_id='course-v1:org2+course2',
            price=Decimal('50.00'),
            currency='USD'
        )
        self.item3 = CatalogueItem.objects.create(
            sku='sku3',
            type='paid_course',
            title='Course 3',
            item_ref_id='course-v1:org3+course3',  # Not accessible
            price=Decimal('200.00'),
            currency='USD'
        )

        # Create carts
        self.cart1 = Cart.objects.create(user=self.user, status=Cart.Status.PAID)
        Cart.objects.filter(pk=self.cart1.pk).update(updated_at=now() - timedelta(days=5))
        CartItem.objects.create(
            cart=self.cart1, catalogue_item=self.item1, original_price=Decimal('100.00'), final_price=Decimal('100.00')
        )

        self.cart2 = Cart.objects.create(user=self.user, status=Cart.Status.PAID)
        Cart.objects.filter(pk=self.cart2.pk).update(updated_at=now() - timedelta(days=2))
        CartItem.objects.create(
            cart=self.cart2, catalogue_item=self.item2, original_price=Decimal('50.00'), final_price=Decimal('50.00')
        )

        # Cart with inaccessible item
        self.cart3 = Cart.objects.create(user=self.user, status=Cart.Status.PAID)
        Cart.objects.filter(pk=self.cart3.pk).update(updated_at=now() - timedelta(days=1))
        CartItem.objects.create(
            cart=self.cart3, catalogue_item=self.item3, original_price=Decimal('200.00'), final_price=Decimal('200.00')
        )

        # Unpaid cart
        self.cart4 = Cart.objects.create(user=self.user, status=Cart.Status.PENDING)
        Cart.objects.filter(pk=self.cart4.pk).update(updated_at=now())
        CartItem.objects.create(
            cart=self.cart4, catalogue_item=self.item1, original_price=Decimal('100.00'), final_price=Decimal('100.00')
        )

    def test_get_payment_statistics_all(self):
        """Test getting all payment statistics"""
        from_date = now() - timedelta(days=30)
        to_date = now()

        # Mock accessible courses to include org1 and org2 but not org3
        patch_path = 'futurex_openedx_extensions.dashboard.statistics.payments.get_base_queryset_courses'
        with patch(patch_path) as mock_courses:
            mock_courses.return_value.values.return_value = [
                'course-v1:org1+course1', 'course-v1:org2+course2'
            ]

            stats = get_payment_statistics(self.fx_permission_info, from_date, to_date)

        assert stats['total_sales'] == 150.0
        assert stats['orders_count'] == 2
        assert stats['average_order_value'] == 75.0
        assert len(stats['daily_breakdown']) == 2

    def test_get_payment_statistics_filtered_by_course(self):
        """Test getting payment statistics filtered by course"""
        from_date = now() - timedelta(days=30)
        to_date = now()

        patch_path = 'futurex_openedx_extensions.dashboard.statistics.payments.get_base_queryset_courses'
        with patch(patch_path) as mock_courses:
            mock_courses.return_value.values.return_value = [
                'course-v1:org1+course1', 'course-v1:org2+course2'
            ]

            stats = get_payment_statistics(
                self.fx_permission_info, from_date, to_date, course_id='course-v1:org1+course1'
            )

        assert stats['total_sales'] == 100.0
        assert stats['orders_count'] == 1
        assert stats['average_order_value'] == 100.0
        assert len(stats['daily_breakdown']) == 1

    def test_get_payment_statistics_date_range(self):
        """Test getting payment statistics with date range"""
        from_date = now() - timedelta(days=3)
        to_date = now()

        patch_path = 'futurex_openedx_extensions.dashboard.statistics.payments.get_base_queryset_courses'
        with patch(patch_path) as mock_courses:
            mock_courses.return_value.values.return_value = [
                'course-v1:org1+course1', 'course-v1:org2+course2'
            ]

            stats = get_payment_statistics(self.fx_permission_info, from_date, to_date)

        # Should only include cart2 (2 days ago), cart1 is 5 days ago
        assert stats['total_sales'] == 50.0
        assert stats['orders_count'] == 1
        assert stats['average_order_value'] == 50.0

    def test_get_payment_statistics_no_data(self):
        """Test getting payment statistics with no data"""
        from_date = now() - timedelta(days=30)
        to_date = now()

        patch_path = 'futurex_openedx_extensions.dashboard.statistics.payments.get_base_queryset_courses'
        with patch(patch_path) as mock_courses:
            mock_courses.return_value.values.return_value = []  # No accessible courses

            stats = get_payment_statistics(self.fx_permission_info, from_date, to_date)

        assert stats['total_sales'] == 0.0
        assert stats['orders_count'] == 0
        assert stats['average_order_value'] == 0.0
        assert len(stats['daily_breakdown']) == 0
