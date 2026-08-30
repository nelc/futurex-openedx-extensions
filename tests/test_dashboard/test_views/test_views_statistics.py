"""Test views for the dashboard app - statistics"""
# pylint: disable=duplicate-code
import json
from datetime import date
from unittest.mock import patch

import ddt
import pytest
from common.djangoapps.student.models import CourseEnrollment
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.urls import resolve
from rest_framework import status as http_status
from rest_framework.exceptions import ParseError
from rest_framework.response import Response
from waffle.testutils import override_flag

from futurex_openedx_extensions.dashboard.views.statistics import AggregatedCountsView
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.permissions import FXHasTenantCourseAccess
from tests.fixture_helpers import d_t
from tests.test_dashboard.test_mixins import BaseTestViewMixin


@pytest.mark.usefixtures('base_data')
class TestTotalCountsView(BaseTestViewMixin):
    """Tests for TotalCountsView"""
    VIEW_NAME = 'fx_dashboard:total-counts'

    def test_unauthorized(self):
        """Test unauthorized access"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_invalid_stats(self):
        """Test invalid stats"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url + '?stats=invalid')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(str(response.data['detail']), "Invalid stats type: ['invalid']")

    @override_flag('fx_dashboard.enable_heavy_queries', active=True)
    def test_counts_are_raw_by_default(self):
        """The shipped default drops the staff and visibility exclusions, so counts are never lower."""
        self.login_user(self.staff_user)
        url = self.url + '?stats=enrollments,learners,courses'

        raw = json.loads(self.client.get(url).content)
        with override_flag('fx_dashboard.legacy_filtered_counts', active=True):
            filtered = json.loads(self.client.get(url).content)

        assert raw != filtered, 'the default must differ from the legacy filtered behaviour'
        for key, value in filtered.items():
            if not isinstance(value, dict):
                continue
            for count_key, count in value.items():
                assert raw[key][count_key] >= count, \
                    f'raw counting must never report fewer than filtered for tenant {key}.{count_key}'

    @override_flag('fx_dashboard.legacy_filtered_counts', active=True)
    def test_all_stats(self):
        """Test get method"""
        self.login_user(self.staff_user)
        response = self.client.get(
            self.url + '?stats=certificates,courses,hidden_courses,learners,enrollments,learning_hours,unique_learners'
        )
        self.assertTrue(isinstance(response, JsonResponse))
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertDictEqual(json.loads(response.content), {
            '1': {
                'certificates_count': 11, 'courses_count': 12, 'hidden_courses_count': 0,
                'learners_count': 16, 'enrollments_count': 26, 'learning_hours_count': 220
            },
            '2': {
                'certificates_count': 8, 'courses_count': 5, 'hidden_courses_count': 0,
                'learners_count': 21, 'enrollments_count': 21, 'learning_hours_count': 160
            },
            '3': {
                'certificates_count': 0, 'courses_count': 1, 'hidden_courses_count': 0,
                'learners_count': 6, 'enrollments_count': 4, 'learning_hours_count': 0
            },
            '7': {
                'certificates_count': 6, 'courses_count': 3, 'hidden_courses_count': 0,
                'learners_count': 17, 'enrollments_count': 14, 'learning_hours_count': 120
            },
            '8': {
                'certificates_count': 2, 'courses_count': 2, 'hidden_courses_count': 0,
                'learners_count': 9, 'enrollments_count': 7, 'learning_hours_count': 40
            },
            'total_certificates_count': 27, 'total_courses_count': 23, 'total_hidden_courses_count': 0,
            'total_learners_count': 69, 'total_enrollments_count': 72, 'total_learning_hours_count': 540,
            'total_unique_learners': 37, 'limited_access': False
        })

    @override_flag('fx_dashboard.enable_heavy_queries', active=True)
    @override_flag('fx_dashboard.legacy_filtered_counts', active=True)
    def test_all_stats_with_include_staff(self):
        """Test get method"""
        self.login_user(self.staff_user)
        response = self.client.get(
            self.url + '?stats=certificates,courses,learners,enrollments&include_staff=1'
        )
        self.assertTrue(isinstance(response, JsonResponse))
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertDictEqual(json.loads(response.content), {
            '1': {'certificates_count': 14, 'courses_count': 12, 'learners_count': 18, 'enrollments_count': 32},
            '2': {'certificates_count': 9, 'courses_count': 5, 'learners_count': 26, 'enrollments_count': 25},
            '3': {'certificates_count': 0, 'courses_count': 1, 'learners_count': 6, 'enrollments_count': 4},
            '7': {'certificates_count': 7, 'courses_count': 3, 'learners_count': 20, 'enrollments_count': 17},
            '8': {'certificates_count': 2, 'courses_count': 2, 'learners_count': 10, 'enrollments_count': 8},
            'total_certificates_count': 32,
            'total_courses_count': 23,
            'total_learners_count': 80,
            'total_enrollments_count': 86,
            'limited_access': False
        })

    def test_limited_access(self):
        """Test get method with limited access"""
        self.login_user(9)
        response = self.client.get(self.url + '?tenant_ids=1&stats=certificates')  # we need at least one stat
        self.assertTrue(isinstance(response, JsonResponse))
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(json.loads(response.content)['limited_access'], True)

    @override_flag('fx_dashboard.enable_heavy_queries', active=True)
    @override_flag('fx_dashboard.legacy_filtered_counts', active=True)
    def test_selected_tenants(self):
        """Test get method with selected tenants"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url + '?stats=certificates,courses,learners&tenant_ids=1,2')
        self.assertTrue(isinstance(response, JsonResponse))
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        expected_response = {
            '1': {'certificates_count': 11, 'courses_count': 12, 'learners_count': 16},
            '2': {'certificates_count': 8, 'courses_count': 5, 'learners_count': 21},
            'total_certificates_count': 19,
            'total_courses_count': 17,
            'total_learners_count': 37,
            'limited_access': False,
        }
        self.assertDictEqual(json.loads(response.content), expected_response)


@ddt.ddt
@pytest.mark.usefixtures('base_data')
class TestAggregatedCountsView(BaseTestViewMixin):
    """Tests for AggregatedCountsView"""
    VIEW_NAME = 'fx_dashboard:aggregated-counts'

    def setUp(self):
        """Setup"""
        super().setUp()
        self.view = AggregatedCountsView()
        self.view.request = self._get_request()

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_invalid_stats(self):
        """Test invalid stats"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url + '?stats=invalid')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(str(response.data['detail']), "Invalid stats type: ['invalid']")

    @patch('futurex_openedx_extensions.dashboard.views.statistics.AggregatedCountsView._construct_result')
    @ddt.data(
        (None, '2024-01-01', '2024-01-01', 'Invalid aggregate_period: None'),
        ('day', '2024-01-01', '2024-01-01', None),
        ('day', '2024-01-01', '2024-01-02', None),
        ('day', '2024-01-02', '2024-01-01', None),
        ('day', None, '2024-01-01', None),
        ('day', '2024-01-02', None, None),
        ('day', None, None, None),
        ('invalid', '2024-01-01', '2024-01-02', 'Invalid aggregate_period: invalid'),
        (
            'day',
            'invalid', '2024-01-02',
            'Invalid dates. date_from and date_to must be formated as YYYY-MM-DD when provided.',
        ),
        (
            'day',
            '2024-01-01',
            'invalid',
            'Invalid dates. date_from and date_to must be formated as YYYY-MM-DD when provided.',
        ),
        ('day', '2024-01-03', '2024-01-02', None),
    )
    @ddt.unpack
    def test_load_query_params(
        self, aggregate_period, date_from, date_to, error_message, mock_construct_result,
    ):  # pylint: disable=too-many-arguments
        """Verify that _load_query_params works as expected"""
        mock_construct_result.return_value = {
            'query_settings': {
                'aggregate_period': aggregate_period,
                'date_from': date_from,
                'date_to': date_to,
            },
            'by_tenant': [],
            'all_tenants': {
                'enrollments_count': [],
                'totals': {
                    'enrollments_count': 0,
                },
            },
            'limited_access': False,
        }
        self.login_user(self.staff_user)
        url = self.url + f'?stats=enrollments&aggregate_period={aggregate_period}'
        if date_from:
            url += f'&date_from={date_from}'
        if date_to:
            url += f'&date_to={date_to}'
        response = self.client.get(url)
        if error_message:
            self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
            print(response.data)
            self.assertEqual(str(response.data['detail']), error_message)
        else:
            self.assertEqual(response.status_code, http_status.HTTP_200_OK)

    @ddt.data(
        ('', 0, 'should be zero when max_period_chunks is not provided.'),
        ('44', 0, 'should be zero when max_period_chunks is greater than settings value.'),
        ('-1', 0, 'should be zero when max_period_chunks is negative.'),
        ('24', 24, 'should be the sam provided max_period_chunks value when it is less or equal settings value.'),
        ('0', 0, 'should be the sam provided max_period_chunks value when it is less or equal settings value.'),
        ('3', 3, 'should be the sam provided max_period_chunks value when it is less or equal settings value.'),
    )
    @ddt.unpack
    def test_load_query_params_max_period_chunks(
        self, max_period_chunks_query_params, expected_max_period_chunks, error_details,
    ):
        """Verify that _load_query_params works saves the correct value for max_period_chunks"""
        self.view.request.query_params = {
            'stats': 'enrollments',
            'aggregate_period': 'month',
        }
        if max_period_chunks_query_params:
            self.view.request.query_params['max_period_chunks'] = max_period_chunks_query_params

        assert self.view.max_period_chunks == 0, 'bad test data'
        self.view._load_query_params(request=self.view.request)  # pylint: disable=protected-access
        assert self.view.max_period_chunks == expected_max_period_chunks, error_details

    def test_load_query_params_max_period_chunks_not_int(self):
        """Verify that _load_query_params raises ParseError when max_period_chunks is not an integer"""
        self.view.request.query_params = {
            'stats': 'enrollments',
            'aggregate_period': 'month',
            'max_period_chunks': 'not_integer',
        }

        assert self.view.max_period_chunks == 0, 'bad test data'
        with pytest.raises(ParseError) as exc:
            self.view._load_query_params(request=self.view.request)  # pylint: disable=protected-access
        assert str(exc.value) == 'Invalid max_period_chunks. It must be an integer.'

    def _prepare_test_dates_for_aggregated_counts(self):
        """Prepare test dates for aggregated counts"""
        self.assertEqual(CourseEnrollment.objects.count(), 73)
        enrollments = CourseEnrollment.objects.filter(
            is_active=True,
            user_id__lt=30,
            user__is_superuser=False,
            user__is_staff=False,
            user__is_active=True,
            course__org='org2',
        )
        assert enrollments.count() == 16, 'bad test data'
        count = 7
        enrollment = enrollments.first()
        while enrollment and count > 0:
            enrollment.created = '2024-08-07' if count < 4 else '2024-12-26'
            enrollment.save()
            count -= 1
            enrollment = enrollments.filter(id__gt=enrollment.id).first()

        assert CourseEnrollment.objects.filter(created='2024-08-07').count() == 3, 'test data preparation failed!'
        assert CourseEnrollment.objects.filter(created='2024-12-26').count() == 4, 'test data preparation failed!'

        expected_result = {
            'query_settings': {
                'aggregate_period': 'day',
                'date_from': '2022-12-28T00:00:00Z',
                'date_to': '2024-12-26T23:59:59Z',
            },
            'all_tenants': {
                'enrollments_count': [
                    {'label': '2024-08-07', 'value': 3},
                    {'label': '2024-12-26', 'value': 4},
                ],
                'totals': {'enrollments_count': 7},
            },
            'by_tenant': [
                {
                    'enrollments_count': [
                        {'label': '2024-08-07', 'value': 3},
                        {'label': '2024-12-26', 'value': 4},
                    ],
                    'totals': {'enrollments_count': 7},
                    'tenant_id': 1,
                },
                {
                    'enrollments_count': [],
                    'totals': {'enrollments_count': 0},
                    'tenant_id': 2,
                },
            ],
            'limited_access': False,
        }
        return expected_result

    @patch('futurex_openedx_extensions.dashboard.views.statistics.AggregatedCountsView.get_data_with_missing_periods')
    @ddt.data(True, False)
    def test_all_stats(self, fill_missing_periods, mock_missing_periods):
        """Test get method"""
        mock_missing_periods.side_effect = lambda data, already_sorted: data
        expected_result = self._prepare_test_dates_for_aggregated_counts()

        self.login_user(self.staff_user)
        url = self.url + '?&tenant_ids=1,2&include_staff=1&stats=enrollments&date_to=2024-12-26&aggregate_period=day'
        if not fill_missing_periods:
            url += '&fill_missing_periods=0'
        response = self.client.get(url)
        self.assertTrue(isinstance(response, Response))
        self.assertEqual(
            response.status_code,
            http_status.HTTP_200_OK,
            f'{http_status}: {response.data.get("detail")}',
        )

        self.assertDictEqual(json.loads(response.content), expected_result)
        self.assertEqual(
            mock_missing_periods.call_count,
            len(expected_result['all_tenants']['enrollments_count']) if fill_missing_periods else 0,
        )

    @ddt.data('courses', 'learners', 'learning_hours', 'certificates')
    def test_unsupported_stats(self, stat):
        """Test unsupported stats"""
        with pytest.raises(NotImplementedError):
            self.view._get_stat_count(stat=stat, tenant_id=1)  # pylint: disable=protected-access

    @ddt.data(
        ('day', '2024-08-07'),
        ('month', '2024-08'),
        ('quarter', '2024-Q3'),
        ('year', '2024'),
    )
    @ddt.unpack
    def test_get_period_label(self, aggregate_period, expected_label):
        """Verify that get_period_label returns the correct result"""
        assert self.view.get_period_label(aggregate_period, date(2024, 8, 7)) == expected_label

    @ddt.data(
        ('day', d_t('2024-08-07'), d_t('2024-08-08')),
        ('day', d_t('2024-12-31'), d_t('2025-01-01')),
        ('month', d_t('2024-08-07'), d_t('2024-09-01')),
        ('month', d_t('2024-12-26'), d_t('2025-01-01')),
        ('quarter', d_t('2024-08-07'), d_t('2024-10-01')),
        ('quarter', d_t('2024-12-26'), d_t('2025-01-01')),
        ('year', d_t('2024-08-07'), d_t('2025-01-01')),
    )
    @ddt.unpack
    def test_get_next_period_date(self, aggregate_period, the_date, expected_next_date):
        """Verify that get_next_period_date returns the correct result"""
        assert self.view.get_next_period_date(aggregate_period, the_date) == expected_next_date

    @ddt.data(
        'get_period_label', 'get_next_period_date',
    )
    def test_extractors_bad_period(self, method_name):
        """Verify that extractor methods raise FXCodedException when the period is invalid"""
        with pytest.raises(FXCodedException) as exc_info:
            getattr(self.view, method_name)('invalid-period', date(2024, 8, 7))
        assert exc_info.value.code == FXExceptionCodes.INVALID_INPUT.value
        assert str(exc_info.value) == 'Invalid aggregate_period: invalid-period'

    @ddt.data(
        'get_period_label', 'get_next_period_date',
    )
    def test_get_period_label_bad_date(self, method_name):
        """Verify that extractor methods raise FXCodedException when the date is invalid"""
        with pytest.raises(ValidationError) as exc_info:
            getattr(self.view, method_name)('day', 'not-date-or-datetime')
        assert exc_info.value.message == 'the_date must be a date or datetime object. Got (str)'

    def test_get_data_with_missing_periods_no_data(self):
        """Verify that get_data_with_missing_periods returns an empty list when there is no data"""
        result = self.view.get_data_with_missing_periods([])
        assert not result
        assert isinstance(result, list)

    @ddt.data(
        (d_t('2024-08-07'), None),
        (None, d_t('2024-08-08')),
        (None, None),
    )
    @ddt.unpack
    def test_get_data_with_missing_periods_no_dates(self, date_from, date_to):
        """Verify that get_data_with_missing_periods returns the same data when there are no dates"""
        self.view.date_from = date_from
        self.view.date_to = date_to
        data = [{'label': '2024-12-26', 'value': 3}, {'label': '2024-08-08', 'value': 4}]
        sorted_data = [{'label': '2024-08-08', 'value': 4}, {'label': '2024-12-26', 'value': 3}]

        assert self.view.get_data_with_missing_periods(data) == sorted_data
        assert self.view.get_data_with_missing_periods(data, already_sorted=False) == sorted_data
        assert self.view.get_data_with_missing_periods(data, already_sorted=True) == data

    def test_get_data_with_missing_periods(self):
        """Verify that get_data_with_missing_periods returns the correct result"""
        self.view.date_from = d_t('2024-07-16')
        self.view.date_to = d_t('2025-02-14')
        self.view.aggregate_period = 'month'
        data = [{'label': '2024-12', 'value': 3}, {'label': '2024-08', 'value': 4}]

        assert self.view.get_data_with_missing_periods(data) == [
            {'label': '2024-07', 'value': 0},
            {'label': '2024-08', 'value': 4},
            {'label': '2024-09', 'value': 0},
            {'label': '2024-10', 'value': 0},
            {'label': '2024-11', 'value': 0},
            {'label': '2024-12', 'value': 3},
            {'label': '2025-01', 'value': 0},
            {'label': '2025-02', 'value': 0},
        ]

    def test_get_data_with_missing_periods_protection(self):
        """
        Verify that get_data_with_missing_periods is protected from infinite loops when the data is not sorted, and
        the caller passed already_sorted as True.
        """
        self.view.date_from = d_t('2024-07-16')
        self.view.date_to = d_t('2025-02-14')
        self.view.aggregate_period = 'month'
        data = [{'label': '2024-12', 'value': 3}, {'label': '2024-08', 'value': 4}]

        result = self.view.get_data_with_missing_periods(data, already_sorted=True)
        expected_added_zeros = ['2024-07', '2024-09', '2024-10', '2024-11', '2025-01', '2025-02']
        assert len(result) == 8
        for item in result:
            if item['label'] in expected_added_zeros:
                assert item['value'] == 0, f'{item["label"]} should be added as zero'
            if item['label'] == '2024-08':
                assert item['value'] == 0, '2024-08 should be set to zero because the data is not sorted'
            if item['label'] == '2024-12':
                assert item['value'] == 3, (
                    '2024-12 should be set to the correct value because it\' reached first, and any label less than'
                    ' 2024-12 will be set to zero. This is the correct behavior for a wrong data!'
                )


