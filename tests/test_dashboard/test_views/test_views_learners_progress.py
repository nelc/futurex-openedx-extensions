"""Test views for the dashboard app - bulk course progress of all learners"""
# pylint: disable=duplicate-code
import base64
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from unittest.mock import patch

import ddt
import pytest
from common.djangoapps.student.models import CourseEnrollment
from completion_aggregator.models import Aggregator
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from lms.djangoapps.certificates.models import GeneratedCertificate
from lms.djangoapps.grades.models import PersistentCourseGrade
from opaque_keys.edx.locator import CourseLocator
from rest_framework import status as http_status
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from futurex_openedx_extensions.dashboard.views.learners import LearnerCoursesView, LearnersCoursesProgressView
from futurex_openedx_extensions.helpers.pagination import IdWindowPagination
from futurex_openedx_extensions.helpers.permissions import FXHasTenantCourseAccess
from tests.test_dashboard.test_mixins import BaseTestViewMixin

KEYS = {
    'national_id', 'user_id', 'email', 'course_id', 'date_joined', 'last_login', 'course_score', 'progress',
    'certificate_available', 'certificate_date', 'grade', 'passed',
}
COURSE_ORG1 = 'course-v1:Org1+1+1'  # tenant 1, learner 5
COURSE_ORG1_B = 'course-v1:ORG1+5+5'  # tenant 1, learner 15
COURSE_ORG2 = 'course-v1:ORG2+4+4'  # tenant 1, learner 21
COURSE_ORG3 = 'course-v1:ORG3+1+1'  # tenant 2, learner 40


def _cursor(position):
    """A cursor value as DRF encodes it (base64 of p=<position>)"""
    return base64.b64encode(f'p={position}'.encode()).decode()


def _progress(user_id, course_id, percent, aggregation_name='course'):
    """Store one completion aggregator row"""
    return Aggregator.objects.create(
        user_id=user_id, course_key=CourseLocator.from_string(course_id), aggregation_name=aggregation_name,
        percent=percent,
    )


def _grade(user_id, course_id, percent, letter_grade='', passed_timestamp=None):
    """Store one persisted course grade"""
    return PersistentCourseGrade.objects.create(
        user_id=user_id, course_id=CourseLocator.from_string(course_id), percent_grade=percent,
        letter_grade=letter_grade, passed_timestamp=passed_timestamp,
    )


