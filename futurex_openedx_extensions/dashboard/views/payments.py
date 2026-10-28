"""Views for the dashboard app - payments feature"""
# pylint: disable=duplicate-code

from __future__ import annotations

from typing import Any, Dict

from django.db.models.query import QuerySet
from eox_tenant.models import TenantConfig
from rest_framework import status as http_status
from rest_framework.exceptions import ParseError
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from zeitlabs_payments.models import Cart, CatalogueItem
from zeitlabs_payments.serializers import CartSerializer

from futurex_openedx_extensions.dashboard import serializers
from futurex_openedx_extensions.dashboard.details.courses import get_courses_orders_queryset, get_invoices_queryset
from futurex_openedx_extensions.dashboard.docs_utils import docs
from futurex_openedx_extensions.helpers.constants import FX_VIEW_DEFAULT_AUTH_CLASSES
from futurex_openedx_extensions.helpers.converters import error_details_to_dictionary
from futurex_openedx_extensions.helpers.course_price import (
    CoursePriceConflict,
    get_course_overview,
    get_course_price_info,
    set_course_price,
)
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.export_mixins import ExportCSVMixin
from futurex_openedx_extensions.helpers.pagination import DefaultPagination
from futurex_openedx_extensions.helpers.payments import (
    get_masked_payment_settings,
    get_tenant_payment_status,
    update_tenant_payment_configs,
)
from futurex_openedx_extensions.helpers.permissions import (
    FXHasTenantAllCoursesAccess,
    FXHasTenantCourseAccess,
    IsSystemStaff,
)
from futurex_openedx_extensions.helpers.roles import FXViewRoleInfoMixin
from futurex_openedx_extensions.helpers.routers import use_read_replica_if_available
from futurex_openedx_extensions.helpers.tenants import get_tenant_site

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


@docs('PaymentOrdersViewV2.get')
class PaymentOrdersViewV2(ExportCSVMixin, FXViewRoleInfoMixin, ListAPIView):
    """View to list payment orders (v2) with a flat shape including learner fields and invoice URL."""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    pagination_class = DefaultPagination
    fx_view_name = 'orders_list_v2'
    serializer_class = serializers.PaymentOrderV2Serializer
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/payments/v2/orders/: Get the list of orders (v2)'

    def get_queryset(self) -> QuerySet:
        """Get the list of payment orders for v2."""
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
            include_invoice=True,
            include_user_details=True,
            status=status,
            item_type=item_type,
        )

        # v2 filters by the invoice's paid_at; the cart's created_at stays display-only.
        paid_at_filter = {}
        date_from = date_serializer.validated_data.get('date_from')
        date_to = date_serializer.validated_data.get('date_to')
        if date_from:
            paid_at_filter['invoices__paid_at__date__gte'] = date_from
        if date_to:
            paid_at_filter['invoices__paid_at__date__lte'] = date_to
        if paid_at_filter:
            qs = qs.filter(**paid_at_filter).distinct()

        return qs

    @use_read_replica_if_available
    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """GET /api/fx/payments/v2/orders/"""
        return super().get(request, *args, **kwargs)


@docs('PaymentInvoicesView.get')
class PaymentInvoicesView(FXViewRoleInfoMixin, ListAPIView):
    """View to list the invoices of the accessible courses."""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    pagination_class = DefaultPagination
    fx_view_name = 'payments_invoices'
    serializer_class = serializers.PaymentInvoiceSerializer
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/payments/v1/invoices/: Get the list of invoices'

    def get_queryset(self) -> QuerySet:
        """Get the list of invoices"""
        course_ids = self.request.query_params.get('course_ids', '')
        date_serializer = serializers.ReportDateFilterSerializer(data=self.request.query_params)
        if not date_serializer.is_valid(raise_exception=False):
            raise ParseError(
                'Invalid dates. date_from and date_to must be formated as YYYY-MM-DD when provided.',
            )

        return get_invoices_queryset(
            fx_permission_info=self.fx_permission_info,
            course_ids=[course.strip() for course in course_ids.split(',')] if course_ids else None,
            date_from=date_serializer.validated_data.get('date_from'),
            date_to=date_serializer.validated_data.get('date_to'),
        )

    @use_read_replica_if_available
    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """GET /api/fx/payments/v1/invoices/"""
        return super().get(request, *args, **kwargs)


@docs('PaymentInvoiceDetailView.get')
class PaymentInvoiceDetailView(FXViewRoleInfoMixin, APIView):
    """View to get one invoice of the accessible courses."""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    fx_view_name = 'payments_invoice_detail'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/payments/v1/invoices/<invoice_number>/: Get one invoice'

    @use_read_replica_if_available
    def get(self, request: Any, invoice_number: str) -> Response:
        """GET /api/fx/payments/v1/invoices/<invoice_number>/"""
        invoice = get_invoices_queryset(fx_permission_info=self.fx_permission_info).filter(
            invoice_number=invoice_number,
        ).first()
        if not invoice:
            return Response(
                error_details_to_dictionary(reason=f'Invoice not found: {invoice_number}'),
                status=http_status.HTTP_404_NOT_FOUND,
            )
        return Response(serializers.PaymentInvoiceSerializer(invoice, context={'request': request}).data)


