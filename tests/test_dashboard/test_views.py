"""Test views for the dashboard app"""
# pylint: disable=too-many-lines
import hashlib
import json
import os
from datetime import date
from unittest.mock import ANY, Mock, patch

import ddt
import pytest
from common.djangoapps.student.models import CourseAccessRole, CourseEnrollment
from deepdiff import DeepDiff
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.paginator import EmptyPage
from django.db.models import Q
from django.http import JsonResponse
from django.urls import resolve, reverse
from django.utils.functional import SimpleLazyObject
from django.utils.timezone import now, timedelta
from eox_nelp.course_experience.models import FeedbackCourse
from eox_tenant.models import Route, TenantConfig
from opaque_keys.edx.locator import CourseLocator, LibraryLocator
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from rest_framework import status as http_status
from rest_framework.exceptions import ParseError
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST
from rest_framework.test import APIRequestFactory, APITestCase

from futurex_openedx_extensions.dashboard import serializers, urls, views
from futurex_openedx_extensions.dashboard.views import (
    LearnersEnrollmentView,
    ThemeConfigDraftView,
    ThemeConfigPublishView,
    UserRolesManagementView,
)
from futurex_openedx_extensions.helpers import clickhouse_operations as ch
from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers.constants import ALLOWED_FILE_EXTENSIONS
from futurex_openedx_extensions.helpers.converters import dict_to_hash
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.filters import DefaultOrderingFilter
from futurex_openedx_extensions.helpers.models import (
    ConfigAccessControl,
    DataExportTask,
    DraftConfig,
    TenantAsset,
    ViewAllowedRoles,
)
from futurex_openedx_extensions.helpers.pagination import DefaultPagination
from futurex_openedx_extensions.helpers.permissions import (
    FXHasTenantAllCoursesAccess,
    FXHasTenantCourseAccess,
    IsAnonymousOrSystemStaff,
    IsSystemStaff,
)
from tests.fixture_helpers import d_t, get_all_orgs, get_test_data_dict, get_user1_fx_permission_info
from tests.test_dashboard.test_mixins import MockPatcherMixin


class BaseTestViewMixin(APITestCase):
    """Base test view mixin"""
    VIEW_NAME = 'view name is not set!'

    def setUp(self):
        """Setup"""
        self.view_name = self.VIEW_NAME
        self.url_args = []
        self.staff_user = 2

    @property
    def url(self):
        """Get the URL"""
        return reverse(self.view_name, args=self.url_args)

    def login_user(self, user_id):
        """Helper to login user"""
        self.client.force_login(get_user_model().objects.get(id=user_id))

    def _get_request(self):
        """Helper to get the request"""
        factory = APIRequestFactory()
        request = factory.get(self.url)
        request.query_params = {}
        request.user = get_user_model().objects.get(id=self.staff_user)
        request.fx_permission_info = get_user1_fx_permission_info()
        request.fx_permission_info['user'] = request.user
        return request


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
        self.view = views.AggregatedCountsView()
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

    @patch('futurex_openedx_extensions.dashboard.views.AggregatedCountsView._construct_result')
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
            'Invalid dates. You must provide a valid date_from and date_to formated as YYYY-MM-DD'
        ),
        (
            'day',
            '2024-01-01',
            'invalid',
            'Invalid dates. You must provide a valid date_from and date_to formated as YYYY-MM-DD'
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

    @patch('futurex_openedx_extensions.dashboard.views.AggregatedCountsView.get_data_with_missing_periods')
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
class TestLearnersView(BaseTestViewMixin):
    """Tests for LearnersView"""
    VIEW_NAME = 'fx_dashboard:learners'

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_no_tenants(self):
        """Verify that the view returns the result for all accessible tenants when no tenant IDs are provided"""
        self.login_user(self.staff_user)
        with patch('futurex_openedx_extensions.dashboard.views.get_learners_queryset') as mock_queryset:
            self.client.get(self.url)
            mock_queryset.assert_called_once()
            assert mock_queryset.call_args_list[0][1]['fx_permission_info']['view_allowed_full_access_orgs'] \
                   == get_all_orgs()
            assert mock_queryset.call_args_list[0][1]['search_text'] is None

    def test_search(self):
        """Verify that the view filters the learners by search text"""
        self.login_user(self.staff_user)
        with patch('futurex_openedx_extensions.dashboard.views.get_learners_queryset') as mock_queryset:
            self.client.get(self.url + '?tenant_ids=1&search_text=user')
            assert mock_queryset.call_args_list[0][1]['fx_permission_info']['view_allowed_tenant_ids_any_access'] == [1]
            assert mock_queryset.call_args_list[0][1]['search_text'] == 'user'

    def test_success(self):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 37)
        self.assertGreater(len(response.data['results']), 0)

    @patch('futurex_openedx_extensions.dashboard.views.get_learners_queryset')
    def test_enrollments_filter(self, mock_get_learners_queryset):
        """Verify that the view filters the learners by enrollments"""
        self.login_user(self.staff_user)

        self.client.get(self.url)
        mock_get_learners_queryset.assert_called_once_with(
            fx_permission_info=ANY,
            search_text=None,
            include_staff=False,
            enrollments_filter=(-1, -1)
        )

        mock_get_learners_queryset.reset_mock()
        self.client.get(self.url + '?min_enrollments_count=1&max_enrollments_count=10')
        mock_get_learners_queryset.assert_called_once_with(
            fx_permission_info=ANY,
            search_text=None,
            include_staff=False,
            enrollments_filter=(1, 10)
        )

    def test_enrollments_filter_invalid(self):
        """Verify that the view returns 400 when the enrollments filter is invalid"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url + '?min_enrollments_count=HELLO')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data['reason'], 'Enrollments filter must be a tuple or a list of two integer values.'
        )


@ddt.ddt
@pytest.mark.usefixtures('base_data')
class TestCoursesView(BaseTestViewMixin):
    """Tests for CoursesView"""
    VIEW_NAME = 'fx_dashboard:courses'

    def test_list_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_list_no_tenants(self):
        """Verify that the view returns the result for all accessible tenants when no tenant IDs are provided"""
        self.login_user(self.staff_user)
        with patch('futurex_openedx_extensions.dashboard.views.get_courses_queryset') as mock_queryset:
            self.client.get(self.url)
            assert mock_queryset.call_args_list[0][1]['fx_permission_info']['view_allowed_full_access_orgs'] \
                   == get_all_orgs()
            assert mock_queryset.call_args_list[0][1]['search_text'] is None
            assert mock_queryset.call_args_list[0][1]['visible_filter'] is None

    def test_list_search(self):
        """Verify that the view filters the courses by search text"""
        self.login_user(self.staff_user)
        with patch('futurex_openedx_extensions.dashboard.views.get_courses_queryset') as mock_queryset:
            self.client.get(self.url + '?tenant_ids=1&search_text=course')
            assert mock_queryset.call_args_list[0][1]['fx_permission_info']['view_allowed_tenant_ids_any_access'] == [1]
            assert mock_queryset.call_args_list[0][1]['search_text'] == 'course'
            assert mock_queryset.call_args_list[0][1]['visible_filter'] is None

    def test_list_success(self):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 18)
        self.assertEqual(len(response.data['results']), 18)

    def test_list_sorting(self):
        """Verify that the view sorting filter is set correctly"""
        view_func, _, _ = resolve(self.url)
        view_class = view_func.view_class
        self.assertEqual(view_class.filter_backends, [DefaultOrderingFilter])

    def test_invalid_input(self):
        """Verify that the view filters the courses by enrollments"""
        self.login_user(self.staff_user)

        with patch('futurex_openedx_extensions.dashboard.serializers.CourseCreateSerializer') as mock_ser:
            mocked_serializer = Mock()
            mocked_serializer.is_valid.return_value = False
            mocked_serializer.errors = {'tenant_id': ['This field is required.']}
            mock_ser.return_value = mocked_serializer
            response = self.client.post(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'errors': {'tenant_id': ['This field is required.']}})

    @patch('futurex_openedx_extensions.dashboard.serializers.ensure_organization')
    @patch('futurex_openedx_extensions.dashboard.serializers.CourseInstructorRole')
    @patch('futurex_openedx_extensions.dashboard.serializers.CourseStaffRole')
    @patch('futurex_openedx_extensions.dashboard.serializers.add_users')
    @patch('futurex_openedx_extensions.dashboard.serializers.seed_permissions_roles')
    @patch('futurex_openedx_extensions.dashboard.serializers.CourseEnrollment.enroll')
    @patch('futurex_openedx_extensions.dashboard.serializers.assign_default_role')
    @patch('futurex_openedx_extensions.dashboard.serializers.add_organization_course')
    @patch('futurex_openedx_extensions.dashboard.serializers.DiscussionsConfiguration.get')
    def test_create_success(
        self, mock_discussions_config_get, mock_add_org_course, mock_assign_default_role,
        mock_course_enrollment_enroll, mock_seed_permissions_roles, mock_add_users,
        mock_staff_role, mock_instructor_role, mock_ensure_org
    ):  # pylint: disable=too-many-arguments
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        staff_user_obj = get_user_model().objects.get(id=self.staff_user)
        staff_user_lazy_obj = SimpleLazyObject(lambda: staff_user_obj)
        mock_ensure_org.return_value = {'id': 'org1', 'name': 'org1', 'short_name': 'org1'}

        with patch('futurex_openedx_extensions.dashboard.serializers.relative_url_to_absolute_url') as mock_get_url:
            mock_get_url.return_value = 'https://example.com/courses/course-v1:org1+11+111'
            response = self.client.post(
                self.url, data={'tenant_id': 1, 'display_name': 'test 1', 'number': '11', 'run': '111'}
            )

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.json(), {
            'id': 'course-v1:org1+11+111',
            'url': mock_get_url.return_value,
        })

        expected_course_locator = CourseLocator.from_string('course-v1:org1+11+111')
        mock_ensure_org.assert_called_once_with('org1')
        mock_staff_role.assert_called_once_with(expected_course_locator)
        mock_instructor_role.assert_called_once_with(expected_course_locator)
        mock_add_users.assert_called_once_with(
            staff_user_lazy_obj, mock_staff_role.return_value, staff_user_lazy_obj
        )
        mock_seed_permissions_roles.assert_called_once_with(expected_course_locator)
        mock_course_enrollment_enroll.assert_called_once_with(staff_user_obj, expected_course_locator)
        mock_assign_default_role.assert_called_once_with(expected_course_locator, staff_user_obj)
        mock_add_org_course.assert_called_once_with(mock_ensure_org.return_value, expected_course_locator)
        mock_discussions_config_get.assert_called_once_with(context_key=expected_course_locator)


@ddt.ddt
@pytest.mark.usefixtures('base_data')
class TestCoursesFeedbackView(BaseTestViewMixin):
    """Tests for CoursesFeedbackView"""
    VIEW_NAME = 'fx_dashboard:courses-feedback'

    @staticmethod
    def prepare_feedbacks() -> None:
        """Create all components required for tests"""
        FeedbackCourse.objects.create(
            author=get_user_model().objects.get(id=3),
            course_id=CourseOverview.objects.get(id='course-v1:Org1+1+1'),
            rating_content=5,
            feedback='some comment 1',
            public=True,
            rating_instructors=4,
            recommended=True,
        )
        FeedbackCourse.objects.create(
            author=get_user_model().objects.get(id=1),
            course_id=CourseOverview.objects.get(id='course-v1:ORG1+2+2'),
            rating_content=4,
            feedback='some comment 2',
            public=True,
            rating_instructors=3,
            recommended=True,
        )
        FeedbackCourse.objects.create(
            author=get_user_model().objects.get(id=3),
            course_id=CourseOverview.objects.get(id='course-v1:ORG1+4+4'),
            rating_content=2,
            feedback='some comment 3',
            public=False,
            rating_instructors=2,
            recommended=True,
        )
        FeedbackCourse.objects.create(
            author=get_user_model().objects.get(id=47),
            course_id=CourseOverview.objects.get(id='course-v1:ORG8+1+1'),
            rating_content=5,
            feedback='some comment by learner',
            public=True,
            rating_instructors=1,
            recommended=False,
        )

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_success_no_filters(self):
        """Verify that user can only view feedbacks of accessible courses"""
        self.prepare_feedbacks()
        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(
            len(response.data['results']),
            4,
            'Unexpected result, as global staff user should have access to all feedbacks'
        )
        self.login_user(23)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(
            len(response.data['results']),
            1,
            'Unexpected result, user 23 has only access to org5 and org8 courses.'
        )

    def test_filter_by_course_ids(self):
        """Verify filtering by course_ids returns only feedbacks for specified courses"""
        self.prepare_feedbacks()
        self.login_user(self.staff_user)
        response = self.client.get(self.url + '?course_ids=course-v1%3AORG1%2B2%2B2')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        assert len(response.data['results']) == 1
        assert response.data['results'][0]['feedback'] == 'some comment 2'

    def test_filter_by_feedback_search(self):
        """Verify filtering by feedback_search returns matching feedback"""
        self.prepare_feedbacks()
        self.login_user(self.staff_user)
        response = self.client.get(self.url + '?feedback_search=learner')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        assert len(response.data['results']) == 1
        assert 'learner' in response.data['results'][0]['feedback']

    def test_filter_by_public_only(self):
        """Verify filtering by public_only=1 returns only public feedbacks"""
        self.prepare_feedbacks()
        self.login_user(self.staff_user)
        response = self.client.get(self.url + '?public_only=1')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        assert len(response.data['results']) == 3  # 1 feedback is public=False

    def test_filter_by_recommended_only(self):
        """Verify filtering by recommended_only=1 returns only recommended feedbacks"""
        self.prepare_feedbacks()
        self.login_user(self.staff_user)
        response = self.client.get(self.url + '?recommended_only=1')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        assert len(response.data['results']) == 3  # 1 feedback is recommended=False

    def test_filter_by_rating_content(self):
        """Verify filtering by rating_content returns only matching ratings"""
        self.prepare_feedbacks()
        self.login_user(self.staff_user)
        response = self.client.get(self.url + '?rating_content=5')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        assert len(response.data['results']) == 2

    def test_filter_by_rating_instructors(self):
        """Verify filtering by rating_instructors returns only matching instructor ratings"""
        self.prepare_feedbacks()
        self.login_user(self.staff_user)
        response = self.client.get(self.url + '?rating_instructors=2')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        assert len(response.data['results']) == 1
        assert response.data['results'][0]['rating_instructors'] == 2

    @ddt.data(
        (
            '5,2',
            http_status.HTTP_200_OK,
            None
        ),
        (
            '3,6',
            http_status.HTTP_400_BAD_REQUEST,
            "Each value in 'rating_content' must be between 0 and 5 (inclusive)."
        ),
        (
            '3,-1',
            http_status.HTTP_400_BAD_REQUEST,
            "Each value in 'rating_content' must be between 0 and 5 (inclusive)."
        ),
        (
            '3,2,invalid',
            http_status.HTTP_400_BAD_REQUEST,
            "'rating_content' must be a comma-separated list of valid integers."
        ),
    )
    @ddt.unpack
    def test_rating_content_validation(self, query, expected_status, error_message):
        """Test rating_content filter for validation logic"""
        self.prepare_feedbacks()
        self.login_user(self.staff_user)
        response = self.client.get(f'{self.url}?rating_content={query}')
        assert response.status_code == expected_status
        if expected_status == http_status.HTTP_400_BAD_REQUEST:
            assert response.json()['reason'] == error_message
        else:
            assert 'results' in response.data
            assert len(response.data['results']) == 3


@ddt.ddt
@pytest.mark.usefixtures('base_data')
class TestLibrariesView(BaseTestViewMixin):
    """Tests for CoursesView"""
    VIEW_NAME = 'fx_dashboard:libraries'

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_library_list_success(self):
        """Verify that the view returns the correct response"""
        normal_user_id = 16
        normal_user = get_user_model().objects.get(id=normal_user_id)
        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 3)
        self.assertEqual(
            len(response.data['results']),
            3,
            'Unexpected result, as global staff user should have access to all libraries'
        )

        self.login_user(normal_user_id)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)
        CourseAccessRole.objects.create(org='org1', user=normal_user, role='staff')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(
            response.data['count'],
            2,
            'Unexpected result, as user with allowed org wide role should have access to all libraries of that org'
        )
        CourseAccessRole.objects.create(
            org='org5', user=normal_user, role='library_user', course_id='library-v1:org5+11'
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(
            response.data['count'],
            3,
            'Unexpected result, as user with allowed role for specific library should have access to that library'
        )

    def test_library_list_search(self):
        """Verify that search is returning right response"""
        self.login_user(self.staff_user)
        response = self.client.get(f'{self.url}?search_text=org5')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    def test_library_list_tenant_ids_filter(self):
        """Verify tenant_ids filter is working correctly"""
        self.login_user(self.staff_user)
        response = self.client.get(f'{self.url}?tenant_ids=1')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_library_list_pagination(self):
        """Verify pagination is working correctly"""
        self.login_user(self.staff_user)
        response = self.client.get(f'{self.url}?page_size=1')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 3)
        self.assertEqual(len(response.data['results']), 1)
        self.assertIsNone(response.data['previous'])
        self.assertIn('page=2', response.data['next'], msg="Expected 'page=2' in next URL.")

    @patch('futurex_openedx_extensions.dashboard.serializers.CourseInstructorRole')
    @patch('futurex_openedx_extensions.dashboard.serializers.CourseStaffRole')
    @patch('futurex_openedx_extensions.dashboard.serializers.add_users')
    def test_library_create_success(self, mock_add_users, mock_staff_role, mock_instructor_role):
        """Verify that the view returns the correct response for library creation"""
        staff_user = get_user_model().objects.get(id=self.staff_user)
        staff_user_lazy_obj = SimpleLazyObject(lambda: staff_user)
        self.login_user(self.staff_user)
        response = self.client.post(self.url, data={
            'tenant_id': 1, 'number': '33', 'display_name': 'Test Library Three org1'
        })
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)
        self.assertEqual(response.json()['library'], 'library-v1:org1+33')

        expected_lib_locator = LibraryLocator.from_string('library-v1:org1+33')
        mock_add_users.assert_called_once_with(staff_user_lazy_obj, mock_staff_role.return_value, staff_user_lazy_obj)
        mock_instructor_role.assert_called_once_with(expected_lib_locator)
        mock_staff_role.assert_called_once_with(expected_lib_locator)

    def test_library_create_for_failure(self):
        """Verify that the view returns the correct response for library creation api failure general errors"""
        self.login_user(self.staff_user)
        response = self.client.post(self.url, data={
            'tenant_id': 1
        })
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()['errors']['number'][0], 'This field is required.')
        self.assertEqual(response.json()['errors']['display_name'][0], 'This field is required.')

    @ddt.data(
        (
            4,
            'Invalid tenant_id: "4". This tenant does not exist or is not configured properly.',
            'invalid tenant as LMS_BASE not set'
        ),
        (
            3,
            'No default organization configured for tenant_id: "3".',
            'default org is not set'
        ),
        (
            7,
            'Invalid default organization "invalid" configured for tenant ID "7". '
            'This organization is not associated with the tenant.',
            'default org is not valid',
        ),
    )
    @ddt.unpack
    def test_library_create_for_failure_for_tenant_id_errors(self, tenant_id, expected_error, case):
        """Verify the view returns the correct error for various invalid tenant_id configurations."""
        self.login_user(self.staff_user)
        response = self.client.post(self.url, data={
            'tenant_id': tenant_id,
            'number': '33',
            'display_name': f'Test Library - {case}',
        })
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()['errors']['tenant_id'][0], expected_error, f'Failed for usecase: {case}')

    def test_library_create_with_duplicate_key_error(self):
        """Verify that the view returns the correct response for library creation"""
        self.login_user(self.staff_user)
        response = self.client.post(self.url, data={
            'tenant_id': 1, 'number': '11', 'display_name': 'whatever'
        })
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()[0], 'Library with org: org1 and number: 11 already exists.')


@pytest.mark.usefixtures('base_data')
class TestCourseCourseStatusesView(BaseTestViewMixin):
    """Tests for CourseStatusesView"""
    VIEW_NAME = 'fx_dashboard:course-statuses'

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_no_tenants(self):
        """Verify that the view returns the result for all accessible tenants when no tenant IDs are provided"""
        self.login_user(self.staff_user)
        with patch('futurex_openedx_extensions.dashboard.views.get_courses_count_by_status') as mock_queryset:
            self.client.get(self.url)
            assert mock_queryset.call_args_list[0][1]['fx_permission_info']['view_allowed_full_access_orgs'] \
                   == get_all_orgs()

    def test_success(self):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        data = json.loads(response.content)
        self.assertDictEqual(data, {
            'active': 12,
            'archived': 3,
            'upcoming': 2,
            'self_active': 1,
            'self_archived': 0,
            'self_upcoming': 0,
        })


def _mock_get_by_key(username_or_email):
    """Mock get_user_by_key"""
    return get_user_model().objects.get(Q(username=username_or_email) | Q(email=username_or_email))


class PermissionsTestOfLearnerInfoViewMixin:
    """Tests for CourseStatusesView"""
    patching_config = {
        'get_by_key': ('futurex_openedx_extensions.helpers.users.get_user_by_username_or_email', {
            'side_effect': _mock_get_by_key,
        }),
    }

    def setUp(self):
        """Setup"""
        super().setUp()
        self.url_args = ['user10']

    def _get_view_class(self):
        """Helper to get the view class"""
        view_func, _, _ = resolve(self.url)
        return view_func.view_class

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        self.assertEqual(self._get_view_class().permission_classes, [FXHasTenantCourseAccess])

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_user_not_found(self):
        """Verify that the view returns 404 when the user is not found"""
        user_name = 'user10x'
        self.url_args = [user_name]
        assert not get_user_model().objects.filter(username=user_name).exists(), 'bad test data'

        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data, {
            'reason': 'User with username/email (user10x) does not exist!', 'details': {}
        })

    def _get_test_users(self, org3_admin_id, org3_learner_id):
        """Helper to get test users for the test_not_staff_user test"""
        admin_user = get_user_model().objects.get(id=org3_admin_id)
        learner_user = get_user_model().objects.get(id=org3_learner_id)

        self.assertFalse(admin_user.is_staff, msg='bad test data')
        self.assertFalse(admin_user.is_superuser, msg='bad test data')
        self.assertFalse(learner_user.is_staff, msg='bad test data')
        self.assertFalse(learner_user.is_superuser, msg='bad test data')
        self.assertFalse(CourseAccessRole.objects.filter(user_id=org3_learner_id).exists(), msg='bad test data')

        self.login_user(org3_admin_id)
        self.url_args = [f'user{org3_learner_id}']

    def test_org_admin_user_with_allowed_learner(self):
        """Verify that the view returns 200 when the user is an admin on the learner's organization"""
        self._get_test_users(4, 45)
        view_class = self._get_view_class()
        ViewAllowedRoles.objects.create(
            view_name=view_class.fx_view_name,
            view_description=view_class.fx_view_description,
            allowed_role='instructor',
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

    def test_org_admin_user_with_allowed_learner_same_tenant_diff_org(self):
        """
        Verify that the view returns 200 when the user is an admin on the learner's organization, where the user is
        in the same tenant but in an organization that is not included in course_access_roles
        for the admin's organization
        """
        self._get_test_users(4, 52)
        view_class = self._get_view_class()
        ViewAllowedRoles.objects.create(
            view_name=view_class.fx_view_name,
            view_description=view_class.fx_view_description,
            allowed_role='instructor',
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

    def test_org_admin_user_with_not_allowed_learner(self):
        """Verify that the view returns 404 when the user is an org admin but the learner belongs to another org"""
        self._get_test_users(4, 16)
        view_class = self._get_view_class()
        ViewAllowedRoles.objects.create(
            view_name=view_class.fx_view_name,
            view_description=view_class.fx_view_description,
            allowed_role='instructor',
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)


@pytest.mark.usefixtures('base_data')
class TestLearnerInfoView(
    PermissionsTestOfLearnerInfoViewMixin, MockPatcherMixin, BaseTestViewMixin,
):  # pylint: disable=too-many-ancestors
    """Tests for CourseStatusesView"""
    VIEW_NAME = 'fx_dashboard:learner-info'

    def test_success(self):
        """Verify that the view returns the correct response"""
        user = get_user_model().objects.get(username='user10')
        user.courses_count = 3
        user.certificates_count = 1
        self.url_args = [user.username]
        self.assertFalse(())

        self.login_user(self.staff_user)
        with patch('futurex_openedx_extensions.dashboard.views.get_learner_info_queryset') as mock_get_info:
            mock_get_info.return_value = Mock(first=Mock(return_value=user))
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        data = json.loads(response.content)
        self.assertDictEqual(data, serializers.LearnerDetailsExtendedSerializer(user).data)

    @patch('futurex_openedx_extensions.dashboard.views.serializers.LearnerDetailsExtendedSerializer')
    def test_request_in_context(self, mock_serializer):
        """Verify that the view calls the serializer with the correct context"""
        request = self._get_request()
        view_class = self._get_view_class()
        mock_serializer.return_value = Mock(data={})

        with patch('futurex_openedx_extensions.dashboard.views.get_learner_info_queryset') as mock_get_info:
            mock_get_info.return_value = Mock()
            view = view_class()
            view.request = request
            view.get(request, 'user10')

        mock_serializer.assert_called_once_with(
            mock_get_info.return_value.first(),
            context={'request': request},
        )


@patch.object(
    serializers.LearnerCoursesDetailsSerializer,
    'get_grade',
    lambda self, obj: {'letter_grade': 'Pass', 'percent': 0.7, 'is_passing': True}
)
@pytest.mark.usefixtures('base_data')
class TestLearnerCoursesDetailsView(
    PermissionsTestOfLearnerInfoViewMixin, MockPatcherMixin, BaseTestViewMixin,
):  # pylint: disable=too-many-ancestors
    """Tests for LearnerCoursesView"""
    VIEW_NAME = 'fx_dashboard:learner-courses'

    def test_success(self):
        """Verify that the view returns the correct response"""
        user = get_user_model().objects.get(username='user10')
        self.url_args = [user.username]

        courses = CourseOverview.objects.filter(courseenrollment__user=user)
        for course in courses:
            course.enrollment_date = now() - timedelta(days=10)
            course.last_activity = now() - timedelta(days=2)
            course.related_user_id = user.id
            course.save()

        self.login_user(self.staff_user)
        with patch('futurex_openedx_extensions.dashboard.views.get_learner_courses_info_queryset') as mock_get_info:
            mock_get_info.return_value = courses
            response = self.client.get(self.url)

        assert mock_get_info.call_args_list[0][1]['fx_permission_info']['view_allowed_full_access_orgs'] \
               == get_all_orgs()
        assert mock_get_info.call_args_list[0][1]['user_key'] == 'user10'
        assert mock_get_info.call_args_list[0][1]['visible_filter'] is None
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        data = json.loads(response.content)
        self.assertEqual(len(data), 2)
        self.assertEqual(list(data), list(serializers.LearnerCoursesDetailsSerializer(courses, many=True).data))

    @patch('futurex_openedx_extensions.dashboard.views.serializers.LearnerCoursesDetailsSerializer')
    def test_request_in_context(self, mock_serializer):
        """Verify that the view uses the correct serializer"""
        request = self._get_request()
        view_class = self._get_view_class()

        with patch('futurex_openedx_extensions.dashboard.views.get_learner_courses_info_queryset') as mock_get_info:
            mock_get_info.return_value = Mock()
            view = view_class()
            view.request = request
            view.get(request, 'user10')

        mock_serializer.assert_called_once_with(
            mock_get_info.return_value,
            context={'request': request},
            many=True,
        )


class TestVersionInfoView(BaseTestViewMixin):
    """Tests for VersionInfoView"""
    VIEW_NAME = 'fx_dashboard:version-info'

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        view_func, _, _ = resolve(self.url)
        view_class = view_func.view_class
        self.assertEqual(view_class.permission_classes, [IsSystemStaff])

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_success(self):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        with patch('futurex_openedx_extensions.__version__', new='0.1.dummy'):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(json.loads(response.content), {'version': '0.1.dummy'})


class TestDataExportTasksView(BaseTestViewMixin):
    """Tests for DataExportTasksView"""
    view_actions = ['detail', 'list']

    def set_action(self, action, task_id=1):
        """Set the viewname and client method"""
        self.view_name = f'fx_dashboard:data-export-tasks-{action}'
        self.url_args = []
        if action == 'detail':
            self.url_args = [task_id]

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        registry = {}
        for _, viewset, basename in urls.export_router.registry:
            registry[basename] = viewset

        for action in self.view_actions:
            self.set_action(action)
            view_class = registry['data-export-tasks']
            self.assertEqual(view_class.permission_classes, [FXHasTenantCourseAccess])

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        for action in self.view_actions:
            self.set_action(action)
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_non_staff_user(self):
        """Verify that user without required role can not access view."""
        for action in self.view_actions:
            self.set_action(action)
            learner_user = get_user_model().objects.get(id=45)
            self.login_user(learner_user.id)
            response = self.client.get(self.url, {})
            self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_list_success(self):
        """Verify view for list"""
        self.set_action('list')
        request = self._get_request()
        self.login_user(request.user.id)
        task = DataExportTask.objects.create(
            user=request.user,
            status=DataExportTask.STATUS_COMPLETED,
            view_name='exported_files_data',
            filename='test.csv',
            progress=1.0,
            tenant_id=1
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], task.id)

    def test_list_user_can_only_view_own_tasks(self):
        """Verify view for list - that the user can only view his tasks"""
        self.set_action('list')
        user1 = get_user_model().objects.get(id=4)
        user2 = get_user_model().objects.get(id=10)
        self.login_user(user1.id)
        user1_task1 = DataExportTask.objects.create(
            user=user1,
            status=DataExportTask.STATUS_COMPLETED,
            view_name='exported_files_data',
            filename='test1.csv',
            progress=1.0,
            tenant_id=1
        )
        user1_task2 = DataExportTask.objects.create(
            user=user1,
            status=DataExportTask.STATUS_COMPLETED,
            view_name='exported_files_data',
            filename='test2.csv',
            progress=1.0,
            tenant_id=1
        )
        # user1 shouldnt have access to the following task as it is created by user2
        DataExportTask.objects.create(
            user=user2,
            status=DataExportTask.STATUS_COMPLETED,
            view_name='exported_files_data',
            filename='test3.csv',
            progress=1.0,
            tenant_id=1
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
        self.assertEqual(response.data['results'][0]['id'], user1_task2.id)
        self.assertEqual(response.data['results'][1]['id'], user1_task1.id)

    def test_patch_success(self):
        """Verify view for update"""
        user = get_user_model().objects.get(id=4)
        self.login_user(user.id)
        task = DataExportTask.objects.create(
            user=user,
            status=DataExportTask.STATUS_COMPLETED,
            view_name='exported_files_data',
            filename='test.csv',
            progress=1.0,
            notes='dummy',
            tenant_id=1
        )
        self.set_action('detail', task.id)
        new_notes = 'dummy new'
        response = self.client.patch(
            self.url,
            data={'notes': new_notes},
            format='json',
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        task.refresh_from_db()
        self.assertEqual(task.notes, new_notes)
        self.assertEqual(response.data['id'], task.id)
        self.assertEqual(response.data['notes'], new_notes)

    def test_patch_user_can_only_edit_own_tasks(self):
        """Verify that the user can only update his tasks"""
        user1 = get_user_model().objects.get(id=4)
        user2 = get_user_model().objects.get(id=10)
        self.login_user(user1.id)
        user1_task = DataExportTask.objects.create(
            user=user1,
            status=DataExportTask.STATUS_COMPLETED,
            view_name='exported_files_data',
            filename='test1.csv',
            progress=1.0,
            tenant_id=1
        )
        self.assertEqual(user1_task.notes, '')
        self.set_action('detail', user1_task.id)
        response = self.client.patch(
            self.url,
            data={'notes': 'new notes'},
            format='json',
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        user1_task.refresh_from_db()
        self.assertEqual(user1_task.notes, 'new notes')

        # user1 shouldnt be able to update following as it is created by user2
        user2_task = DataExportTask.objects.create(
            user=user2,
            status=DataExportTask.STATUS_COMPLETED,
            view_name='exported_files_data',
            filename='test3.csv',
            progress=1.0,
            tenant_id=1
        )
        self.set_action('detail', user2_task.id)
        response = self.client.patch(
            self.url,
            data={'notes': 'new notes update'},
            format='json',
        )
        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)

    def test_patch_for_non_writable_fields(self):
        """Verify view for non writable fields."""
        user = get_user_model().objects.get(id=4)
        self.login_user(user.id)
        task = DataExportTask.objects.create(
            user=user,
            status=DataExportTask.STATUS_COMPLETED,
            view_name='exported_files_data',
            filename='test.csv',
            progress=1.0,
            notes='dummy',
            tenant_id=1
        )
        self.set_action('detail', task.id)
        response = self.client.patch(
            self.url,
            data={'filename': 'newname.csv', 'user': 45},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], task.id)
        # verify filename and user didn't update.
        self.assertEqual(response.data['filename'], 'test.csv')
        self.assertEqual(response.data['user_id'], user.id)

    def test_retrieve_success(self):
        """Verify view for retrieve"""
        user = get_user_model().objects.get(id=4)
        self.login_user(user.id)
        task = DataExportTask.objects.create(
            user=user,
            status=DataExportTask.STATUS_COMPLETED,
            view_name='exported_files_data',
            filename='test.csv',
            progress=1.0,
            notes='dummy',
            tenant_id=1
        )
        self.set_action('detail', task.id)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['id'], task.id)

    def test_not_allowed_methods(self):
        """Verify view for not allowed methods."""
        user = get_user_model().objects.get(id=4)
        self.login_user(user.id)
        task = DataExportTask.objects.create(
            user=user,
            status=DataExportTask.STATUS_COMPLETED,
            view_name='exported_files_data',
            filename='test.csv',
            progress=1.0,
            notes='dummy',
            tenant_id=1
        )
        self.set_action('detail', task.id)
        response = self.client.put(
            self.url,
            data={'notes': 'new'},
            format='json',
        )
        self.assertEqual(response.status_code, 405)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 405)
        self.set_action('list', task.id)
        response = self.client.post(self.url, data={
            'user': 1,
            'view_name': 'fake',
            'filename': 'fake.csv',
            'notes': 'fake notes',
            'tenant_id': 1
        })
        self.assertEqual(response.status_code, 405)


