"""Views for the dashboard app"""
# pylint: disable=too-many-lines
from __future__ import annotations

import logging
import os
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage
from django.db.models.query import QuerySet
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django_filters.rest_framework import DjangoFilterBackend
from drf_yasg.utils import swagger_auto_schema
from edx_api_doc_tools import exclude_schema_for
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.exceptions import ParseError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from futurex_openedx_extensions.dashboard import serializers
from futurex_openedx_extensions.dashboard.docs_utils import docs
from futurex_openedx_extensions.dashboard.statistics.certificates import (
    get_certificates_count,
    get_learning_hours_count,
)
from futurex_openedx_extensions.dashboard.statistics.courses import (
    get_courses_count,
    get_courses_ratings,
    get_enrollments_count,
    get_enrollments_count_aggregated,
)
from futurex_openedx_extensions.dashboard.statistics.learners import get_learners_count
from futurex_openedx_extensions.helpers import clickhouse_operations as ch
from futurex_openedx_extensions.helpers.constants import (
    ALLOWED_FILE_EXTENSIONS,
    CLICKHOUSE_FX_BUILTIN_CA_USERS_OF_TENANTS,
    CLICKHOUSE_FX_BUILTIN_ORG_IN_TENANTS,
    CONFIG_FILES_UPLOAD_DIR,
    COURSE_ACCESS_ROLES_SUPPORTED_READ,
    FX_VIEW_DEFAULT_AUTH_CLASSES,
    RATING_RANGE,
)
from futurex_openedx_extensions.helpers.converters import error_details_to_dictionary
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.filters import DefaultOrderingFilter, DefaultSearchFilter
from futurex_openedx_extensions.helpers.models import ClickhouseQuery, DataExportTask
from futurex_openedx_extensions.helpers.pagination import DefaultPagination
from futurex_openedx_extensions.helpers.permissions import (
    FXHasTenantAllCoursesAccess,
    FXHasTenantCourseAccess,
    get_tenant_limited_fx_permission_info,
)
from futurex_openedx_extensions.helpers.roles import (
    FXViewRoleInfoMixin,
    get_usernames_with_access_roles,
)
from futurex_openedx_extensions.helpers.tenants import get_all_tenants_info
from futurex_openedx_extensions.helpers.upload import get_storage_dir, upload_file

# Constants
default_auth_classes = FX_VIEW_DEFAULT_AUTH_CLASSES.copy()
logger = logging.getLogger(__name__)


@docs('TotalCountsView.get')
class TotalCountsView(FXViewRoleInfoMixin, APIView):
    """
    View to get the total count statistics

    TODO: there is a better way to get info per tenant without iterating over all tenants
    """
    STAT_CERTIFICATES = 'certificates'
    STAT_COURSES = 'courses'
    STAT_ENROLLMENTS = 'enrollments'
    STAT_HIDDEN_COURSES = 'hidden_courses'
    STAT_LEARNERS = 'learners'
    STAT_LEARNING_HOURS = 'learning_hours'
    STAT_UNIQUE_LEARNERS = 'unique_learners'

    STAT_RESULT_KEYS = {
        STAT_CERTIFICATES: 'certificates_count',
        STAT_COURSES: 'courses_count',
        STAT_ENROLLMENTS: 'enrollments_count',
        STAT_HIDDEN_COURSES: 'hidden_courses_count',
        STAT_LEARNERS: 'learners_count',
        STAT_LEARNING_HOURS: 'learning_hours_count',
        STAT_UNIQUE_LEARNERS: 'unique_learners',
    }

    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    fx_view_name = 'total_counts_statistics'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/statistics/v1/total_counts/: Get the total count statistics'

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the view"""
        super().__init__()
        self.valid_stats = [
            self.STAT_CERTIFICATES, self.STAT_COURSES, self.STAT_ENROLLMENTS, self.STAT_HIDDEN_COURSES,
            self.STAT_LEARNERS, self.STAT_LEARNING_HOURS, self.STAT_UNIQUE_LEARNERS,
        ]
        self.stats: list[str] = []
        self.include_staff = False
        self.tenant_ids: list[int] = []

    def _get_certificates_count_data(self, one_tenant_permission_info: dict) -> int:
        """Get the count of certificates for the given tenant"""
        collector_result = get_certificates_count(one_tenant_permission_info, include_staff=self.include_staff)
        return sum(certificate_count for certificate_count in collector_result.values())

    @staticmethod
    def _get_courses_count_data(one_tenant_permission_info: dict, visible_filter: bool | None) -> int:
        """Get the count of courses for the given tenant"""
        collector_result = get_courses_count(one_tenant_permission_info, visible_filter=visible_filter)
        return sum(org_count['courses_count'] for org_count in collector_result)

    def _get_enrollments_count_data(self, one_tenant_permission_info: dict, visible_filter: bool | None) -> int:
        """Get the count of enrollments for the given tenant"""
        collector_result = get_enrollments_count(
            one_tenant_permission_info, visible_filter=visible_filter, include_staff=self.include_staff,
        )
        return sum(org_count['enrollments_count'] for org_count in collector_result)

    def _get_learners_count_data(self, one_tenant_permission_info: dict) -> int:
        """Get the count of learners for the given tenant"""
        return get_learners_count(one_tenant_permission_info, include_staff=self.include_staff)

    def _get_learning_hours_count_data(self, one_tenant_permission_info: dict) -> int:
        """Get the count of learning_hours for the given tenant"""
        return get_learning_hours_count(one_tenant_permission_info, include_staff=self.include_staff)

    def _get_stat_count(self, stat: str, tenant_id: int) -> Any:
        """Get the count of the given stat for the given tenant"""
        if stat == self.STAT_UNIQUE_LEARNERS:
            return get_learners_count(self.fx_permission_info, self.include_staff)

        one_tenant_permission_info = get_tenant_limited_fx_permission_info(self.fx_permission_info, tenant_id)
        if stat == self.STAT_CERTIFICATES:
            result = self._get_certificates_count_data(one_tenant_permission_info)

        elif stat == self.STAT_COURSES:
            result = self._get_courses_count_data(one_tenant_permission_info, visible_filter=True)

        elif stat == self.STAT_ENROLLMENTS:
            result = self._get_enrollments_count_data(one_tenant_permission_info, visible_filter=True)

        elif stat == self.STAT_HIDDEN_COURSES:
            result = self._get_courses_count_data(one_tenant_permission_info, visible_filter=False)

        elif stat == self.STAT_LEARNING_HOURS:
            result = self._get_learning_hours_count_data(one_tenant_permission_info)

        else:
            result = self._get_learners_count_data(one_tenant_permission_info)

        return result

    def _load_query_params(self, request: Any) -> None:
        """Load the query parameters"""
        self.stats = request.query_params.get('stats', '').split(',')
        invalid_stats = list(set(self.stats) - set(self.valid_stats))
        if invalid_stats:
            raise ParseError(f'Invalid stats type: {invalid_stats}')
        self.include_staff = request.query_params.get('include_staff', '0') == '1'
        self.tenant_ids = self.fx_permission_info['view_allowed_tenant_ids_any_access']

    def _construct_result(self) -> dict:
        """Construct the result dictionary"""
        if self.STAT_UNIQUE_LEARNERS in self.stats:
            total_unique_learners = self._get_stat_count(self.STAT_UNIQUE_LEARNERS, 0)
            self.stats.remove(self.STAT_UNIQUE_LEARNERS)
        else:
            total_unique_learners = None
        result: dict[Any, Any] = dict({tenant_id: {} for tenant_id in self.tenant_ids})
        result.update({
            f'total_{self.STAT_RESULT_KEYS[stat]}': 0 for stat in self.stats
        })

        for tenant_id in self.tenant_ids:
            for stat in self.stats:
                count = int(self._get_stat_count(stat, tenant_id))
                result[tenant_id][self.STAT_RESULT_KEYS[stat]] = count
                result[f'total_{self.STAT_RESULT_KEYS[stat]}'] += count

        if total_unique_learners is not None:
            result['total_unique_learners'] = total_unique_learners

        result['limited_access'] = self.fx_permission_info['view_allowed_course_access_orgs'] != []

        return result

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response | JsonResponse:
        """Returns the total count statistics for the selected tenants."""
        self._load_query_params(request)

        return JsonResponse(self._construct_result())


@docs('AggregatedCountsView.get')
class AggregatedCountsView(TotalCountsView):  # pylint: disable=too-many-instance-attributes
    """
    View to get the aggregated count statistics
    """
    AGGREGATE_PERIOD_DAY = 'day'
    AGGREGATE_PERIOD_MONTH = 'month'
    AGGREGATE_PERIOD_QUARTER = 'quarter'
    AGGREGATE_PERIOD_YEAR = 'year'

    VALID_AGGREGATE_PERIOD = [
        AGGREGATE_PERIOD_DAY, AGGREGATE_PERIOD_MONTH, AGGREGATE_PERIOD_YEAR, AGGREGATE_PERIOD_QUARTER,
    ]

    fx_view_name = 'aggregated_counts_statistics'
    fx_view_description = 'api/fx/statistics/v1/aggregated_counts/: Get the total count statistics with aggregate'

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the view"""
        super().__init__()
        self.valid_stats = [self.STAT_ENROLLMENTS]
        self.aggregate_period = self.AGGREGATE_PERIOD_DAY
        self.date_to: date | None = None
        self.date_from: date | None = None
        self.favors_backward = True
        self.max_period_chunks = 0
        self.fill_missing_periods = True

    def _load_query_params(self, request: Any) -> None:
        """Load the query parameters"""
        super()._load_query_params(request)

        aggregate_period = request.query_params.get('aggregate_period')
        if aggregate_period is None or aggregate_period not in self.VALID_AGGREGATE_PERIOD:
            raise ParseError(f'Invalid aggregate_period: {aggregate_period}')

        self.favors_backward = request.query_params.get('favors_backward', '1') == '1'

        try:
            self.max_period_chunks = int(request.query_params.get('max_period_chunks', 0))
        except ValueError as exc:
            raise ParseError('Invalid max_period_chunks. It must be an integer.') from exc

        if self.max_period_chunks < 0 or self.max_period_chunks > settings.FX_MAX_PERIOD_CHUNKS_MAP[aggregate_period]:
            self.max_period_chunks = 0

        self.aggregate_period = aggregate_period

        self.fill_missing_periods = request.query_params.get('fill_missing_periods', '1') == '1'

        serializer = serializers.ReportDateFilterSerializer(data=request.query_params)
        if not serializer.is_valid(raise_exception=False):
            raise ParseError(
                'Invalid dates. date_from and date_to must be formated as YYYY-MM-DD when provided.',
            )
        self.date_from = serializer.validated_data.get('date_from')
        self.date_to = serializer.validated_data.get('date_to')

    def _get_certificates_count_data(self, one_tenant_permission_info: dict) -> int:
        """Get the count of certificates for the given tenant"""
        raise NotImplementedError('Certificates count is not supported for aggregated counts yet')

    @staticmethod
    def _get_courses_count_data(one_tenant_permission_info: dict, visible_filter: bool | None) -> int:
        """Get the count of courses for the given tenant"""
        raise NotImplementedError('Courses count is not supported for aggregated counts yet')

    def _get_enrollments_count_data(  # type: ignore
        self, one_tenant_permission_info: dict, visible_filter: bool | None,
    ) -> tuple[list, datetime | None, datetime | None]:
        """Get the count of enrollments for the given tenant"""
        collector_result, calculated_from, calculated_to = get_enrollments_count_aggregated(
            one_tenant_permission_info,
            visible_filter=visible_filter,
            include_staff=self.include_staff,
            aggregate_period=self.aggregate_period,
            date_from=self.date_from,
            date_to=self.date_to,
            favors_backward=self.favors_backward,
            max_period_chunks=self.max_period_chunks,
        )
        return [
            {'label': item['period'], 'value': item['enrollments_count']} for item in collector_result
        ], calculated_from, calculated_to

    def _get_learners_count_data(self, one_tenant_permission_info: dict) -> int:
        """Get the count of learners for the given tenant"""
        raise NotImplementedError('Learners count is not supported for aggregated counts yet')

    def _get_learning_hours_count_data(self, one_tenant_permission_info: dict) -> int:
        """Get the count of learning_hours for the given tenant"""
        raise NotImplementedError('Learning hours count is not supported for aggregated counts yet')

    @staticmethod
    def get_period_label(aggregate_period: str, the_date: date | datetime) -> str:
        """Get the period label"""
        if not isinstance(the_date, (date, datetime)):
            raise ValidationError(f'the_date must be a date or datetime object. Got ({the_date.__class__.__name__})')

        match aggregate_period:
            case AggregatedCountsView.AGGREGATE_PERIOD_DAY:
                result = the_date.strftime('%Y-%m-%d')

            case AggregatedCountsView.AGGREGATE_PERIOD_MONTH:
                result = the_date.strftime('%Y-%m')

            case AggregatedCountsView.AGGREGATE_PERIOD_QUARTER:
                result = f'{the_date.year}-Q{((the_date.month - 1) // 3) + 1}'

            case AggregatedCountsView.AGGREGATE_PERIOD_YEAR:
                result = str(the_date.year)

            case _:
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT,
                    message=f'Invalid aggregate_period: {aggregate_period}',
                )

        return result

    @staticmethod
    def get_next_period_date(aggregate_period: str, the_date: date | datetime) -> date | datetime:
        """Get the next period date"""
        if not isinstance(the_date, (date, datetime)):
            raise ValidationError(f'the_date must be a date or datetime object. Got ({the_date.__class__.__name__})')

        match aggregate_period:
            case AggregatedCountsView.AGGREGATE_PERIOD_DAY:
                result = the_date + timedelta(days=1)

            case AggregatedCountsView.AGGREGATE_PERIOD_MONTH:
                result = the_date.replace(day=1) + relativedelta(months=1)

            case AggregatedCountsView.AGGREGATE_PERIOD_QUARTER:
                result = the_date.replace(day=1).replace(
                    month=((the_date.month - 1) // 3) * 3 + 1,
                ) + relativedelta(months=3)

            case AggregatedCountsView.AGGREGATE_PERIOD_YEAR:
                result = the_date.replace(day=1, month=1) + relativedelta(years=1)

            case _:
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT,
                    message=f'Invalid aggregate_period: {aggregate_period}',
                )

        return result

    def get_data_with_missing_periods(
        self, data: list[dict[str, Any]], already_sorted: bool = False,
    ) -> list[dict[str, Any]]:
        """Get the date with missing periods."""
        data = sorted(data, key=lambda x: x['label']) if not already_sorted else data

        if not self.date_from or not self.date_to:
            return data

        result = []
        current_date = self.date_from
        for item in data:
            current_label = self.get_period_label(self.aggregate_period, current_date)
            while item['label'] != current_label:
                result.append({'label': current_label, 'value': 0})
                current_date = self.get_next_period_date(self.aggregate_period, current_date)
                current_label = self.get_period_label(self.aggregate_period, current_date)
                if current_date > self.date_to:
                    break
            if current_date > self.date_to:
                break
            result.append(item)
            current_date = self.get_next_period_date(self.aggregate_period, current_date)

        while current_date <= self.date_to:
            result.append({'label': self.get_period_label(self.aggregate_period, current_date), 'value': 0})
            current_date = self.get_next_period_date(self.aggregate_period, current_date)

        return result

    def _construct_result(self) -> dict:
        """Construct the result dictionary"""
        result: dict[Any, Any] = {
            'query_settings': {
                'aggregate_period': self.aggregate_period,
            },
            'by_tenant': [],
            'all_tenants': {
                self.STAT_RESULT_KEYS[stat]: [] for stat in self.stats
            },
        }

        all_tenants = result['all_tenants']
        all_tenants['totals'] = {
            self.STAT_RESULT_KEYS[stat]: 0 for stat in self.stats
        }
        _by_period: dict[str, Any] = {
            self.STAT_RESULT_KEYS[stat]: {} for stat in self.stats
        }
        for tenant_id in self.tenant_ids:
            tenant_data: dict[str, Any] = {
                'tenant_id': tenant_id,
                'totals': {},
            }
            for stat in self.stats:
                key = self.STAT_RESULT_KEYS[stat]
                data = self._get_stat_count(stat, tenant_id)
                self.date_from = data[1]
                self.date_to = data[2]

                if self.fill_missing_periods:
                    full_details = self.get_data_with_missing_periods(data[0], already_sorted=True)
                else:
                    full_details = data[0]
                tenant_data[key] = full_details
                count = sum(item['value'] for item in full_details)
                tenant_data['totals'][key] = count

                all_tenants['totals'][key] += count
                for item in full_details:
                    _by_period[key][item['label']] = _by_period[key].get(item['label'], 0) + item['value']

            result['by_tenant'].append(tenant_data)

        for stat in self.stats:
            key = self.STAT_RESULT_KEYS[stat]
            _by_period[key] = dict(sorted(_by_period[key].items()))
            for item in _by_period[key]:
                all_tenants[key].append({
                    'label': item,
                    'value': _by_period[key][item],
                })

        result['limited_access'] = self.fx_permission_info['view_allowed_course_access_orgs'] != []
        result['query_settings']['date_from'] = self.date_from
        result['query_settings']['date_to'] = self.date_to

        return result

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """Returns the total count statistics for the selected tenants."""
        self._load_query_params(request)

        return Response(serializers.AggregatedCountsSerializer(self._construct_result()).data)