@pytest.mark.usefixtures('base_data')
class TestGlobalRatingView(BaseTestViewMixin):
    """Tests for GlobalRatingView"""
    VIEW_NAME = 'fx_dashboard:statistics-rating'

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        view_func, _, _ = resolve(self.url)
        view_class = view_func.view_class
        self.assertEqual(view_class.permission_classes, [FXHasTenantCourseAccess])

    def test_success(self):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        test_data = {
            'total_rating': 50,
            'courses_count': 2,
            'rating_1_count': 3,
            'rating_2_count': 5,
            'rating_3_count': 2,
            'rating_4_count': 1,
            'rating_5_count': 4,
        }
        expected_result = {
            'total_rating': 50,
            'total_count': 15,
            'courses_count': 2,
            'rating_counts': {
                '1': 3,
                '2': 5,
                '3': 2,
                '4': 1,
                '5': 4,
            },
        }
        for value in range(1, 6):
            assert expected_result['rating_counts'][str(value)] == test_data[f'rating_{value}_count']
        assert expected_result['total_count'] == sum(expected_result['rating_counts'].values())

        with patch('futurex_openedx_extensions.dashboard.views.statistics.get_courses_ratings') as mocked_calc:
            mocked_calc.return_value = test_data
            response = self.client.get(f'{self.url}?tenant_ids=1')
        data = json.loads(response.content)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(data, expected_result)
        mocked_calc.assert_called_once_with(tenant_id=1)

    def test_success_no_rating(self):
        """Verify that the view returns the correct response when there are no ratings"""
        self.login_user(self.staff_user)
        with patch('futurex_openedx_extensions.dashboard.views.statistics.get_courses_ratings') as mocked_calc:
            mocked_calc.return_value = {
                'total_rating': 0,
                'courses_count': 0,
                'rating_1_count': 0,
                'rating_2_count': 0,
                'rating_3_count': 0,
                'rating_4_count': 0,
                'rating_5_count': 0,
            }
            response = self.client.get(f'{self.url}?tenant_ids=1')
        data = json.loads(response.content)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(data, {
            'total_rating': 0,
            'total_count': 0,
            'courses_count': 0,
            'rating_counts': {
                '1': 0,
                '2': 0,
                '3': 0,
                '4': 0,
                '5': 0,
            },
        })
        mocked_calc.assert_called_once_with(tenant_id=1)
