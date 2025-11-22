"""Views for the dashboard app"""
# pylint: disable=too-many-lines
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from common.djangoapps.student.models import get_user_by_username_or_email
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.paginator import EmptyPage
from django.db import transaction
from django.db.models.query import QuerySet
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django_filters.rest_framework import DjangoFilterBackend
from drf_yasg.utils import swagger_auto_schema
from edx_api_doc_tools import exclude_schema_for
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.exceptions import ParseError, PermissionDenied
from rest_framework.generics import ListAPIView
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from futurex_openedx_extensions.dashboard import serializers
from futurex_openedx_extensions.dashboard.details.courses import (
    get_courses_feedback_queryset,
    get_courses_queryset,
    get_learner_courses_info_queryset,
)
from futurex_openedx_extensions.dashboard.details.learners import (
    get_learner_info_queryset,
    get_learners_by_course_queryset,
    get_learners_enrollments_queryset,
    get_learners_queryset,
)
from futurex_openedx_extensions.dashboard.docs_utils import docs
from futurex_openedx_extensions.dashboard.statistics.certificates import (
    get_certificates_count,
    get_learning_hours_count,
)
from futurex_openedx_extensions.dashboard.statistics.courses import (
    get_courses_count,
    get_courses_count_by_status,
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
    COURSE_ACCESS_ROLES_STAFF_EDITOR,
    COURSE_ACCESS_ROLES_SUPPORTED_READ,
    COURSE_STATUS_SELF_PREFIX,
    COURSE_STATUSES,
    FX_VIEW_DEFAULT_AUTH_CLASSES,
)
from futurex_openedx_extensions.helpers.course_categories import CourseCategories
from futurex_openedx_extensions.helpers.converters import dict_to_hash, error_details_to_dictionary
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.export_mixins import ExportCSVMixin
from futurex_openedx_extensions.helpers.filters import DefaultOrderingFilter, DefaultSearchFilter
from futurex_openedx_extensions.helpers.library import get_accessible_libraries
from futurex_openedx_extensions.helpers.models import ClickhouseQuery, ConfigAccessControl, DataExportTask, TenantAsset
from futurex_openedx_extensions.helpers.pagination import DefaultPagination
from futurex_openedx_extensions.helpers.permissions import (
    FXHasTenantAllCoursesAccess,
    FXHasTenantCourseAccess,
    IsAnonymousOrSystemStaff,
    IsSystemStaff,
    get_tenant_limited_fx_permission_info,
)
from futurex_openedx_extensions.helpers.roles import (
    FXViewRoleInfoMixin,
    add_course_access_roles,
    delete_course_access_roles,
    get_accessible_tenant_ids,
    get_course_access_roles_queryset,
    get_usernames_with_access_roles,
    update_course_access_roles,
)
from futurex_openedx_extensions.helpers.tenants import (
    create_new_tenant_config,
    delete_draft_tenant_config,
    get_accessible_config_keys,
    get_all_tenants_info,
    get_draft_tenant_config,
    get_excluded_tenant_ids,
    get_tenant_config,
    get_tenants_info,
    publish_tenant_config,
    update_draft_tenant_config, get_tenants_by_org,
)
from futurex_openedx_extensions.helpers.upload import get_storage_dir, upload_file
from futurex_openedx_extensions.helpers.users import get_user_by_key

default_auth_classes = FX_VIEW_DEFAULT_AUTH_CLASSES.copy()


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

        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        try:
            self.date_from = datetime.strptime(date_from, '%Y-%m-%d').date() if date_from else None
            self.date_to = datetime.strptime(date_to, '%Y-%m-%d').date() if date_to else None
        except (ValueError, TypeError) as exc:
            raise ParseError(
                'Invalid dates. You must provide a valid date_from and date_to formated as YYYY-MM-DD'
            ) from exc

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


@docs('LearnersView.get')
class LearnersView(ExportCSVMixin, FXViewRoleInfoMixin, ListAPIView):
    """View to get the list of learners"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    serializer_class = serializers.LearnerDetailsSerializer
    pagination_class = DefaultPagination
    fx_view_name = 'learners_list'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/learners/v1/learners/: Get the list of learners'

    def get_queryset(self) -> QuerySet:
        """Get the list of learners"""
        search_text = self.request.query_params.get('search_text')
        include_staff = self.request.query_params.get('include_staff', '0') == '1'
        min_enrollments_count = self.request.query_params.get('min_enrollments_count', -1)
        max_enrollments_count = self.request.query_params.get('max_enrollments_count', -1)

        try:
            min_enrollments_count = int(min_enrollments_count)
            max_enrollments_count = int(max_enrollments_count)
        except ValueError:
            pass  # let get_learners_queryset handle the invalid values

        return get_learners_queryset(
            fx_permission_info=self.fx_permission_info,
            search_text=search_text,
            include_staff=include_staff,
            enrollments_filter=(min_enrollments_count, max_enrollments_count),
        )


@docs('CoursesView.get')
@docs('CoursesView.post')
class CoursesView(ExportCSVMixin, FXViewRoleInfoMixin, ListAPIView):
    """View to get the list of courses"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    serializer_class = serializers.CourseDetailsSerializer
    pagination_class = DefaultPagination
    filter_backends = [DefaultOrderingFilter]
    ordering_fields = [
        'id', 'self_paced', 'enrolled_count', 'active_count',
        'certificates_count', 'display_name', 'org', 'completion_rate',
    ]
    ordering = ['display_name']
    fx_view_name = 'courses_list'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/courses/v1/courses/: Get the list of courses'

    def get_queryset(self) -> QuerySet:
        """Get the list of learners"""
        search_text = self.request.query_params.get('search_text')
        include_staff = self.request.query_params.get('include_staff')

        return get_courses_queryset(
            fx_permission_info=self.fx_permission_info,
            search_text=search_text,
            visible_filter=None,
            include_staff=include_staff,
        )

    def post(self, request: Any) -> Response | JsonResponse:  # pylint: disable=no-self-use
        """POST /api/fx/courses/v1/courses/"""
        serializer = serializers.CourseCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            created_course = serializer.save()
            return JsonResponse({
                'id': str(created_course.id),
                'url': serializer.get_absolute_url(),
            })

        return Response(
            {'errors': serializer.errors},
            status=http_status.HTTP_400_BAD_REQUEST
        )


