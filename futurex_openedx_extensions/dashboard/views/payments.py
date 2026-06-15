"""Views for the dashboard app - payments feature"""
# pylint: disable=duplicate-code

from __future__ import annotations

from typing import Any, Dict

from django.db.models.query import QuerySet
from rest_framework.exceptions import ParseError
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from zeitlabs_payments.models import Cart, CatalogueItem
from zeitlabs_payments.serializers import CartSerializer

from futurex_openedx_extensions.dashboard import serializers
from futurex_openedx_extensions.dashboard.details.courses import get_courses_orders_queryset
from futurex_openedx_extensions.dashboard.docs_utils import docs
from futurex_openedx_extensions.helpers.constants import FX_VIEW_DEFAULT_AUTH_CLASSES
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.export_mixins import ExportCSVMixin
from futurex_openedx_extensions.helpers.pagination import DefaultPagination
from futurex_openedx_extensions.helpers.permissions import FXHasTenantCourseAccess
from futurex_openedx_extensions.helpers.roles import FXViewRoleInfoMixin
from futurex_openedx_extensions.helpers.routers import use_read_replica_if_available

default_auth_classes = FX_VIEW_DEFAULT_AUTH_CLASSES.copy()


@docs('PaymentOrdersView.get')
class PaymentOrdersView(ExportCSVMixin, FXViewRoleInfoMixin, ListAPIView):
    """View to list payment orders."""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    pagination_class = DefaultPagination
    fx_view_name = 'orders_list'
    serializer_class = CartSerializer
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/payments/v1/orders/: Get the list of orders'

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the view"""
        super().__init__()
        self._cached_course_map: dict = {}

    def get_course_map(self) -> dict:
        """
        Get the dict of prefetched courses.
        It will be used later in serializer context for optimization.
        """
        if self._cached_course_map:
            return self._cached_course_map
        return getattr(self.get_queryset(), 'courses_map', {})

    def get_queryset(self) -> QuerySet:
        """Get the list of payment orders"""
        course_ids = self.request.query_params.get('course_ids', '')
        user_ids = self.request.query_params.get('user_ids', '')
        usernames = self.request.query_params.get('usernames', '')

        date_serializer = serializers.ReportDateFilterSerializer(data=self.request.query_params)
        if not date_serializer.is_valid(raise_exception=False):
            raise ParseError(
                'Invalid dates. date_from and date_to must be formated as YYYY-MM-DD when provided.',
            )

        course_ids_list = [
            course.strip() for course in course_ids.split(',')
        ] if course_ids else None
        user_ids_list = [
            int(user.strip()) for user in user_ids.split(',') if user.strip().isdigit()
        ] if user_ids else None
        usernames_list = [
            username.strip() for username in usernames.split(',')
        ] if usernames else None

        status = self.request.query_params.get('status')
        if status and status not in Cart.valid_statuses():
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message=f'Invalid status: {status}, must be one of {Cart.valid_statuses()}.'
            )

        item_type = self.request.query_params.get('item_type')
        if item_type and item_type not in CatalogueItem.valid_item_types():
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message=f'Invalid item_type: {item_type}, must be one of {CatalogueItem.valid_item_types()}.'
            )

        qs = get_courses_orders_queryset(
            fx_permission_info=self.fx_permission_info,
            user_ids=user_ids_list,
            course_ids=course_ids_list,
            usernames=usernames_list,
            learner_search=self.request.query_params.get('learner_search'),
            course_search=self.request.query_params.get('course_search'),
            sku_search=self.request.query_params.get('sku_search'),
            include_staff=self.request.query_params.get('include_staff', '0') == '1',
            include_invoice=self.request.query_params.get('include_invoice', '0') == '1',
            include_user_details=self.request.query_params.get('include_user_details', '0') == '1',
            status=status,
            item_type=item_type,
            date_from=date_serializer.validated_data.get('date_from'),
            date_to=date_serializer.validated_data.get('date_to'),
        )
        self._cached_course_map = getattr(qs, 'courses_map', {})
        return qs

    def get_serializer_context(self) -> Dict[str, Any]:
        """Pass courses_map from the cached queryset to serializer context."""
        context = super().get_serializer_context()
        context['prefetched_courses'] = self.get_course_map()
        context['include_invoice'] = self.request.query_params.get('include_invoice', '0') == '1'
        context['include_user_details'] = self.request.query_params.get('include_user_details', '0') == '1'
        return context

    @use_read_replica_if_available
    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """GET /api/fx/payments/v1/orders/"""
        return super().get(request, *args, **kwargs)