@pytest.mark.usefixtures('base_data')
class TestAccessibleTenantsInfoView(BaseTestViewMixin):
    """Tests for AccessibleTenantsInfoView"""
    VIEW_NAME = 'fx_dashboard:accessible-info'

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        view_func, _, _ = resolve(self.url)
        view_class = view_func.view_class
        self.assertEqual(view_class.permission_classes, [IsAnonymousOrSystemStaff])

    @patch('futurex_openedx_extensions.dashboard.views.get_user_by_username_or_email')
    def test_success(self, mock_get_user):
        """Verify that the view returns the correct response"""
        mock_get_user.return_value = get_user_model().objects.get(username='user4')
        response = self.client.get(self.url, data={'username_or_email': 'dummy, the user loader function is mocked'})
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertDictEqual(json.loads(response.content), {
            '1': {
                'lms_root_url': 'https://s1.sample.com',
                'studio_root_url': 'https://studio.example.com',
                'platform_name': 's1 platform name',
                'logo_image_url': '',
            },
            '2': {
                'lms_root_url': 'https://s2.sample.com',
                'studio_root_url': 'https://studio.example.com',
                'platform_name': '', 'logo_image_url': ''
            },
            '7': {
                'lms_root_url': 'https://s7.sample.com',
                'studio_root_url': 'https://studio.example.com',
                'platform_name': '', 'logo_image_url': ''
            },
        })

    @patch('futurex_openedx_extensions.dashboard.views.get_user_by_username_or_email')
    def test_no_username_or_email(self, mock_get_user):
        """Verify that the view returns the correct response"""
        mock_get_user.side_effect = get_user_model().DoesNotExist()
        response = self.client.get(self.url)
        mock_get_user.assert_called_once_with(None)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertDictEqual(json.loads(response.content), {})

    def test_not_existing_username_or_email(self):
        """Verify that the view returns the correct response"""
        response = self.client.get(self.url, data={'username_or_email': 'dummy'})
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertDictEqual(json.loads(response.content), {})


@pytest.mark.usefixtures('base_data')
class TestAccessibleTenantsInfoViewV2(BaseTestViewMixin):
    """Tests for AccessibleTenantsInfoViewv2"""
    VIEW_NAME = 'fx_dashboard:accessible-info-v2'

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        view_func, _, _ = resolve(self.url)
        view_class = view_func.view_class
        self.assertEqual(view_class.permission_classes, [FXHasTenantCourseAccess])

    @patch('futurex_openedx_extensions.dashboard.views.get_user_by_username_or_email')
    def test_success(self, mock_get_user):
        """Verify that the view returns the correct response"""
        mock_get_user.return_value = get_user_model().objects.get(username='user4')
        self.login_user(self.staff_user)
        response = self.client.get(self.url, data={'username_or_email': 'dummy, the user loader function is mocked'})
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertDictEqual(json.loads(response.content), {
            '1': {
                'lms_root_url': 'https://s1.sample.com',
                'studio_root_url': 'https://studio.example.com',
                'platform_name': 's1 platform name',
                'logo_image_url': '',
            },
            '2': {
                'lms_root_url': 'https://s2.sample.com',
                'studio_root_url': 'https://studio.example.com',
                'platform_name': '', 'logo_image_url': ''
            },
            '7': {
                'lms_root_url': 'https://s7.sample.com',
                'studio_root_url': 'https://studio.example.com',
                'platform_name': '', 'logo_image_url': ''
            },
        })

        self.login_user(5)
        response = self.client.get(self.url, data={'username_or_email': 'dummy'})
        self.assertEqual(
            response.status_code,
            http_status.HTTP_403_FORBIDDEN,
            f'Expected 403 for non staf users, but got {response.status_code}'
        )

    @patch('futurex_openedx_extensions.dashboard.views.get_user_by_username_or_email')
    def test_no_username_or_email(self, mock_get_user):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        mock_get_user.side_effect = get_user_model().DoesNotExist()
        response = self.client.get(self.url)
        mock_get_user.assert_called_once_with(None)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertDictEqual(json.loads(response.content), {})

    def test_not_existing_username_or_email(self):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url, data={'username_or_email': 'dummy'})
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertDictEqual(json.loads(response.content), {})