@docs('LibraryView.get')
@docs('LibraryView.post')
class LibraryView(ExportCSVMixin, FXViewRoleInfoMixin, APIView):
    """View to get the list of libraries"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    pagination_class = DefaultPagination
    fx_view_name = 'libraries_list'
    fx_default_read_only_roles = ['staff', 'instructor', 'library_user', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/libraries/v1/libraries/: Get the list of libraries'

    def get(self, request: Any) -> Response:
        """
        GET /api/fx/libraries/v1/libraries/?tenant_ids=<tenantIds>

        <tenantIds> (optional): a comma-separated list of the tenant IDs to get the information for. If not provided,
            the API will assume the list of all accessible tenants by the user
        """
        libraries = get_accessible_libraries(self.fx_permission_info, self.request.query_params.get('search_text'))
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(libraries, request)
        serializer = serializers.LibrarySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request: Any) -> Response:  # pylint: disable=no-self-use
        """
        POST /api/fx/libraries/v1/libraries/
        """
        serializer = serializers.LibrarySerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            created_library = serializer.save()
            return JsonResponse(
                {'library': str(created_library.location.library_key)},
                status=http_status.HTTP_201_CREATED,
            )
        return Response(
            {'errors': serializer.errors},
            status=http_status.HTTP_400_BAD_REQUEST
        )


@docs('CourseStatusesView.get')
class CourseStatusesView(FXViewRoleInfoMixin, APIView):
    """View to get the course statuses"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    fx_view_name = 'course_statuses'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/statistics/v1/course_statuses/: Get the course statuses'

    @staticmethod
    def to_json(result: QuerySet) -> dict[str, int]:
        """Convert the result to JSON format"""
        dict_result = {
            f'{COURSE_STATUS_SELF_PREFIX if self_paced else ""}{status}': 0
            for status in COURSE_STATUSES
            for self_paced in [False, True]
        }

        for item in result:
            status = f'{COURSE_STATUS_SELF_PREFIX if item["self_paced"] else ""}{item["status"]}'
            dict_result[status] = item['courses_count']
        return dict_result

    def get(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:
        """
        GET /api/fx/statistics/v1/course_statuses/?tenant_ids=<tenantIds>

        <tenantIds> (optional): a comma-separated list of the tenant IDs to get the information for. If not provided,
            the API will assume the list of all accessible tenants by the user
        """
        result = get_courses_count_by_status(fx_permission_info=self.fx_permission_info)

        return JsonResponse(self.to_json(result))


@docs('LearnerInfoView.get')
class LearnerInfoView(FXViewRoleInfoMixin, APIView):
    """View to get the information of a learner"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    fx_view_name = 'learner_detailed_info'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/learners/v1/learner/: Get the information of a learner'

    def get(self, request: Any, username: str, *args: Any, **kwargs: Any) -> JsonResponse | Response:
        """
        GET /api/fx/learners/v1/learner/<username>/
        """
        include_staff = request.query_params.get('include_staff', '0') == '1'

        try:
            user = get_learner_info_queryset(
                fx_permission_info=self.fx_permission_info,
                user_key=username,
                include_staff=include_staff,
            ).first()
        except FXCodedException as exc:
            return_status = http_status.HTTP_404_NOT_FOUND if exc.code in (
                FXExceptionCodes.USER_QUERY_NOT_PERMITTED.value, FXExceptionCodes.USER_NOT_FOUND.value,
            ) else http_status.HTTP_400_BAD_REQUEST

            return Response(
                error_details_to_dictionary(reason=str(exc)),
                status=return_status,
            )

        return JsonResponse(
            serializers.LearnerDetailsExtendedSerializer(user, context={'request': request}).data
        )


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


@docs('LearnerCoursesView.get')
class LearnerCoursesView(FXViewRoleInfoMixin, APIView):
    """View to get the list of courses for a learner"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    pagination_class = DefaultPagination
    fx_view_name = 'learner_courses'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/learners/v1/learner_courses/: Get the list of courses for a learner'

    def get(self, request: Any, username: str, *args: Any, **kwargs: Any) -> JsonResponse | Response:
        """
        GET /api/fx/learners/v1/learner_courses/<username>/
        """
        include_staff = request.query_params.get('include_staff', '0') == '1'

        try:
            courses = get_learner_courses_info_queryset(
                fx_permission_info=self.fx_permission_info,
                user_key=username,
                visible_filter=None,
                include_staff=include_staff,
            )
        except FXCodedException as exc:
            return_status = http_status.HTTP_404_NOT_FOUND if exc.code in (
                FXExceptionCodes.USER_QUERY_NOT_PERMITTED.value, FXExceptionCodes.USER_NOT_FOUND.value,
            ) else http_status.HTTP_400_BAD_REQUEST

            return Response(
                error_details_to_dictionary(reason=str(exc)),
                status=return_status,
            )

        return Response(serializers.LearnerCoursesDetailsSerializer(
            courses, context={'request': request}, many=True
        ).data)


@docs('VersionInfoView.get')
class VersionInfoView(APIView):
    """View to get the version information"""
    permission_classes = [IsSystemStaff]

    def get(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:  # pylint: disable=no-self-use
        """
        GET /api/fx/version/v1/info/
        """
        import futurex_openedx_extensions  # pylint: disable=import-outside-toplevel
        return JsonResponse({
            'version': futurex_openedx_extensions.__version__,
        })


@docs('AccessibleTenantsInfoView.get')
class AccessibleTenantsInfoView(APIView):
    """View to get the list of accessible tenants"""
    permission_classes = [IsAnonymousOrSystemStaff]

    def get(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:  # pylint: disable=no-self-use
        """
        GET /api/fx/accessible/v1/info/?username_or_email=<usernameOrEmail>
        """
        username_or_email = request.query_params.get('username_or_email')
        try:
            user = get_user_by_username_or_email(username_or_email)
        except ObjectDoesNotExist:
            user = None

        if not user:
            return JsonResponse({})

        tenant_ids = get_accessible_tenant_ids(user)
        return JsonResponse(get_tenants_info(tenant_ids))


@docs('AccessibleTenantsInfoViewV2.get')
class AccessibleTenantsInfoViewV2(FXViewRoleInfoMixin, APIView):
    """View to get the list of accessible tenants version 2"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    fx_view_name = 'accessible_info'
    fx_view_description = 'api/fx/accessible/v2/info/: Get accessible tenants'

    def get(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:  # pylint: disable=no-self-use
        """
        GET /api/fx/accessible/v1/info/?username_or_email=<usernameOrEmail>
        """
        username_or_email = request.query_params.get('username_or_email')
        try:
            user = get_user_by_username_or_email(username_or_email)
        except ObjectDoesNotExist:
            user = None

        if not user:
            return JsonResponse({})

        tenant_ids = get_accessible_tenant_ids(user)
        return JsonResponse(get_tenants_info(tenant_ids))


@docs('LearnersDetailsForCourseView.get')
class LearnersDetailsForCourseView(ExportCSVMixin, FXViewRoleInfoMixin, ListAPIView):
    """View to get the list of learners for a course"""
    authentication_classes = default_auth_classes
    serializer_class = serializers.LearnerDetailsForCourseSerializer
    permission_classes = [FXHasTenantCourseAccess]
    pagination_class = DefaultPagination
    fx_view_name = 'learners_with_details_for_course'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/learners/v1/learners/<course-id>: Get the list of learners for a course'

    def get_related_id(self) -> None:
        """
        Related ID is course_id for this view.
        """
        return self.kwargs.get('course_id')

    def get_queryset(self, *args: Any, **kwargs: Any) -> QuerySet:
        """Get the list of learners for a course"""
        search_text = self.request.query_params.get('search_text')
        course_id = self.kwargs.get('course_id')
        include_staff = self.request.query_params.get('include_staff', '0') == '1'

        return get_learners_by_course_queryset(
            course_id=course_id,
            search_text=search_text,
            include_staff=include_staff,
        )

    def get_serializer_context(self) -> Dict[str, Any]:
        """Get the serializer context"""
        context = super().get_serializer_context()
        context['course_id'] = self.kwargs.get('course_id')
        context['omit_subsection_name'] = self.request.query_params.get('omit_subsection_name', '0')
        return context


@docs('CoursesFeedbackView.get')
class CoursesFeedbackView(ExportCSVMixin, FXViewRoleInfoMixin, ListAPIView):
    """View to get the list of courses feedbacks"""
    authentication_classes = default_auth_classes
    serializer_class = serializers.CoursesFeedbackSerializer
    permission_classes = [FXHasTenantCourseAccess]
    pagination_class = DefaultPagination
    fx_view_name = 'courses_feedback'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/courses/v1/feedback: Get the list of feedbacks'

    def validate_rating_list(self, param_key: str) -> list[int] | None:
        """
        Validates that the input string from query parameters is a comma-separated list
        of integers between 1 and 5. Returns the parsed list if valid.

        :param param_key: The key in query params to validate (e.g. 'rating_content')
        :return: List of integers if valid, or None if not provided
        :raises: FXCodedException if validation fails
        """
        value = self.request.query_params.get(param_key)
        if not value:
            return None

        try:
            ratings = [int(r.strip()) for r in value.split(',')]
        except ValueError as exc:
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message=f"'{param_key}' must be a comma-separated list of valid integers."
            ) from exc

        if any(r < 0 or r > 5 for r in ratings):
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message=f"Each value in '{param_key}' must be between 0 and 5 (inclusive)."
            )

        return ratings

    def get_queryset(self, *args: Any, **kwargs: Any) -> QuerySet:
        """Get the list of course feedbacks"""
        course_ids = self.request.query_params.get('course_ids', '')
        course_ids_list = [
            course.strip() for course in course_ids.split(',')
        ] if course_ids else None

        return get_courses_feedback_queryset(
            fx_permission_info=self.request.fx_permission_info,
            course_ids=course_ids_list,
            public_only=self.request.query_params.get('public_only', '0') == '1',
            recommended_only=self.request.query_params.get('recommended_only', '0') == '1',
            feedback_search=self.request.query_params.get('feedback_search'),
            rating_content_filter=self.validate_rating_list('rating_content'),
            rating_instructors_filter=self.validate_rating_list('rating_instructors')
        )


@docs('LearnersEnrollmentView.get')
class LearnersEnrollmentView(ExportCSVMixin, FXViewRoleInfoMixin, ListAPIView):
    """View to get the list of learners for a course"""
    authentication_classes = default_auth_classes
    serializer_class = serializers.LearnerEnrollmentSerializer
    permission_classes = [FXHasTenantCourseAccess]
    pagination_class = DefaultPagination
    fx_view_name = 'learners_enrollment_details'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/learners/v1/enrollments: Get the list of enrollments'
    is_single_course_requested = False

    @staticmethod
    def validate_progress_range(progress_min_str: str, progress_max_str: str) -> tuple[float, float]:
        """
        Validates that the input strings from query parameters are valid float numbers between 0 and 100.

        :param progress_min_str: The minimum progress value as a string
        :param progress_max_str: The maximum progress value as a string
        :return: Tuple of (min_progress, max_progress) as floats
        :raises: FXCodedException if validation fails
        """
        def raise_error(var_name: str) -> None:
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message=f'{var_name} must be a valid number between 0.0 and 1.0 (inclusive). Or a negative value'
                        ' to ignore it.'
            )

        min_progress: float = -1
        max_progress: float = -1

        try:
            min_progress = float(progress_min_str or -1)
        except ValueError:
            raise_error('progress_min')

        if min_progress > 1:
            raise_error('progress_min')

        try:
            max_progress = float(progress_max_str or -1)
        except ValueError:
            raise_error('progress_max')

        if max_progress > 1:
            raise_error('progress_max')

        if min_progress >= 0 and 0 <= max_progress < min_progress:
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message='progress_min cannot be greater than progress_max.'
            )

        return min_progress, max_progress

    def get_queryset(self, *args: Any, **kwargs: Any) -> QuerySet:
        """Get the list of learners for a course"""
        course_ids = self.request.query_params.get('course_ids', '')
        user_ids = self.request.query_params.get('user_ids', '')
        usernames = self.request.query_params.get('usernames', '')

        progress_min_str = self.request.query_params.get('progress_min', '-1')
        progress_max__str = self.request.query_params.get('progress_max', '-1')
        progress_min, progress_max = self.validate_progress_range(progress_min_str, progress_max__str)

        course_ids_list = [
            course.strip() for course in course_ids.split(',')
        ] if course_ids else None
        user_ids_list = [
            int(user.strip()) for user in user_ids.split(',') if user.strip().isdigit()
        ] if user_ids else None
        usernames_list = [
            username.strip() for username in usernames.split(',')
        ] if usernames else None

        if course_ids_list and len(course_ids_list) == 1:
            self.is_single_course_requested = True

        return get_learners_enrollments_queryset(
            fx_permission_info=self.request.fx_permission_info,
            user_ids=user_ids_list,
            course_ids=course_ids_list,
            usernames=usernames_list,
            learner_search=self.request.query_params.get('learner_search'),
            course_search=self.request.query_params.get('course_search'),
            include_staff=self.request.query_params.get('include_staff', '0') == '1',
            progress_filter=(progress_min, progress_max),
        )

    def get_serializer_context(self) -> Dict[str, Any]:
        """Get the serializer context"""
        context = super().get_serializer_context()
        if self.is_single_course_requested and self.get_queryset().exists():
            context['course_id'] = str(self.get_queryset().first().course_id)
            context['omit_subsection_name'] = self.request.query_params.get('omit_subsection_name', '0')
        return context


@docs('GlobalRatingView.get')
class GlobalRatingView(FXViewRoleInfoMixin, APIView):
    """View to get the global rating"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    fx_view_name = 'global_rating'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/statistics/v1/rating/: Get the global rating for courses'

    def get(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:
        """
        GET /api/fx/statistics/v1/rating/?tenant_ids=<tenantIds>

        <tenantIds> (optional): a comma-separated list of the tenant IDs to get the information for. If not provided,
            the API will assume the list of all accessible tenants by the user
        """
        data_result = get_courses_ratings(fx_permission_info=self.fx_permission_info)
        result = {
            'total_rating': data_result['total_rating'],
            'total_count': sum(data_result[f'rating_{index}_count'] for index in range(1, 6)),
            'courses_count': data_result['courses_count'],
            'rating_counts': {
                str(index): data_result[f'rating_{index}_count'] for index in range(1, 6)
            },
        }

        return JsonResponse(result)


@docs('UserRolesManagementView.create')
@docs('UserRolesManagementView.destroy')
@docs('UserRolesManagementView.list')
@docs('UserRolesManagementView.retrieve')
@docs('UserRolesManagementView.update')
@exclude_schema_for('partial_update')
@method_decorator(transaction.non_atomic_requests, name='dispatch')
class UserRolesManagementView(FXViewRoleInfoMixin, viewsets.ModelViewSet):  # pylint: disable=too-many-ancestors
    """View to get the user roles"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'user_roles'
    fx_default_read_only_roles = ['org_course_creator_group']
    fx_default_read_write_roles = ['org_course_creator_group']
    fx_allowed_write_methods = ['POST', 'PUT', 'DELETE']
    fx_view_description = 'api/fx/roles/v1/user_roles/: user roles management APIs'

    lookup_field = 'username'
    lookup_value_regex = '[^/]+'
    serializer_class = serializers.UserRolesSerializer
    pagination_class = DefaultPagination

    def get_queryset(self) -> QuerySet:
        """Get the list of users"""
        dummy_serializers = serializers.UserRolesSerializer(context={'request': self.request})

        try:
            q_set = get_user_model().objects.filter(
                id__in=get_course_access_roles_queryset(
                    orgs_filter=dummy_serializers.orgs_filter,
                    remove_redundant=True,
                    users=None,
                    search_text=dummy_serializers.query_params['search_text'],
                    roles_filter=dummy_serializers.query_params['roles_filter'],
                    active_filter=dummy_serializers.query_params['active_filter'],
                    course_ids_filter=dummy_serializers.query_params['course_ids_filter'],
                    excluded_role_types=dummy_serializers.query_params['excluded_role_types'],
                    excluded_hidden_roles=not dummy_serializers.query_params['include_hidden_roles'],
                ).values('user_id').distinct().order_by()
            ).select_related('profile').order_by('id')
        except (ValueError, FXCodedException) as exc:
            raise ParseError(f'Invalid parameter: {exc}') from exc

        return q_set

    def create(self, request: Any, *args: Any, **kwargs: Any) -> Response | JsonResponse:
        """Create a new user role"""
        data = request.data
        try:
            if (
                not isinstance(data['tenant_ids'], list) or
                not all(isinstance(t_id, int) for t_id in data['tenant_ids'])
            ):
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT,
                    message='tenant_ids must be a list of integers',
                )

            if not isinstance(data['users'], list):
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT,
                    message='users must be a list',
                )

            if not isinstance(data['role'], str):
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT,
                    message='role must be a string',
                )

            if not isinstance(data['tenant_wide'], int):
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT,
                    message='tenant_wide must be an integer flag',
                )

            if not isinstance(data.get('course_ids', []), list):
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT,
                    message='course_ids must be a list',
                )

            result = add_course_access_roles(
                caller=self.fx_permission_info['user'],
                tenant_ids=data['tenant_ids'],
                user_keys=data['users'],
                role=data['role'],
                tenant_wide=data['tenant_wide'] != 0,
                course_ids=data.get('course_ids', []),
            )
        except KeyError as exc:
            return Response(
                error_details_to_dictionary(reason=f'Missing required parameter: {exc}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )
        except FXCodedException as exc:
            return Response(
                error_details_to_dictionary(reason=f'({exc.code}) {str(exc)}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        return JsonResponse(
            result,
            status=http_status.HTTP_201_CREATED,
        )

    @staticmethod
    def verify_username(username: str) -> Response | Dict[str, Any]:
        """Verify the username"""
        user_info = get_user_by_key(username)
        if not user_info['user']:
            return Response(
                error_details_to_dictionary(reason=f'({user_info["error_code"]}) {user_info["error_message"]}'),
                status=http_status.HTTP_404_NOT_FOUND
            )
        return user_info

    def update(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """Update a user role"""
        user_info = self.verify_username(kwargs['username'])
        if isinstance(user_info, Response):
            return user_info

        result = update_course_access_roles(
            caller=self.fx_permission_info['user'],
            user=user_info['user'],
            new_roles_details=request.data or {},
            dry_run=False,
        )

        if result['error_code']:
            return Response(
                error_details_to_dictionary(reason=f'({result["error_code"]}) {result["error_message"]}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        return Response(
            self.serializer_class(user_info['user'], context={'request': request}).data,
            status=http_status.HTTP_200_OK,
        )

    def destroy(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """Delete a user role"""
        if not request.query_params.get('tenant_ids'):
            return Response(
                error_details_to_dictionary(reason="Missing required parameter: 'tenant_ids'"),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        user_info = self.verify_username(kwargs['username'])
        if isinstance(user_info, Response):
            return user_info

        try:
            delete_course_access_roles(
                caller=self.fx_permission_info['user'],
                tenant_ids=self.fx_permission_info['view_allowed_tenant_ids_any_access'],
                user=user_info['user'],
            )
        except FXCodedException as exc:
            return Response(
                error_details_to_dictionary(reason=str(exc)),
                status=http_status.HTTP_404_NOT_FOUND
            )

        return Response(status=http_status.HTTP_204_NO_CONTENT)


@docs('MyRolesView.get')
class MyRolesView(FXViewRoleInfoMixin, APIView):
    """View to get the user roles of the caller"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    fx_view_name = 'my_roles'
    fx_default_read_only_roles = COURSE_ACCESS_ROLES_SUPPORTED_READ.copy()
    fx_view_description = 'api/fx/roles/v1/my_roles/: user roles management APIs'

    serializer_class = serializers.UserRolesSerializer

    def get(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:
        """Get the list of users"""
        data = serializers.UserRolesSerializer(self.fx_permission_info['user'], context={'request': request}).data
        data['is_system_staff'] = self.fx_permission_info['is_system_staff_user']
        return JsonResponse(data)


@docs('ExcludedTenantsView.get')
class ExcludedTenantsView(APIView):
    """View to get the list of excluded tenants"""
    authentication_classes = default_auth_classes
    permission_classes = [IsSystemStaff]

    def get(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:  # pylint: disable=no-self-use
        """Get the list of excluded tenants"""
        return JsonResponse(get_excluded_tenant_ids())


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


@docs('ConfigEditableInfoView.get')
class ConfigEditableInfoView(FXViewRoleInfoMixin, APIView):
    """View to get the list of editable keys of the theme designer config"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'fx_config_editable_fields'
    fx_view_description = 'api/fx/config/v1/editable: Get editable settings of config'
    fx_default_read_write_roles = ['staff', 'fx_api_access_global']
    fx_default_read_only_roles = ['staff', 'fx_api_access_global']

    def get(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:
        """
        GET /api/fx/config/v1/editable/
        """
        tenant_id = self.verify_one_tenant_id_provided(request)

        return JsonResponse({
            'editable_fields': get_accessible_config_keys(
                user_id=request.user.id,
                tenant_id=tenant_id,
                writable_fields_filter=True,
            ),
            'read_only_fields': get_accessible_config_keys(
                user_id=request.user.id,
                tenant_id=tenant_id,
                writable_fields_filter=False,
            ),
        })


@docs('ThemeConfigDraftView.get')
@docs('ThemeConfigDraftView.put')
@docs('ThemeConfigDraftView.delete')
class ThemeConfigDraftView(FXViewRoleInfoMixin, APIView):
    """View to manage draft theme config"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'theme_config_draft'
    fx_allowed_write_methods = ['PUT', 'DELETE']
    fx_view_description = 'api/fx/config/v1/draft/<tenant_id>: draft theme config APIs'
    fx_default_read_write_roles = ['staff', 'fx_api_access_global']
    fx_default_read_only_roles = ['staff', 'fx_api_access_global']
    fx_tenant_id_url_arg_name: str = 'tenant_id'

    def get(self, request: Any, tenant_id: int) -> Response | JsonResponse:  # pylint: disable=no-self-use
        """Get draft config"""
        updated_fields = get_draft_tenant_config(tenant_id=int(tenant_id))
        return JsonResponse({
            'updated_fields': updated_fields,
            'draft_hash': dict_to_hash(updated_fields)
        })

    @staticmethod
    def validate_input(current_revision_id: int) -> None:
        """Validate the input"""
        if current_revision_id is None:
            raise KeyError('current_revision_id')

        try:
            _ = int(current_revision_id)
        except ValueError as exc:
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message='current_revision_id type must be numeric value.'
            ) from exc

    def put(self, request: Any, tenant_id: int) -> Response:
        """Update draft config"""
        data = request.data
        try:
            key = data['key']
            if not isinstance(key, str):
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT, message='Key name must be a string.'
                )

            key_access_info = ConfigAccessControl.objects.get(key_name=key)
            if not key_access_info.writable:
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT, message=f'Config Key: ({data["key"]}) is not writable.'
                )

            if 'reset' not in data and 'new_value' not in data:
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT, message='Provide either new_value or reset.'
                )

            new_value = data.get('new_value')
            current_revision_id = data.get('current_revision_id')
            reset = data.get('reset', False) is True
            self.validate_input(current_revision_id)

            update_draft_tenant_config(
                tenant_id=int(tenant_id),
                config_path=key_access_info.path,
                current_revision_id=int(current_revision_id),
                new_value=new_value,
                reset=reset,
                user=request.user,
            )

            data = get_tenant_config(tenant_id=int(tenant_id), keys=[key], published_only=False)
            return Response(
                status=http_status.HTTP_200_OK,
                data=serializers.TenantConfigSerializer(data, context={'request': request}).data,
            )

        except KeyError as exc:
            return Response(
                error_details_to_dictionary(reason=f'Missing required parameter: {exc}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )
        except FXCodedException as exc:
            if exc.code in [
                FXExceptionCodes.DRAFT_CONFIG_CREATE_MISMATCH.value,
                FXExceptionCodes.DRAFT_CONFIG_UPDATE_MISMATCH.value,
                FXExceptionCodes.DRAFT_CONFIG_DELETE_MISMATCH.value,
            ]:
                return Response(
                    error_details_to_dictionary(reason=f'({exc.code}) {str(exc)}'),
                    status=http_status.HTTP_409_CONFLICT
                )
            return Response(
                error_details_to_dictionary(reason=f'({exc.code}) {str(exc)}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )
        except ConfigAccessControl.DoesNotExist:
            return Response(
                error_details_to_dictionary(
                    reason=f'Invalid key, unable to find key: ({data["key"]}) in config access control'
                ),
                status=http_status.HTTP_400_BAD_REQUEST
            )

    def delete(self, request: Any, tenant_id: int) -> Response:  # pylint: disable=no-self-use
        """Delete draft config"""
        delete_draft_tenant_config(tenant_id=int(tenant_id))
        return Response(status=http_status.HTTP_204_NO_CONTENT)


@docs('ThemeConfigPublishView.post')
@method_decorator(transaction.non_atomic_requests, name='dispatch')
class ThemeConfigPublishView(FXViewRoleInfoMixin, APIView):
    """View to publish theme config"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'theme_config_publish'
    fx_view_description = 'api/fx/config/v1/publish/: Get editable settings of config'
    fx_default_read_write_roles = ['staff', 'fx_api_access_global']
    fx_default_read_only_roles = ['staff', 'fx_api_access_global']

    @staticmethod
    def validate_payload(data: dict, fx_permission_info: dict) -> dict:
        """
        Validates the payload.

        :param data: The payload data from the request
        :param fx_permission_info: The permission info
        :raises FXCodedException: If the payload data is invalid
        """
        tenant_id = data.get('tenant_id')
        if not tenant_id or not isinstance(tenant_id, int):
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message='Tenant id is required and must be an int.'
            )

        if tenant_id not in fx_permission_info['view_allowed_tenant_ids_full_access']:
            raise PermissionDenied(detail=json.dumps(
                {'reason': f'User does not have required access for tenant ({tenant_id})'}
            ))

        draft_hash = data.get('draft_hash')
        if not draft_hash or not isinstance(draft_hash, str):
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message='Draft hash is required and must be a string.'
            )
        current_draft = get_draft_tenant_config(tenant_id=tenant_id)
        current_draft_hash = dict_to_hash(current_draft)
        if current_draft_hash != draft_hash:
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message='Draft hash mismatched with current draft values hash.'
            )
        return current_draft

    @staticmethod
    def rename_keys(updated_fields: dict) -> dict:
        """
        Rename 'published_value' to 'old_value' and 'draft_value' to 'new_value
        """
        renamed_data = {}
        for key, value in updated_fields.items():
            renamed_data[key] = {
                'old_value': value.get('published_value', None),
                'new_value': value.get('draft_value', None)
            }
        return renamed_data

    def post(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:
        """
        POST /api/fx/config/v1/publish/
        """
        data = request.data
        updated_fields = self.validate_payload(data, self.request.fx_permission_info)
        publish_tenant_config(data['tenant_id'])
        return JsonResponse({'updated_fields': self.rename_keys(updated_fields)})


@docs('ThemeConfigRetrieveView.get')
class ThemeConfigRetrieveView(FXViewRoleInfoMixin, APIView):
    """View to get theme config values"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'theme_config_values'
    fx_view_description = 'api/fx/config/v1/values/: Get theme config values'
    fx_default_read_only_roles = ['staff', 'fx_api_access_global']

    def validate_keys(self, tenant_id: int) -> list:
        """Validate keys"""
        keys = self.request.query_params.get('keys', '')
        if keys:
            return keys.split(',')

        return get_accessible_config_keys(user_id=self.request.user.id, tenant_id=tenant_id)

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """
        GET /api/fx/config/v1/values/
        """
        tenant_id = self.verify_one_tenant_id_provided(request)

        data = get_tenant_config(
            tenant_id,
            self.validate_keys(tenant_id=tenant_id),
            request.query_params.get('published_only', '0') == '1'
        )
        return Response(serializers.TenantConfigSerializer(data, context={'request': request}).data)


@docs('ThemeConfigTenantView.post')
class ThemeConfigTenantView(FXViewRoleInfoMixin, APIView):
    """View to create new Tenant and theme config"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'theme_config_tenant'
    fx_view_description = 'api/fx/config/v1/tenant/: Create new Tenant'

    @staticmethod
    def validate_payload(data: dict) -> None:
        """
        Validates the payload.

        :param data: The payload data from the request
        :raises FXCodedException: If the payload data is invalid
        """
        sub_domain = data.get('sub_domain')
        if not sub_domain:
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message='Subdomain is required.'
            )
        if not isinstance(sub_domain, str):
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message='Subdomain must be a string.'
            )
        if len(sub_domain) > 16:
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message='Subdomain cannot exceed 16 characters.'
            )
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9]*$', sub_domain):
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message=(
                    'Subdomain can only contain letters and numbers and cannot start with a number.'
                )
            )

        platform_name = data.get('platform_name')
        if not platform_name:
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message='Platform name is required.'
            )
        if not isinstance(platform_name, str):
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message='Platform name must be a string.'
            )

        owner_user_id = data.get('owner_user_id')
        if owner_user_id and not get_user_model().objects.filter(id=owner_user_id).exists():
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message=f'User with ID {owner_user_id} does not exist.'
            )

    def post(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:
        """
        POST /api/fx/config/v1/tenant/
        """
        data = request.data
        self.validate_payload(data)
        tenant_config = create_new_tenant_config(data['sub_domain'], data['platform_name'])
        owner_user_id = data.get('owner_user_id')
        if owner_user_id:
            add_course_access_roles(
                caller=self.fx_permission_info['user'],
                tenant_ids=[tenant_config.id],
                user_keys=[data['owner_user_id']],
                role=COURSE_ACCESS_ROLES_STAFF_EDITOR,
                tenant_wide=True,
                course_ids=[],
            )

        result = {'tenant_id': tenant_config.id}
        result.update(get_all_tenants_info()['info'].get(tenant_config.id))
        return JsonResponse(result)


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


@docs('TenantAssetsManagementView.create')
@docs('TenantAssetsManagementView.list')
@exclude_schema_for('retrieve', 'update', 'partial_update', 'destroy')
class TenantAssetsManagementView(FXViewRoleInfoMixin, viewsets.ModelViewSet):  # pylint: disable=too-many-ancestors
    """View to list and retrieve course assets."""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    serializer_class = serializers.TenantAssetSerializer
    pagination_class = DefaultPagination
    fx_view_name = 'tenant_assets'
    fx_default_read_write_roles = ['staff', 'fx_api_access_global']
    fx_default_read_only_roles = ['staff', 'fx_api_access_global']
    fx_allowed_write_methods = ['POST']
    fx_view_description = 'api/fx/tenant/v1/assets/: Tenant Assets Management APIs.'
    filter_backends = [DefaultOrderingFilter, DjangoFilterBackend, DefaultSearchFilter]
    filterset_fields = ['tenant_id', 'updated_by']
    ordering = ['-id']
    search_fields = ['slug']

    parser_classes = [MultiPartParser]

    def get_queryset(self) -> QuerySet:
        """Get the list of user uploaded files."""
        is_staff_user = self.request.fx_permission_info['is_system_staff_user']
        accessible_tenant_ids = self.request.fx_permission_info['view_allowed_tenant_ids_full_access']
        if is_staff_user:
            template_tenant_id = get_all_tenants_info()['template_tenant']['tenant_id']
            if template_tenant_id:
                accessible_tenant_ids.append(template_tenant_id)

        result = TenantAsset.objects.filter(tenant__id__in=accessible_tenant_ids)
        if not is_staff_user:
            result = result.exclude(slug__startswith='_')

        return result


class SetThemePreviewCookieView(APIView):
    """View to set theme preview cookie"""
    def get(self, request: Any) -> Any:  # pylint: disable=no-self-use
        """Set theme preview cookie"""
        next_url = request.GET.get('next', request.build_absolute_uri())
        if request.COOKIES.get('theme-preview') == 'yes':
            return redirect(next_url)

        return render(request, template_name='set_theme_preview.html', context={'next_url': next_url})


@docs('CategoriesView.get')
@docs('CategoriesView.post')
class CategoriesView(FXViewRoleInfoMixin, APIView):
    """View to manage course categories"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'categories_management'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_default_read_write_roles = ['staff', 'instructor', 'org_course_creator_group']
    fx_allowed_write_methods = ['POST']
    fx_view_description = 'api/fx/courses/v1/categories/: Manage course categories'

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """GET /api/fx/courses/v1/categories/"""
        tenant_id = self.verify_one_tenant_id_provided(request)
        include_courses = 'courses' in request.query_params.get('optional_field_tags', '').split(',')

        category_manager = CourseCategories(tenant_id, open_as_read_only=True)

        result = []
        for category_name in category_manager.sorting:
            category_data = category_manager.get_category(category_name)
            item = {
                'id': category_name,
                'label': category_data['label'],
            }
            if include_courses:
                item['courses'] = category_data['courses']
            result.append(item)

        return Response(result)

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """POST /api/fx/courses/v1/categories/"""
        serializer = serializers.CategorySerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=http_status.HTTP_400_BAD_REQUEST)

        try:
            category = serializer.save()
            return Response(category, status=http_status.HTTP_201_CREATED)
        except FXCodedException as exc:
            return Response(
                error_details_to_dictionary(reason=f'({exc.code}) {str(exc)}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )


@docs('CategoryDetailView.patch')
@docs('CategoryDetailView.delete')
class CategoryDetailView(FXViewRoleInfoMixin, APIView):
    """View to manage individual category"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'category_detail'
    fx_default_read_write_roles = ['staff', 'instructor', 'org_course_creator_group']
    fx_allowed_write_methods = ['PATCH', 'DELETE']
    fx_view_description = 'api/fx/courses/v1/categories/<category_id>/: Manage individual category'

    def patch(self, request: Any, category_id: str, *args: Any, **kwargs: Any) -> Response:
        """PATCH /api/fx/courses/v1/categories/<category_id>/"""
        tenant_id = self.verify_one_tenant_id_provided(request)

        serializer = serializers.CategoryUpdateSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=http_status.HTTP_400_BAD_REQUEST)

        try:
            category_manager = CourseCategories(tenant_id, open_as_read_only=False)
            category_manager.verify_category_name_exists(category_id)

            if 'label' in serializer.validated_data:
                category_manager.categories[category_id]['label'] = serializer.validated_data['label']

            if 'courses' in serializer.validated_data:
                category_manager.set_courses_for_category(category_id, serializer.validated_data['courses'])

            category_manager.save()
            return Response(status=http_status.HTTP_204_NO_CONTENT)

        except FXCodedException as exc:
            return Response(
                error_details_to_dictionary(reason=f'({exc.code}) {str(exc)}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )

    def delete(self, request: Any, category_id: str, *args: Any, **kwargs: Any) -> Response:
        """DELETE /api/fx/courses/v1/categories/<category_id>/"""
        tenant_id = self.verify_one_tenant_id_provided(request)

        try:
            category_manager = CourseCategories(tenant_id, open_as_read_only=False)
            category_manager.remove_category(category_id)
            category_manager.save()
            return Response(status=http_status.HTTP_204_NO_CONTENT)

        except FXCodedException as exc:
            return Response(
                error_details_to_dictionary(reason=f'({exc.code}) {str(exc)}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )


@docs('CategoriesOrderView.post')
class CategoriesOrderView(FXViewRoleInfoMixin, APIView):
    """View to update categories order"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'categories_order'
    fx_default_read_write_roles = ['staff', 'instructor', 'org_course_creator_group']
    fx_allowed_write_methods = ['POST']
    fx_view_description = 'api/fx/courses/v1/categories_order/: Update categories order'

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """POST /api/fx/courses/v1/categories_order/"""
        serializer = serializers.CategoriesOrderSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=http_status.HTTP_400_BAD_REQUEST)

        try:
            tenant_id = serializer.validated_data['tenant_id']
            categories = serializer.validated_data['categories']

            category_manager = CourseCategories(tenant_id, open_as_read_only=False)
            category_manager.set_categories_sorting(categories)
            category_manager.save()

            return Response(status=http_status.HTTP_204_NO_CONTENT)

        except FXCodedException as exc:
            return Response(
                error_details_to_dictionary(reason=f'({exc.code}) {str(exc)}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )


@docs('CourseCategoriesView.put')
class CourseCategoriesView(FXViewRoleInfoMixin, APIView):
    """View to assign categories to a course"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'course_categories'
    fx_default_read_write_roles = ['staff', 'instructor', 'org_course_creator_group']
    fx_allowed_write_methods = ['PUT']
    fx_view_description = 'api/fx/courses/v1/course_categories/<course_id>/: Assign categories to a course'

    def put(self, request: Any, course_id: str, *args: Any, **kwargs: Any) -> Response:
        """PUT /api/fx/courses/v1/course_categories/<course_id>/"""
        serializer = serializers.CourseCategoriesSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=http_status.HTTP_400_BAD_REQUEST)

        try:
            course_org = course_id.split(':')[1].split('+')[0] if ':' in course_id else course_id.split('+')[0]
            tenant_ids = get_tenants_by_org(course_org)

            if not tenant_ids:
                return Response(
                    error_details_to_dictionary(reason=f'No tenant found for course: {course_id}'),
                    status=http_status.HTTP_404_NOT_FOUND
                )

            tenant_id = tenant_ids[0]
            if tenant_id not in self.fx_permission_info['view_allowed_tenant_ids_full_access']:
                return Response(
                    error_details_to_dictionary(reason=f'User does not have required access for tenant ({tenant_id})'),
                    status=http_status.HTTP_403_FORBIDDEN
                )

            category_manager = CourseCategories(tenant_id, open_as_read_only=False)
            category_manager.set_categories_for_course(course_id, serializer.validated_data['categories'])
            category_manager.save()

            return Response(status=http_status.HTTP_204_NO_CONTENT)

        except FXCodedException as exc:
            return Response(
                error_details_to_dictionary(reason=f'({exc.code}) {str(exc)}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )

