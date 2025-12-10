"""Mock"""
from datetime import date

from django.db.models.query import QuerySet


def get_orders_queryset(  # pylint: disable=too-many-arguments,unused-argument
    filtered_courses_qs: QuerySet,
    filtered_users_qs: QuerySet = None,
    sku_search: str | None = None,
    status: str | None = None,
    item_type: str | None = None,
    include_invoice: bool = False,
    include_user_details: bool = False,
    date_from: date | None = None,
    date_to: date | None = None,
):
    """
    Mock.
    """
    return