@docs('DataExportManagementView.list')
@docs('DataExportManagementView.partial_update')
@docs('DataExportManagementView.retrieve')
class DataExportManagementView(FXViewRoleInfoMixin, viewsets.ModelViewSet):  # pylint: disable=too-many-ancestors
    """View to list and retrieve data export tasks."""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    serializer_class = serializers.DataExportTaskSerializer
    pagination_class = DefaultPagination
    fx_view_name = 'exported_files_data'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_default_read_write_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_allowed_write_methods = ['PATCH']
    fx_view_description = 'api/fx/export/v1/tasks/: Data Export Task Management APIs.'
    http_method_names = ['get', 'patch']
    filter_backends = [DjangoFilterBackend, DefaultOrderingFilter, DefaultSearchFilter]
    filterset_fields = ['related_id', 'view_name']
    ordering = ['-id']
    search_fields = ['filename', 'notes']

    def get_queryset(self) -> QuerySet:
        """Get the list of user tasks."""
        return DataExportTask.objects.filter(
            user=self.request.user,
            tenant__id__in=self.fx_permission_info['view_allowed_tenant_ids_any_access']
        )

    def get_object(self) -> DataExportTask:
        """Override to ensure that the user can only retrieve their own tasks."""
        task_id = self.kwargs.get('pk')  # Use 'pk' for the default lookup
        task = get_object_or_404(DataExportTask, id=task_id, user=self.request.user)
        return task


@docs('GlobalRatingView.get')
class GlobalRatingView(FXViewRoleInfoMixin, APIView):
    """View to get the global rating for a single tenant"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    fx_view_name = 'global_rating'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/statistics/v1/rating/: Get the global rating for courses in a single tenant'

    def get(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:
        """
        GET /api/fx/statistics/v1/rating/?tenant_ids=<tenantId>

        <tenantId> (required): a single tenant ID to get the rating information for.
        Multiple tenant IDs are not supported - only one tenant ID must be provided.
        """
        tenant_id = self.verify_one_tenant_id_provided(request)

        data_result = get_courses_ratings(tenant_id=tenant_id)
        rating_counts = {str(i): data_result[f'rating_{i}_count'] for i in RATING_RANGE}
        total_count = sum(rating_counts.values())

        result = {
            'total_rating': data_result['total_rating'],
            'total_count': total_count,
            'courses_count': data_result['courses_count'],
            'rating_counts': rating_counts,
        }

        return JsonResponse(result)


@docs('TenantInfoView.get')
class TenantInfoView(FXViewRoleInfoMixin, APIView):
    """View to get the list of excluded tenants"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    fx_view_name = 'tenant_info'
    fx_default_read_only_roles = COURSE_ACCESS_ROLES_SUPPORTED_READ.copy()
    fx_view_description = 'api/fx/tenants/v1/info/<tenant_id>/: tenant basic information'

    def get(
        self, request: Any, tenant_id: str, *args: Any, **kwargs: Any,
    ) -> JsonResponse | Response:
        """Get the tenant's information by tenant ID"""
        if int(tenant_id) not in self.request.fx_permission_info['view_allowed_tenant_ids_any_access']:
            return Response(
                error_details_to_dictionary(reason='You do not have access to this tenant'),
                status=http_status.HTTP_403_FORBIDDEN,
            )

        result = {'tenant_id': int(tenant_id)}
        result.update(get_all_tenants_info()['info'].get(int(tenant_id)))
        return JsonResponse(result)