@pytest.mark.usefixtures('base_data')
@ddt.ddt
class TestLearnersCoursesProgressView(BaseTestViewMixin):
    """Tests for LearnersCoursesProgressView"""
    VIEW_NAME = 'fx_dashboard:learners-courses-progress'

    def setUp(self):
        """Seed progress for four enrollments, and noise that must never show"""
        super().setUp()
        self.passed_at = datetime(2026, 3, 1, tzinfo=dt_timezone.utc)
        _progress(5, COURSE_ORG1, 0.5)
        _progress(15, COURSE_ORG1_B, 1.0)
        _progress(21, COURSE_ORG2, 0.25)
        _progress(40, COURSE_ORG3, 0.75)
        _progress(3, 'course-v1:ORG1+2+2', 0.0)  # zero completion: excluded
        _progress(1, 'course-v1:ORG1+5+5', 0.9, aggregation_name='chapter')  # not the course aggregate: excluded
        _grade(5, COURSE_ORG1, 0.8, letter_grade='Pass', passed_timestamp=self.passed_at)
        _grade(15, COURSE_ORG1_B, 0.3)
        GeneratedCertificate.objects.create(
            user_id=5, course_id=CourseLocator.from_string(COURSE_ORG1), status='downloadable',
        )
        GeneratedCertificate.objects.create(
            user_id=15, course_id=CourseLocator.from_string(COURSE_ORG1_B), status='notpassing',
        )

    def _rows(self, user_id=None, **params):
        """Login, call the feed and index the rows by (user_id, course_id)"""
        self.login_user(user_id or self.staff_user)
        response = self.client.get(self.url, data=params)
        assert response.status_code == http_status.HTTP_200_OK, response.data
        return {(row['user_id'], row['course_id']): row for row in response.data['results']}

    def test_view_registration(self):
        """The route without a username serves the feed; with a username it is unchanged"""
        view_class = resolve(self.url)[0].view_class
        assert view_class is LearnersCoursesProgressView
        assert view_class.permission_classes == [FXHasTenantCourseAccess]
        assert view_class.pagination_class is IdWindowPagination
        assert view_class.fx_default_read_only_roles == [
            'staff', 'instructor', 'data_researcher', 'org_course_creator_group',
        ]
        per_learner_url = reverse('fx_dashboard:learner-courses', args=['user5'])
        assert resolve(per_learner_url)[0].view_class is LearnerCoursesView

    def test_anonymous_denied(self):
        """An anonymous caller gets 403"""
        assert self.client.get(self.url).status_code == http_status.HTTP_403_FORBIDDEN

    def test_only_enrollments_with_progress(self):
        """Only course-level completion above zero is included"""
        assert set(self._rows()) == {
            (5, COURSE_ORG1), (15, COURSE_ORG1_B), (21, COURSE_ORG2), (40, COURSE_ORG3),
        }

    @patch('futurex_openedx_extensions.dashboard.details.learners.is_learner_certificates_enabled', return_value=True)
    def test_fields(self, _):
        """Every row carries exactly the contract fields, from the stored values"""
        rows = self._rows()
        for row in rows.values():
            assert set(row) == KEYS

        passed = rows[(5, COURSE_ORG1)]
        assert passed['national_id'] == '123456700005'
        assert passed['email'] == 'user5@example.com'
        assert passed['progress'] == 0.5
        assert passed['course_score'] == 0.8
        assert passed['grade'] == 'Pass'
        assert passed['passed'] is True
        assert passed['certificate_available'] is True
        assert passed['certificate_date'] is not None
        assert passed['date_joined'] is not None

        not_passing = rows[(15, COURSE_ORG1_B)]
        assert not_passing['national_id'] is None
        assert not_passing['course_score'] == 0.3
        assert not_passing['grade'] == ''
        assert not_passing['passed'] is False
        assert not_passing['certificate_available'] is False
        assert not_passing['certificate_date'] is None

        never_graded = rows[(21, COURSE_ORG2)]
        assert never_graded['course_score'] is None
        assert never_graded['grade'] is None
        assert never_graded['passed'] is False

    def test_certificates_flag_off(self):
        """With the learner certificates flag off (the default), no certificate is reported"""
        row = self._rows()[(5, COURSE_ORG1)]
        assert row['certificate_available'] is False
        assert row['certificate_date'] is None

    def test_scope(self):
        """An org-wide staff of Org1 sees only the rows of the courses it reaches"""
        rows = self._rows(user_id=3)
        assert (5, COURSE_ORG1) in rows
        assert (40, COURSE_ORG3) not in rows
        assert (21, COURSE_ORG2) not in rows

    def _walk(self, **params):
        """Follow next until it is null, returning every page"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url, data=params)
        pages = []
        while True:
            assert response.status_code == http_status.HTTP_200_OK, response.data
            assert list(response.data) == ['count', 'page', 'next', 'previous', 'results']
            assert response.data['previous'] is None
            assert response.data['page'] == len(pages) + 1
            pages.append([(row['user_id'], row['course_id']) for row in response.data['results']])
            assert response.data['count'] == self._total
            if not response.data['next']:
                assert self._total == sum(len(page) for page in pages)
                return pages
            response = self.client.get(response.data['next'])

    @property
    def _total(self):
        """The rows the walk is expected to return in total: active enrollments with course completion above 0"""
        started = {
            (user_id, str(course_key)) for user_id, course_key in Aggregator.objects.filter(
                aggregation_name='course', percent__gt=0,
            ).values_list('user_id', 'course_key')
        }
        enrollments = CourseEnrollment.objects.filter(is_active=True).values_list('user_id', 'course_id')
        return sum((user_id, str(course_id)) in started for user_id, course_id in enrollments)

    def test_walk_one_window(self):
        """Within one window, a full page continues after its last row, in enrollment id order"""
        pages = self._walk(page_size=1)
        assert [len(page) for page in pages] == [1, 1, 1, 1]
        assert {row for page in pages for row in page} == set(self._rows())

    @ddt.data(1, 3, 50)
    def test_walk_small_windows(self, window_size):
        """With small windows the walk crosses short and empty pages, sees every row once, and ends"""
        with patch.object(IdWindowPagination, 'window_size', window_size):
            pages = self._walk(page_size=2)
        rows = [row for page in pages for row in page]
        assert len(rows) == len(set(rows)) == 4
        assert set(rows) == set(self._rows())
        if window_size == 1:
            assert [] in pages

    def test_walk_ends_at_last_enrollment(self):
        """The last window is the one that reaches the highest enrollment id"""
        top_id = CourseEnrollment.objects.order_by('-id').values_list('id', flat=True).first()
        with patch.object(IdWindowPagination, 'window_size', top_id):
            assert len(self._walk()) == 1
        with patch.object(IdWindowPagination, 'window_size', top_id - 1):
            assert len(self._walk()) == 2

    def test_walk_no_enrollments(self):
        """No enrollment at all: one empty page and no next"""
        CourseEnrollment.objects.all().delete()
        assert self._walk() == [[]]

    def test_count_once_per_walk(self):
        """The total is counted on the call without a cursor only, and the later pages read it from the cursor"""
        with patch(
            'futurex_openedx_extensions.dashboard.views.learners.get_learners_progress_count', return_value=4,
        ) as mock_count:
            pages = self._walk(page_size=1)
        assert len(pages) == 4
        mock_count.assert_called_once()

    def test_count_follows_modified_since(self):
        """The total uses the same filters as the rows"""
        old = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
        Aggregator.objects.update(modified=old)
        PersistentCourseGrade.objects.update(modified=old)
        GeneratedCertificate.objects.update(modified_date=old)
        Aggregator.objects.filter(user_id=21).update(modified=old + timedelta(days=30))
        self.login_user(self.staff_user)
        response = self.client.get(self.url, data={'modified_since': (old + timedelta(days=30)).isoformat()})
        assert response.data['count'] == len(response.data['results']) == 1

    def test_count_no_enrollments(self):
        """No enrollment at all: count 0 on the single page"""
        CourseEnrollment.objects.all().delete()
        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        assert (response.data['count'], response.data['page'], response.data['next']) == (0, 1, None)

    def test_old_cursor_still_walks(self):
        """A cursor issued before count/page existed (a bare id) still walks to the end, with count and page null"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url, data={'cursor': _cursor('0'), 'page_size': 1})
        seen = 0
        while True:
            assert response.status_code == http_status.HTTP_200_OK, response.data
            assert (response.data['count'], response.data['page']) == (None, None)
            seen += len(response.data['results'])
            if not response.data['next']:
                break
            response = self.client.get(response.data['next'])
        assert seen == self._total

    @staticmethod
    def test_paginator_counts_the_queryset_without_a_view_counter():
        """A view that has no get_total_count gets queryset.count()"""
        paginator = IdWindowPagination()
        request = Request(APIRequestFactory().get('/feed/'))
        queryset = CourseEnrollment.objects.filter(id__lte=3).values('id')
        page = paginator.paginate_queryset(queryset, request, view=object())
        assert paginator.total_count == queryset.count() == len(page)
        assert paginator.page_number == 1

    @ddt.data(
        'not-base64!',  # garbage
        'cD1hYmM=',  # p=abc: the position is not a number
        _cursor('5:2'),  # two parts: neither the old nor the new shape
        _cursor('5:2:9:1'),  # four parts
        _cursor('x:2:9'),  # the id part is not a number
        _cursor('5:y:9'),  # the page part is not a number
    )
    def test_invalid_cursor(self, cursor):
        """A cursor that cannot be decoded is a 404, like DRF's own cursor pagination"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url, data={'cursor': cursor})
        assert response.status_code == http_status.HTTP_404_NOT_FOUND

    def test_constant_query_count(self):
        """A page of four rows runs the same number of queries as a page of one row (no per-row query)"""
        self.login_user(self.staff_user)
        self.client.get(self.url)  # warm the per-process caches

        with CaptureQueriesContext(connection) as four_rows:
            response = self.client.get(self.url)
        assert len(response.data['results']) == 4

        Aggregator.objects.exclude(user_id=5).delete()
        with CaptureQueriesContext(connection) as one_row:
            response = self.client.get(self.url)
        assert len(response.data['results']) == 1

        assert len(one_row.captured_queries) == len(four_rows.captured_queries)

    @ddt.data('completion', 'grade', 'certificate')
    def test_modified_since(self, source):
        """Only enrollments with a completion, grade or certificate change at or after the time are returned"""
        old = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
        since = old + timedelta(days=30)
        Aggregator.objects.update(modified=old)
        PersistentCourseGrade.objects.update(modified=old)
        GeneratedCertificate.objects.update(modified_date=old)
        assert not self._rows(modified_since=since.isoformat())

        if source == 'completion':
            Aggregator.objects.filter(user_id=21).update(modified=since)
            expected = (21, COURSE_ORG2)
        elif source == 'grade':
            PersistentCourseGrade.objects.filter(user_id=15).update(modified=since)
            expected = (15, COURSE_ORG1_B)
        else:
            GeneratedCertificate.objects.filter(user_id=5).update(modified_date=since)
            expected = (5, COURSE_ORG1)

        assert set(self._rows(modified_since=since.isoformat())) == {expected}

    def test_modified_since_invalid(self):
        """An unparsable modified_since is a 400"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url, data={'modified_since': 'yesterday'})
        assert response.status_code == http_status.HTTP_400_BAD_REQUEST
