"""
Payment statistics module.

This module provides functions to retrieve payment statistics for courses.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from django.db.models import Count, Sum
from django.db.models.functions import TruncDay
from zeitlabs_payments.models import Cart, CartItem

from futurex_openedx_extensions.helpers.querysets import get_base_queryset_courses


def get_payment_statistics(  # pylint: disable=too-many-locals
    fx_permission_info: dict,
    from_date: datetime,
    to_date: datetime,
    course_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get payment statistics for the given date range.

    :param fx_permission_info: Dictionary containing permission information
    :param from_date: Start date for the statistics
    :param to_date: End date for the statistics
    :param course_id: Optional course ID to filter by
    :return: Dictionary containing total sales, number of orders, average order value, and daily breakdown
    """
    accessible_courses = get_base_queryset_courses(fx_permission_info)

    filters = {
        'cart__status': Cart.Status.PAID,
        'cart__updated_at__range': (from_date, to_date),
        'catalogue_item__item_ref_id__in': accessible_courses.values('id'),
    }

    if course_id:
        filters['catalogue_item__item_ref_id'] = course_id

    queryset = CartItem.objects.filter(**filters)

    # Aggregate overall statistics
    overall_stats = queryset.aggregate(
        total_sales=Sum('final_price'),
        orders_count=Count('cart', distinct=True),
    )

    total_sales = overall_stats['total_sales'] or Decimal('0.00')
    orders_count = overall_stats['orders_count'] or 0
    avg_order_value = (total_sales / orders_count) if orders_count > 0 else Decimal('0.00')

    # Aggregate daily statistics
    daily_stats = (
        queryset.annotate(day=TruncDay('cart__updated_at'))
        .values('day')
        .annotate(
            daily_sales=Sum('final_price'),
            daily_orders=Count('cart', distinct=True),
        )
        .order_by('day')
    )

    daily_breakdown = []
    for entry in daily_stats:
        daily_sales = entry['daily_sales'] or Decimal('0.00')
        daily_orders = entry['daily_orders'] or 0
        daily_avg = (daily_sales / daily_orders) if daily_orders > 0 else Decimal('0.00')

        daily_breakdown.append({
            'date': entry['day'].date().isoformat(),
            'total_sales': float(daily_sales),
            'orders_count': daily_orders,
            'average_order_value': float(daily_avg),
        })

    return {
        'total_sales': float(total_sales),
        'orders_count': orders_count,
        'average_order_value': float(avg_order_value),
        'daily_breakdown': daily_breakdown,
    }
