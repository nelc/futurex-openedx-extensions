"""Statistics views for the dashboard app"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from rest_framework.exceptions import ParseError
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
    get_enrollments_count,
    get_enrollments_count_aggregated,
)
from futurex_openedx_extensions.dashboard.statistics.learners import get_learners_count
from futurex_openedx_extensions.helpers.constants import FX_VIEW_DEFAULT_AUTH_CLASSES
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.permissions import (
    FXHasTenantCourseAccess,
    get_tenant_limited_fx_permission_info,
)
from futurex_openedx_extensions.helpers.roles import FXViewRoleInfoMixin

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