@docs('TenantPaymentsStatusView.get')
class TenantPaymentsStatusView(FXViewRoleInfoMixin, APIView):
    """View to get the payments status of the accessible tenants."""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'payments_tenants_status'
    fx_default_read_only_roles = ['staff', 'fx_api_access_global']
    fx_view_description = 'api/fx/payments/v1/tenants/: Get the payments status of the tenants'

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """GET /api/fx/payments/v1/tenants/"""
        tenant_ids = sorted(self.fx_permission_info['view_allowed_tenant_ids_full_access'])
        configs = dict(TenantConfig.objects.filter(id__in=tenant_ids).values_list('id', 'lms_configs'))
        return Response([
            {
                'tenant_id': tenant_id,
                'domain': get_tenant_site(tenant_id),
                **get_tenant_payment_status(configs.get(tenant_id) or {}),
            } for tenant_id in tenant_ids
        ])


@docs('TenantPaymentsSettingsView.get')
@docs('TenantPaymentsSettingsView.patch')
class TenantPaymentsSettingsView(APIView):
    """View to read and change the payments settings of one tenant. System staff only."""
    authentication_classes = default_auth_classes
    permission_classes = [IsSystemStaff]

    @staticmethod
    def _settings_data(tenant_id: int, lms_configs: dict) -> Dict[str, Any]:
        """Return the status and the masked settings of a tenant"""
        return {
            'tenant_id': tenant_id,
            'domain': get_tenant_site(tenant_id),
            **get_tenant_payment_status(lms_configs),
            'settings': get_masked_payment_settings(lms_configs),
        }

    def get(self, request: Any, tenant_id: int) -> Response:
        """GET /api/fx/payments/v1/tenants/<tenant_id>/"""
        lms_configs = TenantConfig.objects.filter(id=int(tenant_id)).values_list('lms_configs', flat=True).first()
        if lms_configs is None:
            return Response(
                error_details_to_dictionary(reason=f'Unable to find tenant with id: {tenant_id}'),
                status=http_status.HTTP_404_NOT_FOUND,
            )
        return Response(self._settings_data(int(tenant_id), lms_configs))

    def patch(self, request: Any, tenant_id: int) -> Response:
        """PATCH /api/fx/payments/v1/tenants/<tenant_id>/"""
        try:
            lms_configs = update_tenant_payment_configs(int(tenant_id), request.data, request.user)
        except FXCodedException as exc:
            return Response(
                error_details_to_dictionary(reason=f'({exc.code}) {str(exc)}'),
                status=(
                    http_status.HTTP_404_NOT_FOUND if exc.code == FXExceptionCodes.TENANT_NOT_FOUND.value
                    else http_status.HTTP_400_BAD_REQUEST
                ),
            )
        return Response(self._settings_data(int(tenant_id), lms_configs))


@docs('CoursePriceView.get')
@docs('CoursePriceView.put')
class CoursePriceView(APIView):
    """View to read and set the price of a course, with its payment readiness. System staff only."""
    authentication_classes = default_auth_classes
    permission_classes = [IsSystemStaff]

    @staticmethod
    def _course_not_found(course_id: str) -> Response:
        """Return the course-not-found response"""
        return Response(
            error_details_to_dictionary(reason=f'Course not found: {course_id}'),
            status=http_status.HTTP_404_NOT_FOUND,
        )

    def get(self, request: Any, course_id: str, *args: Any, **kwargs: Any) -> Response:
        """GET /api/fx/payments/v1/courses/<course_id>/price/"""
        course = get_course_overview(course_id)
        if not course:
            return self._course_not_found(course_id)
        return Response(get_course_price_info(course))

    def put(self, request: Any, course_id: str, *args: Any, **kwargs: Any) -> Response:
        """PUT /api/fx/payments/v1/courses/<course_id>/price/"""
        course = get_course_overview(course_id)
        if not course:
            return self._course_not_found(course_id)
        if not isinstance(request.data, dict) or 'price' not in request.data:
            return Response(
                error_details_to_dictionary(reason='Missing required parameter: price'),
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = set_course_price(course, request.data['price'], request.data.get('sku'), request.user)
        except CoursePriceConflict as exc:
            return Response(error_details_to_dictionary(reason=str(exc)), status=http_status.HTTP_409_CONFLICT)
        except FXCodedException as exc:
            return Response(
                error_details_to_dictionary(reason=f'({exc.code}) {str(exc)}'),
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        return Response(result)