@pytest.mark.usefixtures('base_data')
class TestLearnersDetailsForCourseView(BaseTestViewMixin):
    """Tests for LearnersDetailsForCourseView"""
    VIEW_NAME = 'fx_dashboard:learners-course'

    def setUp(self):
        """Setup"""
        super().setUp()
        self.url_args = ['course-v1:ORG1+5+5']

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        view_func, _, _ = resolve(self.url)
        view_class = view_func.view_class
        self.assertEqual(view_class.permission_classes, [FXHasTenantCourseAccess])

    def test_get_related_id(self):
        """Verify get_related_id returns course_id"""
        view_func, _, kwargs = resolve(self.url)
        view = view_func.view_class()
        view.kwargs = kwargs
        expected_related_id = 'course-v1:ORG1+5+5'
        related_id = view.get_related_id()
        assert expected_related_id == related_id

    def test_success(self):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 3)
        self.assertGreater(len(response.data['results']), 0)


@pytest.mark.usefixtures('base_data')
@ddt.ddt
class TestLearnersEnrollmentView(BaseTestViewMixin):
    """Tests for LearnersEnrollmentView"""
    VIEW_NAME = 'fx_dashboard:learners-enrollements'

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
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        user_id = 15
        course_id = 'course-v1:ORG1+5+5'
        response = self.client.get(self.url, data={'course_ids': course_id, 'user_ids': user_id})
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['user_id'], user_id)
        self.assertEqual(response.data['results'][0]['course_id'], course_id)

    def test_success_for_user_ids_and_usernames(self):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url, data={
            'user_ids': 15,
            'usernames': 'user21, user15',
        })
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 6)
        self.assertEqual(
            set(user_data['user_id'] for user_data in response.data['results']),
            {15, 21}
        )

    @ddt.data(
        ('0', '1', 0.0, 1.0),
        ('0.5', '0.9', 0.5, 0.9),
        ('', '', -1.0, -1.0),
        (None, None, -1.0, -1.0),
        ('-1', '-1', -1.0, -1.0),
        ('0', '', 0.0, -1.0),
        ('', '0.8', -1.0, 0.8),
    )
    @ddt.unpack
    def test_valid_progress_range(self, progress_min, progress_max, expected_min, expected_max):
        """Verify that valid progress ranges are returned correctly"""
        result = LearnersEnrollmentView.validate_progress_range(progress_min, progress_max)
        self.assertEqual(result, (expected_min, expected_max))

    def test_min_greater_than_max_raises(self):
        """Verify that progress_min greater than progress_max raises FXCodedException"""
        with self.assertRaises(FXCodedException) as ctx:
            LearnersEnrollmentView.validate_progress_range('0.8', '0.5')

        self.assertEqual(ctx.exception.code, FXExceptionCodes.INVALID_INPUT.value)
        self.assertIn('progress_min cannot be greater than progress_max', str(ctx.exception))

    @ddt.data(
        ('abc', '0.5', 'progress_min'),
        ('0.2', 'xyz', 'progress_max'),
        ('1.01', '0.5', 'progress_min'),
        ('0.2', '1.01', 'progress_max'),
    )
    @ddt.unpack
    def test_invalid_number(self, progress_min, progress_max, variable_name):
        """Verify that invalid progress values raise FXCodedException"""
        with self.assertRaises(FXCodedException) as ctx:
            LearnersEnrollmentView.validate_progress_range(progress_min, progress_max)

        self.assertEqual(ctx.exception.code, FXExceptionCodes.INVALID_INPUT.value)
        self.assertIn(variable_name, str(ctx.exception))


class MockClickhouseQuery:
    """Mock ClickhouseQuery"""
    def __init__(
        self, query, slug, version, scope, enabled, params_config, paginated
    ):  # pylint: disable=too-many-arguments
        self.query = query
        self.slug = slug
        self.version = version
        self.scope = scope
        self.enabled = enabled
        self.params_config = params_config
        self.paginated = paginated

    def fix_param_types(self, *args, **kwargs):
        """Mock parse_query"""
        return self.query

    @classmethod
    def get_query_record(cls, scope, version, slug):
        """Mock get_query_record"""
        if slug == 'non-existing-query':
            return None

        paginated = not slug.endswith('-nop')

        enabled = 'disabled' not in slug

        query = 'SELECT * FROM table'
        if 'ca-users' in slug:
            query += f' WHERE user_id IN {{{{{cs.CLICKHOUSE_FX_BUILTIN_CA_USERS_OF_TENANTS}}}}}'

        return MockClickhouseQuery(
            query=query,
            slug=slug,
            version=version,
            scope=scope,
            enabled=enabled,
            params_config={},
            paginated=paginated,
        )


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

        with patch('futurex_openedx_extensions.dashboard.views.get_courses_ratings') as mocked_calc:
            mocked_calc.return_value = test_data
            response = self.client.get(self.url)
        data = json.loads(response.content)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(data, expected_result)

    def test_success_no_rating(self):
        """Verify that the view returns the correct response when there are no ratings"""
        self.login_user(self.staff_user)
        with patch('futurex_openedx_extensions.dashboard.views.get_courses_ratings') as mocked_calc:
            mocked_calc.return_value = {
                'total_rating': 0,
                'courses_count': 0,
                'rating_1_count': 0,
                'rating_2_count': 0,
                'rating_3_count': 0,
                'rating_4_count': 0,
                'rating_5_count': 0,
            }
            response = self.client.get(self.url)
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


@ddt.ddt
class TestMyRolesView(BaseTestViewMixin):
    """Tests for MyRolesView"""
    VIEW_NAME = 'fx_dashboard:my-roles'

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
        self.login_user(3)
        expected_result = {
            'user_id': 3,
            'email': 'user3@example.com',
            'username': 'user3',
            'national_id': '11223344556677',
            'full_name': '',
            'alternative_full_name': '',
            'is_system_staff': False,
            'global_roles': [],
            'tenants': {
                '1': {
                    'tenant_roles': ['staff'],
                    'course_roles': {
                        'course-v1:ORG1+3+3': ['instructor'],
                        'course-v1:ORG1+4+4': ['instructor'],
                    },
                },
            },
        }
        response = self.client.get(self.url)
        data = json.loads(response.content)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertFalse(DeepDiff(data, expected_result))


@ddt.ddt
class TestUserRolesManagementView(BaseTestViewMixin):
    """Tests for UserRolesManagementView for GET list"""
    def set_action(self, action):
        """Set the action"""
        self.view_name = f'fx_dashboard:user-roles-{action}'
        if action == 'detail':
            self.url_args = ['user4']

    def test_dispatch_is_non_atomic(self):
        """Verify that the view has the correct dispatch method"""
        dispatch_method = UserRolesManagementView.dispatch
        is_non_atomic = getattr(dispatch_method, '_non_atomic_requests', False)
        self.assertTrue(
            is_non_atomic,
            'dispatch method should be decorated with non_atomic_requests. atomic is used internally when needed'
        )

    @ddt.data('list', 'detail')
    def test_permission_classes(self, action):
        """Verify that the view has the correct permission classes"""
        self.set_action(action)

        registry = {}
        for _, viewset, basename in urls.roles_router.registry:
            registry[basename] = viewset
        view_class = registry['user-roles']
        self.assertEqual(view_class.permission_classes, [FXHasTenantAllCoursesAccess])

    @ddt.data('list', 'detail')
    def test_unauthorized(self, action):
        """Verify that the view returns 403 when the user is not authenticated"""
        self.set_action(action)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_bad_course_id(self):
        """Verify that the view returns 400 when the course ID is invalid"""
        self.set_action('list')

        self.login_user(self.staff_user)
        response = self.client.get(self.url, data={'only_course_ids': 'course-v1:ORG1+4+4,invalid-course-id'})
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertIn('Invalid course ID format: invalid-course-id', response.data['detail'])

    def test_success_list(self):
        """Verify that the view returns the correct response when list action is used"""
        self.set_action('list')

        self.login_user(self.staff_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        test_data = get_test_data_dict()
        assert len(response.data['results']) == len(test_data)
        for user_roles in response.data['results']:
            username = user_roles['username']
            assert username in test_data
            del test_data[username]

        assert not test_data

    def test_success_detail(self):
        """Verify that the view returns the correct response when detail action is used"""
        self.set_action('detail')

        self.login_user(self.staff_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        assert response.data['tenants'] == {
            1: {'tenant_roles': ['instructor'], 'course_roles': {'course-v1:ORG1+4+4': ['staff']}},
            2: {'tenant_roles': ['instructor'], 'course_roles': {'course-v1:ORG3+1+1': ['staff']}},
            7: {'tenant_roles': ['instructor'], 'course_roles': {'course-v1:ORG3+1+1': ['staff']}}
        }

    @patch('futurex_openedx_extensions.dashboard.views.add_course_access_roles')
    def test_post_success(self, mock_add_users):
        """Verify that the view returns 201 for POST"""
        self.set_action('list')

        self.login_user(self.staff_user)
        mock_add_users.return_value = {
            'failed': [],
            'added': ['shadinaif', 'ahmad@gmail.com'],
            'updated': [10098765],
            'not_updated': [],
        }
        response = self.client.post(
            self.url,
            data={
                'tenant_ids': [9],
                'users': ['shadinaif', 'ahmad@gmail.com', 10098765],
                'role': 'staff',
                'tenant_wide': False,
                'course_ids': ['course-v1:ORG1+TOPIC+2024', 'course-v1:ORG1+TOPIC2+2024'],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(json.loads(response.content), mock_add_users.return_value)

    @patch('futurex_openedx_extensions.dashboard.views.add_course_access_roles')
    @ddt.data(
        ('tenant_ids', 'not list', True, 'tenant_ids must be a list of integers'),
        ('tenant_ids', [1, 'not int'], True, 'tenant_ids must be a list of integers'),
        ('users', 'not list', True, 'users must be a list'),
        ('role', ['not str'], True, 'role must be a string'),
        ('tenant_wide', 'not int', True, 'tenant_wide must be an integer flag'),
        ('course_ids', 'not list', False, 'course_ids must be a list'),
    )
    @ddt.unpack
    def test_post_validation_error(
        self, key, value, is_required, error_message, mock_add_users
    ):  # pylint: disable=too-many-arguments
        """Verify that the view returns 400 for POST when the payload is invalid"""
        error_message = f'({FXExceptionCodes.INVALID_INPUT.value}) {error_message}'
        self.set_action('list')
        self.login_user(self.staff_user)
        data = {
            'tenant_ids': [9],
            'users': ['shadinaif', 'ahmad@gmail.com', 10098765],
            'role': 'staff',
            'tenant_wide': False,
            'course_ids': ['course-v1:ORG1+TOPIC+2024', 'course-v1:ORG1+TOPIC2+2024'],
        }

        data.pop(key)
        mock_add_users.return_value = {}
        response = self.client.post(self.url, data=data, format='json')
        if is_required:
            self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
            self.assertEqual(response.data, {
                'reason': f"Missing required parameter: '{key}'", 'details': {}
            })
        else:
            self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)

        data.update({key: value})
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {'reason': error_message, 'details': {}})

    @patch('futurex_openedx_extensions.dashboard.views.add_course_access_roles')
    def test_post_add_validation_error(self, mock_add_users):
        """Verify that the view returns 400 for POST when the payload is invalid"""
        self.set_action('list')
        self.login_user(self.staff_user)
        data = {
            'tenant_ids': [9],
            'users': ['shadinaif', 'ahmad@gmail.com', 10098765],
            'role': 'staff',
            'tenant_wide': False,
            'course_ids': ['course-v1:ORG1+TOPIC+2024', 'course-v1:ORG1+TOPIC2+2024'],
        }

        mock_add_users.side_effect = FXCodedException(
            code=FXExceptionCodes.INVALID_INPUT,
            message='an internal validation error!'
        )
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data,
            {'reason': f'({FXExceptionCodes.INVALID_INPUT.value}) an internal validation error!', 'details': {}}
        )

    def test_put_bad_username(self):
        """Verify that the view returns 404 when the given username is invalid"""
        self.set_action('detail')
        self.url_args = ['invalid_username']

        self.login_user(self.staff_user)
        response = self.client.put(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data, {
            'reason': '(1001) User with username/email (invalid_username) does not exist!', 'details': {}
        })

    @patch('futurex_openedx_extensions.dashboard.views.update_course_access_roles')
    @patch('futurex_openedx_extensions.dashboard.views.UserRolesManagementView.verify_username')
    def test_put_failed(self, mock_verify_username, mock_update_users):
        """Verify that the view returns 400 when the fails for any reason"""
        self.set_action('detail')

        self.login_user(self.staff_user)
        mock_verify_username.return_value = {
            'user': get_user_model().objects.get(id=4),
            'key_type': cs.USER_KEY_TYPE_USERNAME,
            'error_code': None,
            'error_message': None,
        }
        mock_update_users.return_value = {
            'error_code': '999',
            'error_message': 'the error message',
        }
        response = self.client.put(self.url)

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {
            'reason': '(999) the error message', 'details': {}
        })

    @patch('futurex_openedx_extensions.dashboard.views.update_course_access_roles')
    @patch('futurex_openedx_extensions.dashboard.views.UserRolesManagementView.verify_username')
    def test_put_success(self, mock_verify_username, mock_update_users):
        """Verify that the view returns 204 for PUT"""
        self.set_action('detail')

        self.login_user(self.staff_user)
        mock_update_users.return_value = {
            'error_code': None,
            'error_message': None,
        }
        mock_verify_username.return_value = {
            'user': get_user_model().objects.get(id=4),
            'key_type': cs.USER_KEY_TYPE_USERNAME,
            'error_code': None,
            'error_message': None,
        }
        response = self.client.put(self.url, data={'the data': 'whatever, the function is mocked'})
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['user_id'], 4)

    @patch('futurex_openedx_extensions.dashboard.views.get_user_by_key')
    def test_delete_bad_username(self, mock_get_user):
        """Verify that the view returns 400 when the user tries to delete their own roles"""
        self.set_action('detail')

        mock_get_user.return_value = {
            'user': None,
            'key_type': cs.USER_KEY_TYPE_NOT_ID,
            'error_code': '999',
            'error_message': 'the error message',
        }
        self.url_args = ['invalid_username']

        self.login_user(self.staff_user)
        response = self.client.delete(self.url + '?tenant_ids=1,2')
        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data, {'reason': '(999) the error message', 'details': {}})

    @patch('futurex_openedx_extensions.dashboard.views.get_user_by_key')
    def test_delete_missing_required_parameter(self, _):
        """Verify that the view returns 400 when there is a missing required-parameter"""
        self.set_action('detail')

        self.login_user(self.staff_user)
        response = self.client.delete(self.url + '?tenant_ids_not_sent_in_query_params=x')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {'reason': "Missing required parameter: 'tenant_ids'", 'details': {}})

    @patch('futurex_openedx_extensions.dashboard.views.get_user_by_key')
    @patch('futurex_openedx_extensions.dashboard.views.delete_course_access_roles')
    def test_delete_success(self, mock_delete_user, mock_get_user):
        """Verify that the view returns 400 when the user tries to delete their own roles"""
        self.set_action('detail')

        mock_get_user.return_value = {
            'user': get_user_model().objects.get(id=4),
            'key_type': cs.USER_KEY_TYPE_ID,
            'error_code': None,
            'error_message': None,
        }

        self.login_user(self.staff_user)
        response = self.client.delete(self.url + '?tenant_ids=1,2')
        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)
        self.assertIsNone(response.data)
        mock_delete_user.call_args_list[0][1].pop('caller')
        mock_delete_user.assert_called_once_with(tenant_ids=[1, 2], user=mock_get_user.return_value['user'])

    @patch('futurex_openedx_extensions.dashboard.views.get_user_by_key')
    @patch('futurex_openedx_extensions.dashboard.views.delete_course_access_roles')
    def test_delete_no_roles_found_for_user(self, mock_delete_user, mock_get_user):
        """Verify that the view returns 404 when no roles are found for the user"""
        self.set_action('detail')

        mock_get_user.return_value = {
            'user': get_user_model().objects.get(id=3),
            'key_type': cs.USER_KEY_TYPE_ID,
            'error_code': None,
            'error_message': None,
        }
        mock_delete_user.side_effect = FXCodedException(999, 'the error message')
        self.login_user(self.staff_user)
        response = self.client.delete(self.url + '?tenant_ids=1')
        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)
        self.assertDictEqual(response.data, {'reason': 'the error message', 'details': {}})