@exclude_schema_for('get')
class ClickhouseQueryView(FXViewRoleInfoMixin, APIView):
    """View to get the Clickhouse query"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    fx_view_name = 'clickhouse_query_fetcher'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/query/v1/<scope>/<slug>: Get result of the related clickhouse query'

    @staticmethod
    def get_page_url_with_page(url: str, new_page_no: int | None) -> str | None:
        """
        Get the URL with the new page number

        :param url: The URL
        :type url: str
        :param new_page_no: The new page number
        :type new_page_no: int | None
        :return: The URL with the new page number
        :rtype: str | None
        """
        if new_page_no is None:
            return None

        url_parts = urlsplit(url)
        query_params = parse_qs(url_parts.query)

        page_size = query_params.get(DefaultPagination.page_size_query_param, None)
        if page_size:
            del query_params[DefaultPagination.page_size_query_param]

        if 'page' in query_params:
            del query_params['page']

        if page_size:
            query_params[DefaultPagination.page_size_query_param] = page_size
        query_params['page'] = [str(new_page_no)]

        new_query_string = urlencode(query_params, doseq=True)

        new_url_parts = (url_parts.scheme, url_parts.netloc, url_parts.path, new_query_string, url_parts.fragment)
        new_full_url = urlunsplit(new_url_parts)
        return new_full_url

    @staticmethod
    def pop_out_page_params(params: Dict[str, str], paginated: bool) -> tuple[int | None, int]:
        """
        Pop out the page and page size parameters, and return them as integers in the result. Always return the page
        as None if not paginated

        :param params: The parameters
        :type params: Dict[str, str]
        :param paginated: Whether the query is paginated
        :type paginated: bool
        :return: The page and page size parameters
        :rtype: tuple[int | None, int]
        """
        page_str: str | None = params.pop('page', None)
        page_size_str: str = params.pop(
            DefaultPagination.page_size_query_param, ''
        ) or str(DefaultPagination.page_size)

        if not paginated:
            page = None
        else:
            page = int(page_str) if page_str is not None else page_str
            page = 1 if page is None else page

        return page, int(page_size_str)

    def get(self, request: Any, scope: str, slug: str) -> JsonResponse | Response:
        """
        GET /api/fx/query/v1/<scope>/<slug>/

        :param request: The request object
        :type request: Request
        :param scope: The scope of the query (course, tenant, user)
        :type scope: str
        :param slug: The slug of the query
        :type slug: str
        """
        clickhouse_query = ClickhouseQuery.get_query_record(scope, 'v1', slug)
        if not clickhouse_query:
            return Response(
                error_details_to_dictionary(reason=f'Query not found {scope}.v1.{slug}'),
                status=http_status.HTTP_404_NOT_FOUND
            )

        if not clickhouse_query.enabled:
            return Response(
                error_details_to_dictionary(reason=f'Query is disabled {scope}.v1.{slug}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        params = request.query_params.dict()
        self.get_page_url_with_page(request.build_absolute_uri(), 9)

        page, page_size = self.pop_out_page_params(params, clickhouse_query.paginated)

        orgs = request.fx_permission_info['view_allowed_any_access_orgs'].copy()
        params[CLICKHOUSE_FX_BUILTIN_ORG_IN_TENANTS] = orgs
        if CLICKHOUSE_FX_BUILTIN_CA_USERS_OF_TENANTS in clickhouse_query.query:
            params[CLICKHOUSE_FX_BUILTIN_CA_USERS_OF_TENANTS] = get_usernames_with_access_roles(orgs)

        error_response = None
        try:
            clickhouse_query.fix_param_types(params)

            with ch.get_client() as clickhouse_client:
                records_count, next_page, result = ch.execute_query(
                    clickhouse_client,
                    query=clickhouse_query.query,
                    parameters=params,
                    page=page,
                    page_size=page_size,
                )

        except EmptyPage as exc:
            error_response = Response(
                error_details_to_dictionary(reason=str(exc)), status=http_status.HTTP_404_NOT_FOUND
            )
        except (ch.ClickhouseClientNotConfiguredError, ch.ClickhouseClientConnectionError) as exc:
            error_response = Response(
                error_details_to_dictionary(reason=str(exc)), status=http_status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except (ch.ClickhouseBaseError, ValueError) as exc:
            error_response = Response(
                error_details_to_dictionary(reason=str(exc)), status=http_status.HTTP_400_BAD_REQUEST
            )
        except ValidationError as exc:
            error_response = Response(
                error_details_to_dictionary(reason=exc.message), status=http_status.HTTP_400_BAD_REQUEST
            )

        if error_response:
            return error_response

        if clickhouse_query.paginated:
            return JsonResponse({
                'count': records_count,
                'next': self.get_page_url_with_page(request.build_absolute_uri(), next_page),
                'previous': self.get_page_url_with_page(
                    request.build_absolute_uri(),
                    None if page == 1 else page - 1 if page else None,
                ),
                'results': ch.result_to_json(result),
            })

        return JsonResponse(ch.result_to_json(result), safe=False)


class FileUploadView(FXViewRoleInfoMixin, APIView):
    """View to upload file"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'upload_file'
    fx_view_description = 'api/fx/file/v1/upload/: Upload file'
    fx_default_read_write_roles = ['staff', 'fx_api_access_global']
    fx_default_read_only_roles = ['staff', 'fx_api_access_global']

    parser_classes = [MultiPartParser]

    @swagger_auto_schema(
        request_body=serializers.FileUploadSerializer,
    )
    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """
        POST /api/fx/file/v1/upload/

        Validates the payload, saves the file, and returns the file URL.
        """
        serializer = serializers.FileUploadSerializer(data=request.data, context={'request': self.request})

        if not serializer.is_valid():
            return Response(serializer.errors, status=http_status.HTTP_400_BAD_REQUEST)

        file = serializer.validated_data['file']
        slug = serializer.validated_data['slug']
        tenant_id = serializer.validated_data['tenant_id']

        file_extension = os.path.splitext(file.name)[1]
        if file_extension.lower() not in ALLOWED_FILE_EXTENSIONS:
            return Response(
                error_details_to_dictionary(
                    reason=f'Invalid file type. Allowed types are {ALLOWED_FILE_EXTENSIONS}.'
                ),
                status=http_status.HTTP_400_BAD_REQUEST
            )
        short_uuid = uuid.uuid4().hex[:8]
        file_name = f'{slug}-{short_uuid}{file_extension}'
        storage_path = os.path.join(get_storage_dir(tenant_id, CONFIG_FILES_UPLOAD_DIR), file_name)
        return Response(
            {'url': upload_file(storage_path, file), 'uuid': short_uuid},
            status=http_status.HTTP_201_CREATED
        )


class SetThemePreviewCookieView(APIView):
    """View to set theme preview cookie"""
    def get(self, request: Any) -> Any:  # pylint: disable=no-self-use
        """Set theme preview cookie"""
        next_url = request.GET.get('next', request.build_absolute_uri())
        if request.COOKIES.get('theme-preview') == 'yes':
            return redirect(next_url)

        return render(request, template_name='set_theme_preview.html', context={'next_url': next_url})