class TestExcludedTenantsView(BaseTestViewMixin):
    """Tests for ExcludedTenantsView"""
    VIEW_NAME = 'fx_dashboard:excluded-tenants'

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        view_func, _, _ = resolve(self.url)
        view_class = view_func.view_class
        self.assertEqual(view_class.permission_classes, [IsSystemStaff])

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_success(self):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(json.loads(response.content), {
            '4': [FXExceptionCodes.TENANT_HAS_NO_LMS_BASE.value],
            '5': [FXExceptionCodes.TENANT_COURSE_ORG_FILTER_NOT_VALID.value],
            '6': [FXExceptionCodes.TENANT_HAS_NO_SITE.value],
        })


@pytest.mark.usefixtures('base_data')
class TestTenantInfoView(BaseTestViewMixin):
    """Tests for TenantInfoView"""
    VIEW_NAME = 'fx_dashboard:tenant-info'

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        self.url_args = ['1']
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_no_permission(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        self.url_args = ['1']
        self.login_user(11)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_success(self):
        """Verify that the view returns the correct response"""
        self.url_args = ['1']
        self.login_user(3)
        expected_result = {
            'tenant_id': 1,
            'lms_root_url': 'https://s1.sample.com',
            'studio_root_url': 'https://studio.example.com',
            'platform_name': 's1 platform name',
            'logo_image_url': '',
        }
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertFalse(DeepDiff(response.json(), expected_result))


@ddt.ddt
class TestClickhouseQueryView(MockPatcherMixin, BaseTestViewMixin):
    """Tests for ClickhouseQueryView"""
    VIEW_NAME = 'fx_dashboard:clickhouse-query'

    patching_config = {
        'get_query_record': ('futurex_openedx_extensions.dashboard.views.ClickhouseQuery.get_query_record', {
            'side_effect': MockClickhouseQuery.get_query_record,
        }),
        'parse_query': ('futurex_openedx_extensions.dashboard.views.ClickhouseQuery.fix_param_types', {
            'side_effect': MockClickhouseQuery.fix_param_types,
        }),
        'get_client': ('futurex_openedx_extensions.helpers.clickhouse_operations.get_client', {}),
        'execute_query': ('futurex_openedx_extensions.helpers.clickhouse_operations.execute_query', {
            'return_value': (100, 2, Mock(column_names=['col_name'], result_rows=[[1]])),
        }),
        'get_usernames_with_access_roles': (
            'futurex_openedx_extensions.dashboard.views.get_usernames_with_access_roles',
            {'return_value': []}
        ),
    }

    def setUp(self):
        """Setup"""
        super().setUp()
        self.url_args = ['course', 'test-query']

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        view_func, _, _ = resolve(self.url)
        view_class = view_func.view_class
        self.assertEqual(view_class.permission_classes, [FXHasTenantCourseAccess])

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_success(self):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(json.loads(response.content), {
            'count': 100,
            'next': 'http://testserver/api/fx/query/v1/course/test-query/?page=2',
            'previous': None,
            'results': [{'col_name': 1}]
        })
        self.mocks['get_usernames_with_access_roles'].assert_not_called()

    def test_success_no_pagination(self):
        """Verify that the view returns the correct response when pagination is disabled"""
        self.url_args = ['course', 'test-query-nop']

        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(json.loads(response.content), [{'col_name': 1}])
        self.mocks['get_usernames_with_access_roles'].assert_not_called()

    def test_success_ca_users_needed(self):
        """Verify that the view gets the CA users when the query needs them"""
        self.url_args = ['course', 'test-query-ca-users-nop']
        all_orgs = ['org1', 'org2', 'org3', 'org8', 'org4', 'org5']

        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(json.loads(response.content), [{'col_name': 1}])
        self.mocks['get_usernames_with_access_roles'].assert_called_once_with(all_orgs)

    @ddt.data(
        ('?page=3', 5, '?page=5'),
        ('?page=3', 1, '?page=1'),
        ('?page=3&page_size=33', 5, '?page_size=33&page=5'),
        ('?page=3&whatever=any&page_size=33', 5, '?whatever=any&page_size=33&page=5'),
        ('?page=3&whatever=any&page_size=33', None, None),
    )
    @ddt.unpack
    def test_get_page_url_with_page(self, param_string, new_page_no, expected_result):
        """Verify that get_page_url_with_page returns the correct URL"""
        url = f'http://testserver/api/fx/query/v1/course/test-query/{param_string}'

        if expected_result:
            expected_result = f'http://testserver/api/fx/query/v1/course/test-query/{expected_result}'

        self.assertEqual(views.ClickhouseQueryView.get_page_url_with_page(url, new_page_no), expected_result)

    @ddt.data(
        ({}, True, (1, DefaultPagination.page_size)),
        ({'page': '4'}, True, (4, DefaultPagination.page_size)),
        ({'page': None}, True, (1, DefaultPagination.page_size)),
        ({'page': '2', 'page_size': '23'}, True, (2, 23)),
        ({'page_size': '23'}, True, (1, 23)),
        ({}, False, (None, DefaultPagination.page_size)),
        ({'page': '4'}, False, (None, DefaultPagination.page_size)),
        ({'page': None}, False, (None, DefaultPagination.page_size)),
        ({'page': '2', 'page_size': '23'}, False, (None, 23)),
        ({'page_size': '23'}, False, (None, 23)),
    )
    @ddt.unpack
    def test_pop_out_page_params(self, params, paginated, expected_result):
        """Verify that pop_out_page_params returns the correct page number and page size"""
        self.assertEqual(views.ClickhouseQueryView.pop_out_page_params(params, paginated), expected_result)

    def _assert_not_ok_response(self, status_code, reason):
        """Helper to assert that the response is not OK"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status_code)
        self.assertEqual(response.data, {'details': {}, 'reason': reason})

    def test_query_does_no_exist(self):
        """Verify that the view returns 404 when the query does not exist"""
        self.url_args = ['course', 'non-existing-query']
        self._assert_not_ok_response(
            status_code=404,
            reason='Query not found course.v1.non-existing-query'
        )

    def test_query_not_enabled(self):
        """Verify that the view returns 400 when the query is not enabled"""
        self.url_args = ['course', 'test-query-disabled']
        self._assert_not_ok_response(
            status_code=400,
            reason='Query is disabled course.v1.test-query-disabled'
        )

    def test_empty_page(self):
        """Verify that the view returns 404 when the requested page is empty"""
        self.mocks['execute_query'].side_effect = EmptyPage('wrong page number!')
        self._assert_not_ok_response(
            status_code=404,
            reason='wrong page number!'
        )

    @ddt.data(
        ch.ClickhouseClientNotConfiguredError,
        ch.ClickhouseClientConnectionError,
    )
    def test_clickhouse_connection_error(self, side_effect):
        """Verify that the view returns 503 when there is a Clickhouse connection error"""
        self.mocks['get_client'].side_effect = side_effect('connection issue with clickhouse')
        self._assert_not_ok_response(
            status_code=503,
            reason='connection issue with clickhouse'
        )

    @ddt.data(
        ch.ClickhouseBaseError,
        ValueError,
        ValidationError,
    )
    def test_bad_use_of_arguments(self, side_effect):
        """Verify that the view returns 400 when there is a bad use of arguments"""
        self.mocks['execute_query'].side_effect = side_effect('bad use of arguments')
        self._assert_not_ok_response(
            status_code=400,
            reason='bad use of arguments'
        )


@pytest.mark.usefixtures('base_data')
class TestConfigEditableInfoView(BaseTestViewMixin):
    """Tests for ConfigEditableInfoView"""
    VIEW_NAME = 'fx_dashboard:config-editable-info'

    def test_success(self):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)

        ConfigAccessControl.objects.create(key_name='platform_name', path='platform_name', writable=True)
        ConfigAccessControl.objects.create(key_name='pages', path='theme_v2,sections,pages', writable=True)
        ConfigAccessControl.objects.create(key_name='primary_color', path='theme_v2,primary_color', writable=False)
        response = self.client.get(self.url, data={'tenant_ids': 1})
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        expected_data = {
            'editable_fields': ['platform_name', 'pages'],
            'read_only_fields': ['primary_color']
        }
        self.assertEqual(response.json(), expected_data)

    def test_one_tenant(self):
        """Verify that ConfigEditableInfoView calls verify_one_tenant_id_provided."""
        self.login_user(self.staff_user)
        with patch(
            'futurex_openedx_extensions.dashboard.views.ConfigEditableInfoView.verify_one_tenant_id_provided'
        ) as mock_verify_one_tenant:
            mock_verify_one_tenant.return_value = 1
            response = self.client.get(self.url, data={'tenant_ids': '1'})
            mock_verify_one_tenant.assert_called_once()
            self.assertEqual(response.status_code, http_status.HTTP_200_OK)


class DraftConfigDataMixin:  # pylint: disable=too-few-public-methods
    """Mixin to create draft config data for tests"""
    def setUp(self):
        """Setup"""
        super().setUp()
        draft_config = DraftConfig.objects.create(
            tenant_id=1,
            config_path='theme_v2.links.facebook',
            config_value='draft.facebook.com',
            created_by_id=1,
            updated_by_id=1,
        )
        draft_config.revision_id = 88776655
        draft_config.save()


@ddt.ddt
@pytest.mark.usefixtures('base_data')
class TestThemeConfigDraftView(DraftConfigDataMixin, BaseTestViewMixin):
    """Tests for ThemeConfigDraftView"""
    VIEW_NAME = 'fx_dashboard:theme-config-draft'

    def test_only_authorized_users_can_retrieve_draft_config(self):
        """Verify that only authourized users can retrieve draft"""
        ConfigAccessControl.objects.create(key_name='facebook_link', path='theme_v2.links.facebook')
        tenant_config = TenantConfig.objects.get(id=1)
        self.url_args = [tenant_config.id]

        self.login_user(3)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertIn('updated_fields', response.json())

        self.login_user(10)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['reason'], 'User does not have access to the tenant (1)')

    def test_draft_config_retrieve_success(self):
        """Verify that the view returns the correct response"""
        tenant_config = TenantConfig.objects.get(id=1)
        ConfigAccessControl.objects.create(key_name='facebook_link', path='theme_v2.links.facebook')
        self.login_user(self.staff_user)
        self.url_args = [tenant_config.id]
        expected_result = {
            'facebook_link': {
                'published_value': 'facebook.com',
                'draft_value': 'draft.facebook.com'
            }
        }
        expected_hash = hashlib.sha256(
            json.dumps(expected_result, sort_keys=True, separators=(',', ':')).encode()
        ).hexdigest()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        assert response.json()['updated_fields'] == expected_result
        assert response.json()['draft_hash'] == expected_hash

    @ddt.data(
        (
            {},
            "Missing required parameter: 'key'"
        ),
        (
            {'key': 'not-exist'},
            'Invalid key, unable to find key: (not-exist) in config access control'
        ),
        (
            {'key': 'non-writable'},
            '(4001) Config Key: (non-writable) is not writable.'
        ),
        (
            {'key': 123},
            '(4001) Key name must be a string.'
        ),
        (
            {'key': 'platform_name'},
            '(4001) Provide either new_value or reset.'
        ),
        (
            {'key': 'platform_name', 'new_value': 'new updated name'},
            "Missing required parameter: 'current_revision_id'"
        ),
    )
    @ddt.unpack
    def test_put_payload_validation(self, data, expected_reason):
        """Verify that different validation cases return the correct error message."""
        tenant_config = TenantConfig.objects.create(
            external_key='test',
            lms_configs={
                'platform_name': 'my name',
                'theme_v2': {'pages': ['home_page']},
                'config_draft': {},
                'LMS_BASE': 'example.com',
                'non-writable': 'some data',
                'course_org_filter': 'example',
            }
        )
        Route.objects.create(
            domain='example.com',
            config=tenant_config
        )
        ConfigAccessControl.objects.create(
            key_name='platform_name', path='platform_name', writable=True, key_type='string'
        )
        ConfigAccessControl.objects.create(
            key_name='pages', path='theme_v2.pages', writable=True, key_type='list'
        )
        ConfigAccessControl.objects.create(
            key_name='non-writable', path='non-writable', writable=False, key_type='string'
        )

        self.login_user(self.staff_user)
        self.url_args = [tenant_config.id]
        response = self.client.put(self.url, data=data, format='json')

        assert response.status_code == http_status.HTTP_400_BAD_REQUEST
        assert response.data['reason'] == expected_reason

    @staticmethod
    def _prepare_data(tenant_id, config_path):
        """Helper to prepare data for the test"""
        tenant_config = TenantConfig.objects.get(id=tenant_id)
        assert tenant_config.lms_configs['platform_name'] == 's1 platform name'
        assert DraftConfig.objects.filter(tenant_id=tenant_id).count() == 1, 'bad test data'

        ConfigAccessControl.objects.create(key_name='platform_name', path=config_path, writable=True)
        assert DraftConfig.objects.filter(tenant_id=tenant_id, config_path=config_path).count() == 0, 'bad test data'

    @patch('futurex_openedx_extensions.dashboard.views.ThemeConfigDraftView.validate_input')
    @patch('futurex_openedx_extensions.dashboard.views.update_draft_tenant_config')
    def test_draft_config_update(self, mock_update_draft, mocked_validate_input):
        """Verify that the view returns the correct response"""
        def _update_draft(**kwargs):
            """mock update_draft_tenant_config effect"""
            draft_config = DraftConfig.objects.create(
                tenant_id=1,
                config_path=config_path,
                config_value=new_value,
                created_by_id=1,
                updated_by_id=1,
            )
            draft_config.revision_id = 987
            draft_config.save()

        tenant_id = 1
        config_path = 'platform_name'
        self.login_user(self.staff_user)
        self.url_args = [tenant_id]

        self._prepare_data(tenant_id, config_path)

        new_value = 's1 new name'
        mock_update_draft.side_effect = _update_draft

        response = self.client.put(
            self.url,
            data={
                'key': 'platform_name',
                'new_value': new_value,
                'current_revision_id': '456',
            },
            format='json'
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK, response.data)
        self.assertEqual(response.data, {
            'bad_keys': [],
            'not_permitted': [],
            'revision_ids': {
                'platform_name': '987',
            },
            'values': {
                'platform_name': new_value,
            },
        })
        mock_update_draft.assert_called_once_with(
            tenant_id=tenant_id,
            config_path='platform_name',
            current_revision_id=456,
            new_value=new_value,
            reset=False,
            user=ANY,
        )
        mocked_validate_input.assert_called_once_with('456')

    @patch('futurex_openedx_extensions.dashboard.views.ThemeConfigDraftView.validate_input')
    @patch('futurex_openedx_extensions.dashboard.views.update_draft_tenant_config')
    @ddt.data(
        (None, False),
        ('not boolean', False),
        ('1', False),
        (1, False),
        (False, False),
        (True, True),
    )
    @ddt.unpack
    def test_draft_config_update_reset(self, reset_value, expected_passed_value, mock_update_draft, _):
        """Verify that `reset` is passed to update_draft_tenant_config correctly."""
        tenant_id = 1
        config_path = 'platform_name'
        self._prepare_data(tenant_id, config_path)

        self.url_args = [1]
        self.login_user(self.staff_user)
        self.client.put(
            self.url,
            data={
                'key': 'platform_name',
                'new_value': 'anything',
                'current_revision_id': '0',
                'reset': reset_value,
            },
            format='json'
        )
        mock_update_draft.assert_called_once_with(
            tenant_id=1,
            config_path=config_path,
            current_revision_id=0,
            new_value='anything',
            reset=expected_passed_value,
            user=ANY,
        )

    def test_validate_input(self):
        """Verify the sad scenario when the validation is enabled."""
        with pytest.raises(FXCodedException) as exc_info:
            ThemeConfigDraftView.validate_input('not numeric')
        self.assertEqual(exc_info.value.code, FXExceptionCodes.INVALID_INPUT.value)
        self.assertEqual(str(exc_info.value), 'current_revision_id type must be numeric value.')

    def test_put_with_conflicted_revision_id(self):
        """Verify that the view returns 409 when the revision_id is conflicted."""
        tenant_config = TenantConfig.objects.get(id=1)
        self.login_user(self.staff_user)
        self.url_args = [tenant_config.id]

        assert DraftConfig.objects.filter(tenant_id=1).count() == 1, 'bad test data'
        draft_config = DraftConfig.objects.get(tenant_id=1)
        draft_config.revision_id = 456
        draft_config.save()
        ConfigAccessControl.objects.create(key_name='links', path=draft_config.config_path, writable=True)

        not_the_correct_revision_id = draft_config.revision_id + 1
        response = self.client.put(
            self.url,
            data={
                'key': 'links',
                'new_value': 'new value',
                'current_revision_id': not_the_correct_revision_id,
            },
            format='json'
        )
        self.assertEqual(response.status_code, http_status.HTTP_409_CONFLICT, response.data)
        self.assertEqual(
            response.data['reason'],
            '(13003) Failed to update all the specified draft config paths.',
        )

    @patch('futurex_openedx_extensions.dashboard.views.update_draft_tenant_config')
    def test_draft_config_update_fails(self, mock_update_draft):
        """
        Verify that if the update_draft_tenant_config fails for any reason other than FXExceptionCodes.UPDATE_FAILED
        it'll return 400 with the error message.
        """
        self.login_user(self.staff_user)
        self.url_args = [1]
        ConfigAccessControl.objects.create(key_name='facebook', path='theme_v2.links.facebook', writable=True)

        mock_update_draft.side_effect = FXCodedException(
            code=FXExceptionCodes.INVALID_INPUT,
            message='some error message',
        )

        response = self.client.put(
            self.url,
            data={
                'key': 'facebook',
                'new_value': 'any value',
                'current_revision_id': '456',
            },
            format='json'
        )
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data['reason'], '(4001) some error message')

    def test_draft_config_delete(self):
        """Verify that the view returns the correct response"""
        tenant_config = TenantConfig.objects.get(id=1)
        assert DraftConfig.objects.filter(tenant_id=1).count() != 0
        self.url_args = [tenant_config.id]

        self.login_user(23)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['reason'], 'User does not have access to the tenant (1)')
        tenant_config.refresh_from_db()
        assert DraftConfig.objects.filter(tenant_id=1).count() != 0

        self.login_user(8)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)
        tenant_config.refresh_from_db()
        assert DraftConfig.objects.filter(tenant_id=1).count() == 0


@ddt.ddt
@pytest.mark.usefixtures('base_data')
class TestThemeConfigPublishView(DraftConfigDataMixin, BaseTestViewMixin):
    """Tests for ThemeConfigPublishView"""
    VIEW_NAME = 'fx_dashboard:theme-config-publish'

    @patch('futurex_openedx_extensions.dashboard.views.publish_tenant_config')
    def test_success(self, mocked_publish_config):
        """Verify that the view returns the correct response"""
        ConfigAccessControl.objects.create(key_name='platform_name', path='platform_name', key_type='string')
        ConfigAccessControl.objects.create(key_name='pages', path='theme_v2.pages', key_type='list')
        ConfigAccessControl.objects.create(key_name='links', path='theme_v2.links.facebook', key_type='string')
        updated_fields = {'links': {'published_value': 'facebook.com', 'draft_value': 'draft.facebook.com'}}
        expected_return_value = {
            'updated_fields': {
                'links': {'old_value': 'facebook.com', 'new_value': 'draft.facebook.com'}
            }
        }
        payload = {
            'draft_hash': dict_to_hash(updated_fields),
            'tenant_id': 1
        }
        self.login_user(10)
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['reason'], 'User does not have required access for tenant (1)')

        self.login_user(self.staff_user)
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        mocked_publish_config.assert_called_once_with(1)
        self.assertEqual(response.json(), expected_return_value)

    @ddt.data(
        ('does-not-matter', None, 'Tenant id is required and must be an int.', http_status.HTTP_400_BAD_REQUEST),
        ('does-not-matter', [], 'Tenant id is required and must be an int.', http_status.HTTP_400_BAD_REQUEST),
        ('does-not-matter', '', 'Tenant id is required and must be an int.', http_status.HTTP_400_BAD_REQUEST),
        ('does-not-matter', 'non-int', 'Tenant id is required and must be an int.', http_status.HTTP_400_BAD_REQUEST),
        ('does-not-matter', '1', 'Tenant id is required and must be an int.', http_status.HTTP_400_BAD_REQUEST),
        (None, 1, 'Draft hash is required and must be a string.', http_status.HTTP_400_BAD_REQUEST),
        ('', 1, 'Draft hash is required and must be a string.', http_status.HTTP_400_BAD_REQUEST),
        (['not str'], 1, 'Draft hash is required and must be a string.', http_status.HTTP_400_BAD_REQUEST),
        ('invalid_hash', 1, 'Draft hash mismatched with current draft values hash.', http_status.HTTP_400_BAD_REQUEST),
        ('does-bot-matter', 12, 'User does not have required access for tenant (12)', http_status.HTTP_403_FORBIDDEN),
    )
    @ddt.unpack
    def test_validations(self, draft_hash, tenant_id, expected_error, expected_status):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        response = self.client.post(self.url, data={
            'draft_hash': draft_hash,
            'tenant_id': tenant_id
        }, format='json')
        self.assertEqual(response.status_code, expected_status)
        self.assertEqual(response.data.get('reason'), expected_error)

    def test_dispatch_is_non_atomic(self):
        """Verify that the view has the correct dispatch method"""
        dispatch_method = ThemeConfigPublishView.dispatch
        is_non_atomic = getattr(dispatch_method, '_non_atomic_requests', False)
        self.assertTrue(
            is_non_atomic,
            'dispatch method should be decorated with non_atomic_requests. atomic is used internally when needed'
        )


@ddt.ddt
@pytest.mark.usefixtures('base_data')
class ThemeConfigRetrieveViewTest(DraftConfigDataMixin, BaseTestViewMixin):
    """Tests for ThemeConfigRetrieveView"""
    VIEW_NAME = 'fx_dashboard:theme-config-values'

    def test_success(self):
        """Verify that the view returns the correct response"""
        ConfigAccessControl.objects.create(key_name='platform_name', path='platform_name', key_type='string')
        ConfigAccessControl.objects.create(key_name='pages', path='theme_v2.pages', key_type='list')
        ConfigAccessControl.objects.create(key_name='links', path='theme_v2.links.facebook', key_type='string')
        self.login_user(self.staff_user)
        params = {
            'tenant_ids': '1',
            'keys': 'platform_name,pages,color,links',
            'published_only': '0'
        }
        response = self.client.get(self.url, data=params)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.json()['values'], {
            'platform_name': 's1 platform name',
            'pages': ['home_page'],
            'links': 'draft.facebook.com',
        })
        self.assertEqual(response.json()['revision_ids'], {
            'links': '88776655',
            'pages': '0',
            'platform_name': '0',
        })

        params['published_only'] = '1'
        response = self.client.get(self.url, data=params)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.json()['values'], {
            'platform_name': 's1 platform name',
            'pages': ['home_page'],
            'links': 'facebook.com',
        })
        self.assertEqual(response.json()['revision_ids'], {})

    def test_one_tenant(self):
        """Verify that ThemeConfigRetrieveView calls verify_one_tenant_id_provided."""
        self.login_user(8)
        with patch(
            'futurex_openedx_extensions.dashboard.views.ThemeConfigRetrieveView.verify_one_tenant_id_provided'
        ) as mock_verify_one_tenant:
            mock_verify_one_tenant.return_value = 1
            response = self.client.get(self.url, data={
                'tenant_ids': '1',
                'keys': '',
            })
            mock_verify_one_tenant.assert_called_once()
            self.assertEqual(response.status_code, http_status.HTTP_200_OK)


@ddt.ddt
@pytest.mark.usefixtures('base_data')
class ThemeConfigTenantView(BaseTestViewMixin):
    """Tests for ThemeConfigTenantView"""
    VIEW_NAME = 'fx_dashboard:theme-config-tenant'

    @ddt.data(
        (
            {'owner_user_id': None},
            'Subdomain is required.'
        ),
        (
            {'sub_domain': ['non', 'string'], 'owner_user_id': 1},
            'Subdomain must be a string.'
        ),
        (
            {'sub_domain': 'invalid_domain$', 'owner_user_id': 1},
            'Subdomain can only contain letters and numbers and cannot start with a number.'
        ),
        (
            {'sub_domain': '-startwithhyphen', 'owner_user_id': 1},
            'Subdomain can only contain letters and numbers and cannot start with a number.'
        ),
        (
            {'sub_domain': '1startwithnumber', 'owner_user_id': 1},
            'Subdomain can only contain letters and numbers and cannot start with a number.'
        ),
        (
            {'sub_domain': 'domain space', 'owner_user_id': 1},
            'Subdomain can only contain letters and numbers and cannot start with a number.'
        ),
        (
            {'sub_domain': '$pecial_chars!', 'owner_user_id': 1},
            'Subdomain can only contain letters and numbers and cannot start with a number.'
        ),
        (
            {'sub_domain': 'domain@domain', 'owner_user_id': 1},
            'Subdomain can only contain letters and numbers and cannot start with a number.'
        ),
        (
            {'sub_domain': 'LongString17Chars'},
            'Subdomain cannot exceed 16 characters.'
        ),
        (
            {'sub_domain': 'validsubdomain'},
            'Platform name is required.'
        ),
        (
            {'sub_domain': 'validsubdomain', 'platform_name': 11},
            'Platform name must be a string.'
        ),
        (
            {'sub_domain': 'validsubdomain', 'platform_name': 'Valid name', 'owner_user_id': 999999},
            'User with ID 999999 does not exist.'
        ),
    )
    @ddt.unpack
    def test_payload_validation(self, data, expected_reason):
        """Verify that different sub_domain cases raise the correct reason"""
        self.login_user(self.staff_user)
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, HTTP_400_BAD_REQUEST)
        assert response.data['reason'] == expected_reason

    @pytest.mark.django_db
    @patch('futurex_openedx_extensions.helpers.tenants.generate_tenant_config')
    @patch('futurex_openedx_extensions.dashboard.views.add_course_access_roles')
    @ddt.data(True, False)
    def test_success(self, owner_id_passed, mock_add_course_access_roles, mock_generate_config):
        """Verify that the view returns the correct response"""
        mock_generate_config.return_value = {
            'LMS_BASE': 'testplatform.local.overhang.io:8000',
            'SITE_NAME': 'http://testplatform.local.overhang.io:8000/',
            'course_org_filter': ['testplatform_org'],
        }
        self.login_user(self.staff_user)
        data = {
            'sub_domain': 'testplatform',
            'platform_name': 'Test Platform'
        }
        if owner_id_passed:
            data['owner_user_id'] = self.staff_user
        response = self.client.post(self.url, data=data, format='json')
        if owner_id_passed:
            mock_add_course_access_roles.assert_called_once()
        else:
            mock_add_course_access_roles.assert_not_called()
        assert response.status_code == http_status.HTTP_200_OK
        result = response.json()
        assert result['tenant_id'] > 0
        result.pop('tenant_id')
        assert result == {
            'lms_root_url': 'https://testplatform.local.overhang.io',
            'logo_image_url': '',
            'platform_name': '',
            'studio_root_url': 'https://studio.example.com',
        }


@pytest.mark.usefixtures('base_data')
class FileUploadView(BaseTestViewMixin):
    """Tests for FileUploadView"""
    VIEW_NAME = 'fx_dashboard:file-upload'

    @patch('futurex_openedx_extensions.dashboard.views.uuid.uuid4')
    @patch('futurex_openedx_extensions.dashboard.views.get_storage_dir')
    def test_success(self, mocked_storage_dir, mocked_uuid4):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        mocked_storage_dir.return_value = 'some-dummy-dir'
        mocked_uuid4.return_value = Mock(hex='12345678abcdef12')
        test_file = SimpleUploadedFile('test.png', b'file_content', content_type='image/png')
        data = {
            'file': test_file,
            'slug': 'test-slug',
            'tenant_id': 1
        }
        expected_file_name = 'test-slug-12345678.png'
        expected_storage_path = f'some-dummy-dir/{expected_file_name}'
        response = self.client.post('/api/fx/file/v1/upload/', data, format='multipart')
        assert response.status_code == http_status.HTTP_201_CREATED
        assert response.json()['uuid'] == '12345678'
        assert response.json()['url'] == default_storage.url(expected_storage_path)
        assert default_storage.exists(expected_storage_path)
        default_storage.delete(expected_storage_path)

    @patch('futurex_openedx_extensions.dashboard.views.get_storage_dir')
    def test_failure(self, mocked_storage_dir):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        response = self.client.post(
            '/api/fx/file/v1/upload/',
            data={
                'file': SimpleUploadedFile('test.png', b'file_content', content_type='image/png'),
                'slug': 'test-slug',
                'tenant_id': 10000000
            },
            format='multipart'
        )
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(str(response.data['tenant_id'][0]), 'Tenant with ID 10000000 does not exist.')

        mocked_storage_dir.side_effect = FXCodedException(code=0, message='Some error in file saving.')
        response = self.client.post(
            '/api/fx/file/v1/upload/',
            data={
                'file': SimpleUploadedFile('test.png', b'file_content', content_type='image/png'),
                'slug': 'test-slug',
                'tenant_id': 1
            },
            format='multipart'
        )
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['reason'], 'Some error in file saving.')

        response = self.client.post(
            '/api/fx/file/v1/upload/',
            data={
                'file': SimpleUploadedFile(
                    'file-with-invalid-extension.invalid', b'file_content', content_type='image/png'
                ),
                'slug': 'test-slug',
                'tenant_id': 1
            },
            format='multipart'
        )
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['reason'], f'Invalid file type. Allowed types are {ALLOWED_FILE_EXTENSIONS}.')

    @patch('futurex_openedx_extensions.dashboard.views.uuid.uuid4')
    @patch('futurex_openedx_extensions.dashboard.views.get_storage_dir')
    def test_file_upload_for_tenant_permission(self, mocked_storage_dir, mocked_uuid4):
        """Verify that the view returns the correct response"""
        self.login_user(1)
        mocked_storage_dir.return_value = 'some-dummy-dir'
        mocked_uuid4.return_value = Mock(hex='12345678abcdef12')
        test_file = SimpleUploadedFile('test.png', b'this is a test image content', content_type='image/png')
        expected_storage_path = 'some-dummy-dir/test-slug-12345678.png'
        data = {
            'file': test_file,
            'slug': 'test-slug',
        }

        data['tenant_id'] = 1
        response = self.client.post(self.url, data, format='multipart')
        assert response.status_code == http_status.HTTP_201_CREATED
        assert response.json()['url'] == default_storage.url(expected_storage_path)
        default_storage.delete(expected_storage_path)

        data['tenant_id'] = 6
        response = self.client.post(self.url, data, format='multipart')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(str(response.data['tenant_id'][0]), 'User does not have have required access for tenant (6).')


@pytest.mark.usefixtures('base_data')
class TestTenantAssetsManagementView(BaseTestViewMixin):
    """Tests for TenantAssetsManagementView"""
    view_actions = ['list']
    fake_storage_dir = 'some-dummy-dir'

    def set_action(self, action):
        """Set the viewname and client method"""
        self.view_name = f'fx_dashboard:tenant-assets-{action}'
        self.url_args = []

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        registry = {}
        for _, viewset, basename in urls.tenant_assets_router.registry:
            registry[basename] = viewset

        for action in self.view_actions:
            self.set_action(action)
            view_class = registry['tenant-assets']
            self.assertEqual(view_class.permission_classes, [FXHasTenantAllCoursesAccess])

    @patch('futurex_openedx_extensions.helpers.upload.uuid.uuid4')
    @patch('futurex_openedx_extensions.helpers.upload.get_storage_dir')
    def test_create_success(self, mocked_storage_dir, mocked_uuid4):
        """Verify that the view returns the correct response"""
        self.set_action('list')
        self.login_user(3)
        mocked_storage_dir.return_value = self.fake_storage_dir
        mocked_uuid4.return_value = Mock(hex='12345678abcdef12')
        test_file = SimpleUploadedFile('test.png', b'file_content', content_type='image/png')
        data = {
            'file': test_file,
            'slug': 'test-slug',
            'tenant_id': 1
        }
        expected_storage_path = f'{self.fake_storage_dir}/test-slug-12345678.png'
        response = self.client.post(self.url, data, format='multipart')
        created_asset = TenantAsset.objects.get(slug='test-slug', tenant=1)
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)
        self.assertEqual(response.data['file_url'], default_storage.url(expected_storage_path))
        self.assertEqual(response.data['slug'], 'test-slug')
        self.assertEqual(response.data['updated_by'], 3)
        self.assertEqual(response.data['tenant_id'], 1)
        self.assertEqual(response.data['id'], created_asset.id)
        self.assertTrue(default_storage.exists(expected_storage_path))

        another_file = SimpleUploadedFile('testanother.png', b'file_another_content', content_type='image/png')
        data = {
            'file': another_file,
            'slug': 'test-slug',
            'tenant_id': 1
        }
        mocked_uuid4.return_value = Mock(hex='11223344abcdef12')
        storage_path_file2 = f'{self.fake_storage_dir}/test-slug-11223344.png'
        response = self.client.post(self.url, data, format='multipart')
        self.assertEqual(
            response.data['id'],
            1,
            'Failed, adding another file with existing slug should not create a new db record.'
        )
        self.assertEqual(response.data['file_url'], default_storage.url(storage_path_file2))
        self.assertTrue(default_storage.exists(storage_path_file2))

    def test_create_failure(self):
        """Verify that the view returns 400 for user without access and for invlaid file"""
        self.set_action('list')
        self.login_user(3)
        response = self.client.post(
            self.url,
            data={
                'file': SimpleUploadedFile(
                    'file-with-invalid-extension.invalid', b'file_content', content_type='image/png'
                ),
                'slug': 'does-not-matter',
                'tenant': 1
            },
            format='multipart'
        )
        self.assertEqual(
            response.status_code,
            http_status.HTTP_400_BAD_REQUEST,
            'Failed, 400 response is expected as file type is invalid.'
        )
        self.assertEqual(
            str(response.data['file'][0]),
            f'Invalid file type. Allowed types are {ALLOWED_FILE_EXTENSIONS}.'
        )

        data = {
            'file': SimpleUploadedFile('abcd.png', b'does not matter', content_type='image/png'),
            'slug': 'does-not-matter',
            'tenant_id': 3
        }
        response = self.client.post(self.url, data, format='multipart')
        self.assertEqual(
            response.status_code,
            http_status.HTTP_400_BAD_REQUEST,
            'Failed, 400 response is expected as user does not have tenant access'
        )
        self.assertEqual(str(response.data['tenant_id'][0]), 'User does not have have required access for tenant (3).')

    @patch('futurex_openedx_extensions.helpers.upload.get_storage_dir')
    def test_list_success(self, mocked_storage_dir):
        """Verify that user can only view accessible tenant assets"""
        self.set_action('list')
        mocked_storage_dir.return_value = self.fake_storage_dir
        tenant1_sample1 = TenantAsset.objects.create(
            slug='tenant1-sample1',
            tenant_id=1,
            file=SimpleUploadedFile('sample11.png', b'dumy11', content_type='image/png'),
            updated_by_id=3
        )
        tenant1_sample2 = TenantAsset.objects.create(
            slug='tenant1-sample2',
            tenant_id=1,
            file=SimpleUploadedFile('sample12.png', b'dummy12', content_type='image/png'),
            updated_by_id=3
        )
        tenant1_sample3 = TenantAsset.objects.create(
            slug='tenant1-sample3-by-another-user',
            tenant_id=1,
            file=SimpleUploadedFile('sample13.png', b'dummy13', content_type='image/png'),
            updated_by_id=1
        )
        TenantAsset.objects.create(
            slug='tenant4-sample1',
            tenant_id=2,
            file=SimpleUploadedFile('sample41.png', b'dummy41', content_type='image/png'),
            updated_by_id=3
        )
        self.login_user(3)
        response = self.client.get(self.url)
        self.assertEqual(
            len(response.data['results']),
            3,
            'Failed, user should only have access to accessible tenants.',
        )
        self.assertEqual(response.data['results'][0]['id'], tenant1_sample3.id)
        self.assertEqual(response.data['results'][1]['id'], tenant1_sample2.id)
        self.assertEqual(response.data['results'][2]['id'], tenant1_sample1.id)

        tenant1_sample1.slug = '_private-tenant1-sample1'
        tenant1_sample1.save()
        response = self.client.get(self.url)
        self.assertEqual(
            len(response.data['results']),
            2,
            'Private asset records shouldn\'t be accessible by non system-staff users.',
        )

        self.login_user(1)
        response = self.client.get(self.url)
        self.assertEqual(
            len(response.data['results']),
            TenantAsset.objects.count(),
            'System-staff users should have access to all asset records.',
        )

    @patch('futurex_openedx_extensions.helpers.upload.get_storage_dir')
    def test_list_success_template_tenant(self, mocked_storage_dir):
        """Verify that only staff-users can view assets in the template tenant"""
        self.set_action('list')
        mocked_storage_dir.return_value = self.fake_storage_dir
        self.assertFalse(TenantConfig.objects.filter(external_key=settings.FX_TEMPLATE_TENANT_SITE).exists())
        template_tenant = TenantConfig.objects.create(external_key=settings.FX_TEMPLATE_TENANT_SITE)

        self.assertEqual(TenantAsset.objects.count(), 0, 'bad test data, no assets should exist yet')
        TenantAsset.objects.create(
            slug='sample',
            tenant_id=template_tenant.id,
            file=SimpleUploadedFile('sample.png', b'dummy data', content_type='image/png'),
            updated_by_id=self.staff_user,
        )

        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(
            len(response.data['results']),
            1,
            'Failed, staff user should be able to see the asset records in the template tenant!',
        )

    def tearDown(self):
        """Delete created files"""
        if default_storage.exists(self.fake_storage_dir):
            _, files = default_storage.listdir(self.fake_storage_dir)
            for file_name in files:
                default_storage.delete(os.path.join(self.fake_storage_dir, file_name))
            os.rmdir(self.fake_storage_dir)


@ddt.ddt
class TestSetThemePreviewCookieView(APITestCase):
    """Tests for SetThemePreviewCookieView"""
    def setUp(self):
        """Initialize the test case"""
        self.url = reverse('fx_dashboard:set-theme-preview')

    def test_redirect_when_cookie_present(self):
        """Verify that the view redirects if the theme-preview cookie is set to 'yes'."""
        self.client.cookies['theme-preview'] = 'yes'
        response = self.client.get(self.url)
        assert response.status_code == 302, 'Expected redirect when theme-preview cookie is set'

    def test_render_template_when_cookie_absent(self):
        """Verify that the view renders the set_theme_preview.html template if no theme-preview cookie is set."""
        response = self.client.get(self.url)
        assert response.status_code == 200, 'Expected status 200 when theme-preview cookie is not set'
        assert 'set_theme_preview.html' in [t.name for t in response.templates], 'Expected template to be rendered'

    @ddt.data(
        ('/custom-next-url/', '/custom-next-url/'),
        (None, f'http://testserver{reverse("fx_dashboard:set-theme-preview")}')
    )
    @ddt.unpack
    def test_redirect_url_resolves_correctly(self, next_param, expected_redirect):
        """Verify that the view correctly resolves the next URL parameter for redirection."""
        params = {'next': next_param} if next_param else {}
        self.client.cookies['theme-preview'] = 'yes'
        response = self.client.get(self.url, params)
        assert response.url == expected_redirect, f'Expected redirect to {expected_redirect}'


@pytest.mark.usefixtures('base_data')
@ddt.ddt
class TestLearnerUnenrollView(BaseTestViewMixin):
    """Tests for LearnerUnenrollView"""
    VIEW_NAME = 'fx_dashboard:learner-unenroll'

    def setUp(self):
        """Setup"""
        super().setUp()
        self.staff_user = 2
        # Create test enrollment (using a course that exists in base_data)
        self.test_user = get_user_model().objects.get(id=10)
        self.test_course_id = 'course-v1:ORG1+2+2'
        self.enrollment = CourseEnrollment.objects.create(
            user=self.test_user,
            course_id=self.test_course_id,
            is_active=True
        )

    def test_unauthorized(self):
        """Test unauthorized access"""
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_invalid_request_missing_user_identifier(self):
        """Test request with missing user identifier"""
        self.login_user(self.staff_user)
        data = {
            'course_id': self.test_course_id,
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['reason'], 'Invalid request data')
        # Serializer errors are in 'details' key
        self.assertIn('detail', response.data.get('details', {}))

    def test_invalid_request_missing_course_id(self):
        """Test request with missing course_id"""
        self.login_user(self.staff_user)
        data = {
            'username': self.test_user.username,
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['reason'], 'Invalid request data')
        # Serializer errors are in 'details' key
        self.assertIn('detail', response.data.get('details', {}))

    def test_invalid_request_multiple_user_identifiers(self):
        """Test request with multiple user identifiers"""
        self.login_user(self.staff_user)
        data = {
            'user_id': self.test_user.id,
            'username': self.test_user.username,
            'course_id': self.test_course_id,
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['reason'], 'Invalid request data')
        # Serializer errors are in 'details' key
        self.assertIn('detail', response.data.get('details', {}))

    @ddt.data('user_id', 'username', 'email')
    def test_successful_unenroll_with_different_identifiers(self, identifier_type):
        """Test successful unenrollment using different user identifiers"""
        self.login_user(self.staff_user)
        data = {
            'course_id': self.test_course_id,
        }
        if identifier_type == 'user_id':
            data['user_id'] = self.test_user.id
        elif identifier_type == 'username':
            data['username'] = self.test_user.username
        else:  # email
            data['email'] = self.test_user.email

        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIn('Successfully unenrolled', response.data['message'])
        self.assertEqual(response.data['user_id'], self.test_user.id)
        self.assertEqual(response.data['username'], self.test_user.username)
        self.assertEqual(response.data['course_id'], self.test_course_id)

        # Verify enrollment is inactive
        self.enrollment.refresh_from_db()
        self.assertFalse(self.enrollment.is_active)

    def test_unenroll_with_reason(self):
        """Test unenrollment with a reason provided"""
        self.login_user(self.staff_user)
        data = {
            'username': self.test_user.username,
            'course_id': self.test_course_id,
            'reason': 'Student requested withdrawal'
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertTrue(response.data['success'])

    def test_unenroll_user_not_found(self):
        """Test unenrollment when user doesn't exist"""
        self.login_user(self.staff_user)
        data = {
            'username': 'nonexistent_user',
            'course_id': self.test_course_id,
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        # Error from unenroll() method is caught and put in reason
        self.assertTrue(
            'User not found' in response.data['reason'] or
            'nonexistent_user' in response.data['reason']
        )

    def test_unenroll_course_not_found(self):
        """Test unenrollment when course doesn't exist"""
        self.login_user(self.staff_user)
        data = {
            'username': self.test_user.username,
            'course_id': 'course-v1:ORG1+999+999',
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        # Course validation error is caught during is_valid()
        self.assertEqual(response.data['reason'], 'Invalid request data')
        self.assertIn('detail', response.data.get('details', {}))

    def test_unenroll_invalid_course_id_format(self):
        """Test unenrollment with invalid course ID format"""
        self.login_user(self.staff_user)
        data = {
            'username': self.test_user.username,
            'course_id': 'invalid-course-id',
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        # Course validation error is caught during is_valid()
        self.assertEqual(response.data['reason'], 'Invalid request data')
        self.assertIn('detail', response.data.get('details', {}))

    def test_unenroll_user_not_enrolled(self):
        """Test unenrollment when user is not enrolled in the course"""
        self.login_user(self.staff_user)
        # Use a different course that user is not enrolled in
        data = {
            'username': self.test_user.username,
            'course_id': 'course-v1:ORG1+3+3',  # Different from self.test_course_id (which is ORG1+2+2)
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertIn('not enrolled', response.data['reason'])

    def test_unenroll_already_unenrolled(self):
        """Test unenrollment when user is already unenrolled"""
        self.login_user(self.staff_user)
        # First unenroll
        self.enrollment.is_active = False
        self.enrollment.save()

        data = {
            'username': self.test_user.username,
            'course_id': self.test_course_id,
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        # Error from unenroll() method
        self.assertIn('already unenrolled', response.data['reason'])

    def test_unenroll_invalid_course_id_format_no_org(self):
        """Test unenrollment with course ID that has no org"""
        self.login_user(self.staff_user)
        data = {
            'username': self.test_user.username,
            'course_id': 'course-v1:+1+1',  # Missing org
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        # Course validation error caught during is_valid()
        self.assertEqual(response.data['reason'], 'Invalid request data')
        self.assertIn('detail', response.data.get('details', {}))

    def test_view_has_correct_permissions(self):
        """Test that the view has correct permission classes"""
        view = views.LearnerUnenrollView()
        self.assertIn(FXHasTenantCourseAccess, view.permission_classes)

    def test_view_configuration(self):
        """Test view configuration"""
        view = views.LearnerUnenrollView()
        self.assertEqual(view.fx_view_name, 'learner_unenroll')
        self.assertEqual(view.fx_default_read_only_roles, [])
        self.assertEqual(view.fx_view_description, 'api/fx/learners/v1/unenroll: Unenroll a learner from a course')

    def test_unenroll_permission_denied_for_course_org(self):
        """Test permission denied when user doesn't have access to course org"""
        self.login_user(self.staff_user)

        # Create enrollment for a course the user doesn't have access to
        test_course = 'course-v1:ORG1+3+3'
        CourseEnrollment.objects.create(
            user=self.test_user,
            course_id=test_course,
            is_active=True
        )

        # Patch the post method to modify fx_permission_info before processing
        original_post = views.LearnerUnenrollView.post

        def patched_post(view_self, request, *args, **kwargs):
            # Modify fx_permission_info to exclude ORG1
            request.fx_permission_info['view_allowed_full_access_orgs'] = [
                'org2', 'org3', 'org8', 'org4', 'org5'  # org1 excluded
            ]
            return original_post(view_self, request, *args, **kwargs)

        with patch.object(views.LearnerUnenrollView, 'post', patched_post):
            data = {
                'username': self.test_user.username,
                'course_id': test_course,  # ORG1 not in allowed list
            }
            response = self.client.post(self.url, data, format='json')
            self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)
            self.assertIn(
                'You do not have permission to unenroll learners from this course',
                response.data['reason']
            )

    def test_unenroll_generic_exception(self):
        """Test generic exception handling during unenrollment"""
        self.login_user(self.staff_user)

        # Patch the unenroll method of the serializer to raise a generic exception
        # that's not DRFValidationError or FXCodedException
        with patch(
            'futurex_openedx_extensions.dashboard.serializers.LearnerUnenrollSerializer.unenroll'
        ) as mock_unenroll:
            mock_unenroll.side_effect = RuntimeError('Unexpected database error')

            data = {
                'username': self.test_user.username,
                'course_id': self.test_course_id,
            }
            response = self.client.post(self.url, data, format='json')
            self.assertEqual(response.status_code, http_status.HTTP_500_INTERNAL_SERVER_ERROR)
            self.assertIn('An error occurred during unenrollment', response.data['reason'])
            # Verify the exception was logged
            mock_unenroll.assert_called_once()

    def test_unenroll_fx_coded_exception(self):
        """Test FXCodedException handling during unenrollment"""
        self.login_user(self.staff_user)

        # Patch the unenroll method to raise FXCodedException
        with patch(
            'futurex_openedx_extensions.dashboard.serializers.LearnerUnenrollSerializer.unenroll'
        ) as mock_unenroll:
            mock_unenroll.side_effect = FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message='Invalid enrollment data'
            )

            data = {
                'username': self.test_user.username,
                'course_id': self.test_course_id,
            }
            response = self.client.post(self.url, data, format='json')
            self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
            self.assertIn('Invalid enrollment data', response.data['reason'])
