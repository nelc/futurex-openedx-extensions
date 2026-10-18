"""Test views for the dashboard app - pending course invitations"""
# pylint: disable=duplicate-code,too-many-public-methods
import json
import logging
import re
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from pathlib import Path
from unittest.mock import patch

import ddt
import pytest
from cms.djangoapps.course_creators.models import CourseCreator
from common.djangoapps.student.models import CourseAccessRole, CourseEnrollment, CourseEnrollmentAllowed
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from opaque_keys.edx.locator import CourseLocator
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from organizations.models import Organization
from rest_framework import status as http_status

from futurex_openedx_extensions.dashboard.details.invitations import (
    get_invitation_flags,
    parse_bool_param,
    parse_datetime_param,
)
from futurex_openedx_extensions.dashboard.views.learners import PendingInvitationsView
from futurex_openedx_extensions.helpers.exceptions import FXCodedException
from futurex_openedx_extensions.helpers.models import ViewAllowedRoles
from futurex_openedx_extensions.helpers.permissions import FXHasTenantCourseAccess
from tests.test_dashboard.test_mixins import BaseTestViewMixin
from tests.test_helpers.test_course_creator_manager import _add_clear_org_to_course_creator

LOGGER_NAME = 'futurex_openedx_extensions.pending_invitations_access'
CANARY = 'canary-xyz@example.test'

COURSE_T1 = 'course-v1:ORG1+2+2'  # tenant 1
COURSE_T1_B = 'course-v1:ORG2+1+1'  # tenant 1, another org
COURSE_T2 = 'course-v1:ORG3+1+1'  # tenant 2
COURSE_NO_TENANT = 'course-v1:ORG6+1+1'  # an org in no tenant
KEYS = {'id', 'course_id', 'org', 'email', 'auto_enroll', 'created', 'has_account', 'enrolled'}


def _invite(course_id, email, created=None, user=None, auto_enroll=False):
    """Create one invitation, with a controlled created time"""
    row = CourseEnrollmentAllowed.objects.create(
        email=email, course_id=CourseLocator.from_string(course_id), user=user, auto_enroll=auto_enroll,
    )
    CourseEnrollmentAllowed.objects.filter(id=row.id).update(created=created)
    return row


@pytest.mark.usefixtures('base_data')
@ddt.ddt
class TestPendingInvitationsView(BaseTestViewMixin):
    """Tests for PendingInvitationsView"""
    VIEW_NAME = 'fx_dashboard:pending-invitations'

    def setUp(self):
        """Seed one invitation per interesting course"""
        super().setUp()
        self.base_time = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
        self.in_tenant = _invite(COURSE_T1, 'in-tenant@example.test', self.base_time)
        self.in_tenant_b = _invite(COURSE_T1_B, 'in-tenant-b@example.test', self.base_time + timedelta(days=1))
        self.other_tenant = _invite(COURSE_T2, 'other-tenant@example.test', self.base_time)
        self.no_tenant = _invite(COURSE_NO_TENANT, 'no-tenant@example.test', self.base_time)

    @staticmethod
    def _emails(response):
        """The emails of a response, in order"""
        return [row['email'] for row in response.data['results']]

    def _login_and_get(self, user_id=None, **params):
        """Login and call the tenant-wide route"""
        self.login_user(user_id or self.staff_user)
        return self.client.get(self.url, data=params)

    # ---- wiring, roles, permissions (AC5) ----

    def test_view_registration(self):
        """The view is read only, uses the sibling permission class and the four sibling roles"""
        view_class = resolve(self.url)[0].view_class
        assert view_class is PendingInvitationsView
        assert view_class.permission_classes == [FXHasTenantCourseAccess]
        assert view_class.fx_default_read_only_roles == [
            'staff', 'instructor', 'data_researcher', 'org_course_creator_group',
        ]
        assert view_class.fx_view_name == 'pending_invitations'
        course_url = f'{self.url}{COURSE_T1}/'
        assert resolve(course_url)[0].view_class is PendingInvitationsView

    def test_anonymous_denied(self):
        """An anonymous caller gets 403 like the siblings"""
        response = self.client.get(self.url)
        assert response.status_code == http_status.HTTP_403_FORBIDDEN

    @ddt.data('post', 'put', 'patch', 'delete')
    def test_write_verbs_not_allowed(self, verb):
        """Only GET exists"""
        self.login_user(self.staff_user)
        response = getattr(self.client, verb)(self.url)
        assert response.status_code == http_status.HTTP_405_METHOD_NOT_ALLOWED

    @ddt.data(
        (3, 'staff', {'in-tenant@example.test'}),  # org-wide staff of Org1
        (48, 'instructor', {'org4@example.test'}),  # org-wide instructor of ORG4
        (10, 'data_researcher', {'other-tenant@example.test', 'org4@example.test'}),  # ORG3 data_researcher, Org4 staff
    )
    @ddt.unpack
    def test_allowed_roles(self, user_id, role, expected_emails):
        """Each default role reaches the endpoint, and sees exactly the invitations of its own orgs"""
        assert role in resolve(self.url)[0].view_class.fx_default_read_only_roles
        _invite('course-v1:ORG4+1+1', 'org4@example.test', self.base_time)
        response = self._login_and_get(user_id)
        assert response.status_code == http_status.HTTP_200_OK, response.data
        assert set(self._emails(response)) == expected_emails

    @staticmethod
    def _grant_course_creator(user_id=20, org='ORG1'):
        """
        Give a user the org-wide `org_course_creator_group` role (the shared fixtures grant it no org access). The
        role is only valid with a granted course-creator record that lists the org.
        """
        CourseCreator.objects.bulk_create([  # bulk_create: the model's save() is blocked in this package's tests
            CourseCreator(user_id=user_id, all_organizations=False, state=CourseCreator.GRANTED),
        ])
        creator = CourseCreator.objects.get(user_id=user_id)
        _add_clear_org_to_course_creator(creator, Organization.objects.create(short_name=org))
        CourseAccessRole.objects.create(user_id=user_id, role='org_course_creator_group', org=org)
        cache.clear()

    def test_org_course_creator_group_is_a_live_caller(self):
        """The fourth default role reaches the endpoint and sees exactly the invitations of its own org"""
        self._grant_course_creator()
        response = self._login_and_get(20, tenant_ids='1')
        assert response.status_code == http_status.HTTP_200_OK, response.data
        assert set(self._emails(response)) == {'in-tenant@example.test'}

    @ddt.data(
        (3, '1', 'staff'), (48, '3', 'instructor'), (10, '2', 'data_researcher'),
        (20, '1', 'org_course_creator_group'),
    )
    @ddt.unpack
    def test_export_role_matrix(self, user_id, tenant_id, role):
        """Each default role can start the CSV export, and the task carries the requester's own user id"""
        if role == 'org_course_creator_group':
            self._grant_course_creator()
        self.login_user(user_id)
        with patch('futurex_openedx_extensions.helpers.export_mixins.export_data_to_csv_task') as task, \
                patch('futurex_openedx_extensions.helpers.export_mixins.log_export_task'), \
                patch('django.core.handlers.wsgi.WSGIRequest.site', Site.objects.first(), create=True):
            response = self.client.get(self.url, data={'download': 'csv', 'tenant_ids': tenant_id})
        assert response.status_code == http_status.HTTP_200_OK, (role, response.data)
        assert 'export_task_id' in response.data
        assert task.delay.call_args.args[3]['user_id'] == user_id
        assert task.delay.call_args.args[3]['view_allowed_tenant_ids_any_access'] == [int(tenant_id)]

    def test_export_denied_without_a_role(self):
        """No role of the set, no export (and no task)"""
        self.login_user(20)
        response = self.client.get(self.url, data={'download': 'csv', 'tenant_ids': '1'})
        assert response.status_code == http_status.HTTP_403_FORBIDDEN

    def test_export_of_a_foreign_tenant_is_refused(self):
        """Naming a tenant the caller is not granted is refused for the export too"""
        self.login_user(3)
        response = self.client.get(self.url, data={'download': 'csv', 'tenant_ids': '2'})
        assert response.status_code == http_status.HTTP_403_FORBIDDEN

    def test_role_outside_the_set_denied(self):
        """A user holding no role of the set is denied"""
        response = self._login_and_get(20)
        assert response.status_code == http_status.HTTP_403_FORBIDDEN

    def test_role_changes_at_runtime(self):
        """Removing / adding a role in the existing roles table takes effect (user 48 is instructor of ORG4 only)"""
        assert self._login_and_get(48).status_code == http_status.HTTP_200_OK
        ViewAllowedRoles.objects.filter(view_name='pending_invitations', allowed_role='instructor').delete()
        cache.clear()
        assert self._login_and_get(48).status_code == http_status.HTTP_403_FORBIDDEN
        ViewAllowedRoles.objects.create(
            view_name='pending_invitations', view_description='x', allowed_role='instructor',
        )
        cache.clear()
        assert self._login_and_get(48).status_code == http_status.HTTP_200_OK

    # ---- AC1 tenant isolation, AC8 ----

    def test_tenant_wide_returns_only_caller_tenant(self):
        """Foreign tenant and no-tenant invitations never appear"""
        response = self._login_and_get(4, tenant_ids='1')
        assert response.status_code == http_status.HTTP_200_OK
        assert set(self._emails(response)) == {'in-tenant@example.test', 'in-tenant-b@example.test'}

    def test_system_staff_with_tenant_filter(self):
        """tenant_ids narrows the orgs, it never widens them"""
        response = self._login_and_get(tenant_ids='1')
        assert set(self._emails(response)) == {'in-tenant@example.test', 'in-tenant-b@example.test'}
        response = self._login_and_get(tenant_ids='2')
        assert self._emails(response) == ['other-tenant@example.test']

    def test_foreign_tenant_id_denied(self):
        """A tenant the caller has no role in is refused like the siblings"""
        response = self._login_and_get(4, tenant_ids='3')
        assert response.status_code == http_status.HTTP_403_FORBIDDEN

    def test_course_id_param_cannot_widen(self):
        """Naming a foreign course in the query gives nothing"""
        for course_id in (COURSE_T2, COURSE_NO_TENANT):
            response = self._login_and_get(4, tenant_ids='1', course_id=course_id)
            assert response.status_code == http_status.HTTP_200_OK
            assert response.data['count'] == 0

    def test_per_course_route(self):
        """The path form limits to one course"""
        self.login_user(self.staff_user)
        response = self.client.get(f'{self.url}{COURSE_T1}/')
        assert response.status_code == http_status.HTTP_200_OK
        assert self._emails(response) == ['in-tenant@example.test']
        assert response.data['results'][0]['course_id'] == COURSE_T1

    def test_outside_course_equals_missing_course(self):
        """A foreign course and a course that does not exist give the same status and body"""
        self.login_user(4)
        foreign = self.client.get(f'{self.url}{COURSE_T2}/', data={'tenant_ids': '1'})
        missing = self.client.get(f'{self.url}course-v1:ORG1+99+99/', data={'tenant_ids': '1'})
        assert foreign.status_code == missing.status_code == http_status.HTTP_200_OK
        assert foreign.data == missing.data
        assert foreign.data['count'] == 0

    def test_partial_access_sees_only_its_courses(self):
        """A course-level role (no org-wide access) sees only those courses of the org (user 11: ORG3+2+2)"""
        _invite('course-v1:ORG3+2+2', 'his-course@example.test', self.base_time)
        _invite('course-v1:ORG3+3+3', 'not-his-course@example.test', self.base_time)
        response = self._login_and_get(11, tenant_ids='2')
        assert response.status_code == http_status.HTTP_200_OK
        assert self._emails(response) == ['his-course@example.test']

    def test_hidden_course_invitations_are_returned(self):
        """Invitations to a course out of the catalog are the instructor page's content, so they are listed"""
        CourseOverview.objects.filter(id=COURSE_T1).update(catalog_visibility='none')
        response = self._login_and_get(tenant_ids='1')
        assert 'in-tenant@example.test' in self._emails(response)

    def test_path_and_query_course_mismatch(self):
        """Two different courses in one request is an input error"""
        self.login_user(self.staff_user)
        response = self.client.get(f'{self.url}{COURSE_T1}/', data={'course_id': COURSE_T2})
        assert response.status_code == http_status.HTTP_400_BAD_REQUEST
        response = self.client.get(f'{self.url}{COURSE_T1}/', data={'course_id': COURSE_T1})
        assert response.status_code == http_status.HTTP_200_OK

    # ---- AC2 status ----

    def test_default_is_pending_only(self):
        """A linked invitation is excluded by default and included with status=all"""
        linked = _invite(COURSE_T1, 'linked@example.test', self.base_time, user=get_user_model().objects.get(id=5))
        response = self._login_and_get(tenant_ids='1')
        assert linked.email not in self._emails(response)
        response = self._login_and_get(tenant_ids='1', status='pending')
        assert linked.email not in self._emails(response)
        response = self._login_and_get(tenant_ids='1', status='all')
        assert linked.email in self._emails(response)

    def test_bad_status(self):
        """An unknown status is an input error"""
        response = self._login_and_get(status='nope')
        assert response.status_code == http_status.HTTP_400_BAD_REQUEST

    # ---- AC3 fields ----

    def test_exact_fields(self):
        """The key set is fixed; nothing about the person is exposed beyond the email"""
        old = _invite(COURSE_T1, 'old-row@example.test', None, auto_enroll=True)
        response = self._login_and_get(tenant_ids='1')
        for row in response.data['results']:
            assert set(row.keys()) == KEYS
        row = next(item for item in response.data['results'] if item['id'] == old.id)
        assert row['created'] is None
        assert row['org'] == 'ORG1'
        assert row['auto_enroll'] is True
        assert row['course_id'] == COURSE_T1

    # ---- AC4 pagination / order ----

    def test_envelope_and_page_size(self):
        """The package envelope, default 20, max 100"""
        for index in range(120):
            _invite(COURSE_T1, f'bulk{index}@example.test', self.base_time)
        response = self._login_and_get(tenant_ids='1')
        assert set(response.data) == {'count', 'next', 'previous', 'results', 'num_pages', 'current_page'} or \
            {'count', 'next', 'previous', 'results'} <= set(response.data)
        assert len(response.data['results']) == 20
        response = self._login_and_get(tenant_ids='1', page_size=101)
        assert len(response.data['results']) == 100

    def test_order_newest_first_ties_by_id_nulls_last_stable_across_pages(self):
        """Exact order and no repeat or loss between pages"""
        CourseEnrollmentAllowed.objects.all().delete()
        rows = [
            _invite(COURSE_T1, 'a@example.test', self.base_time),
            _invite(COURSE_T1, 'b@example.test', self.base_time + timedelta(days=2)),
            _invite(COURSE_T1, 'c@example.test', self.base_time),
            _invite(COURSE_T1, 'd@example.test', None),
            _invite(COURSE_T1, 'e@example.test', self.base_time + timedelta(days=2)),
            _invite(COURSE_T1, 'f@example.test', None),
        ]
        expected = [rows[1].id, rows[4].id, rows[0].id, rows[2].id, rows[3].id, rows[5].id]
        first = self._login_and_get(tenant_ids='1')
        assert [row['id'] for row in first.data['results']] == expected
        second = self._login_and_get(tenant_ids='1')
        assert [row['id'] for row in second.data['results']] == expected
        paged = []
        for page in (1, 2, 3):
            paged += [row['id'] for row in self._login_and_get(tenant_ids='1', page=page, page_size=2).data['results']]
        assert paged == expected

    # ---- filters ----

    def test_created_range(self):
        """created_from / created_to are inclusive and validated"""
        response = self._login_and_get(tenant_ids='1', created_from='2026-01-02T00:00:00Z')
        assert self._emails(response) == ['in-tenant-b@example.test']
        response = self._login_and_get(tenant_ids='1', created_to='2026-01-01T00:00:00')
        assert self._emails(response) == ['in-tenant@example.test']
        assert self._login_and_get(created_from='yesterday').status_code == http_status.HTTP_400_BAD_REQUEST
        response = self._login_and_get(created_from='2026-02-01T00:00:00Z', created_to='2026-01-01T00:00:00Z')
        assert response.status_code == http_status.HTTP_400_BAD_REQUEST

    def test_search_prefix_across_courses_contains_inside_one_course(self):
        """A leading-wildcard search is only possible inside one course"""
        response = self._login_and_get(tenant_ids='1', search_text='in-tenant-b')
        assert self._emails(response) == ['in-tenant-b@example.test']
        response = self._login_and_get(tenant_ids='1', search_text='example.test')
        assert response.data['count'] == 0
        self.login_user(self.staff_user)
        response = self.client.get(f'{self.url}{COURSE_T1}/', data={'search_text': 'tenant@exa'})
        assert self._emails(response) == ['in-tenant@example.test']

    def test_bad_course_id_and_dates(self):
        """Invalid input is an error, as in the siblings"""
        assert self._login_and_get(course_id='bad id').status_code == http_status.HTTP_400_BAD_REQUEST

    def test_page_beyond_last(self):
        """A page beyond the last is a 404, as in the siblings"""
        assert self._login_and_get(tenant_ids='1', page=99).status_code == http_status.HTTP_404_NOT_FOUND

    # ---- flags ----

    def test_flags_and_flag_filters(self):
        """has_account / enrolled per row, and their filters need a single course"""
        user = get_user_model().objects.get(id=6)
        member = _invite(COURSE_T1, user.email, self.base_time + timedelta(days=3))
        shouted = _invite(COURSE_T1_B, user.email.upper(), self.base_time + timedelta(days=5))
        stranger = _invite(COURSE_T1, 'stranger@example.test', self.base_time + timedelta(days=2))
        CourseEnrollment.objects.filter(user=user, course_id=COURSE_T1).delete()
        CourseEnrollment.objects.create(user=user, course_id=COURSE_T1, is_active=True)
        other_course = _invite(COURSE_T1_B, user.email, self.base_time + timedelta(days=4))

        response = self._login_and_get(tenant_ids='1')
        rows = {row['id']: row for row in response.data['results']}
        assert (rows[member.id]['has_account'], rows[member.id]['enrolled']) == (True, True)
        assert (rows[stranger.id]['has_account'], rows[stranger.id]['enrolled']) == (False, False)
        # an account that is NOT enrolled in the course of THIS row
        assert (rows[other_course.id]['has_account'], rows[other_course.id]['enrolled']) == (True, False)
        # the account is found whatever the case of the invited email
        assert (rows[shouted.id]['has_account'], rows[shouted.id]['enrolled']) == (True, False)

        CourseEnrollment.objects.filter(user=user, course_id=COURSE_T1).update(is_active=False)
        rows = {row['id']: row for row in self._login_and_get(tenant_ids='1').data['results']}
        assert rows[member.id]['enrolled'] is False

        self.login_user(self.staff_user)
        url = f'{self.url}{COURSE_T1}/'
        assert self._emails(self.client.get(url, data={'has_account': '1'})) == [member.email]
        assert 'stranger@example.test' in self._emails(self.client.get(url, data={'has_account': '0'}))
        assert member.email not in self._emails(self.client.get(url, data={'has_account': '0'}))
        assert self._emails(self.client.get(url, data={'enrolled': '1'})) == []
        assert member.email in self._emails(self.client.get(url, data={'enrolled': '0'}))
        CourseEnrollment.objects.filter(user=user, course_id=COURSE_T1).update(is_active=True)
        assert self._emails(self.client.get(url, data={'enrolled': '1'})) == [member.email]

        for param in ('has_account', 'enrolled'):
            assert self.client.get(self.url, data={param: '1'}).status_code == http_status.HTTP_400_BAD_REQUEST
        assert self.client.get(url, data={'enrolled': 'maybe'}).status_code == http_status.HTTP_400_BAD_REQUEST

    def test_flag_queries_do_not_grow_with_page_size(self):
        """The flags cost the same number of queries for 2 rows and for 50"""
        def count_queries(size):
            self.login_user(self.staff_user)
            with CaptureQueriesContext(connection) as context:
                response = self.client.get(self.url, data={'page_size': size})
            assert response.status_code == http_status.HTTP_200_OK
            return len(context)

        count_queries(2)  # warm the caches (tenants, roles) first
        small = count_queries(2)
        for index in range(60):
            _invite(COURSE_T1, f'q{index}@example.test', self.base_time)
        assert count_queries(50) == small

    # ---- AC5 access log ----

    def test_access_log_on_list(self):
        """One record per list call, with the contract fields and no invitee value"""
        _invite(COURSE_T1, CANARY, self.base_time)
        with self.assertLogs(LOGGER_NAME, level=logging.INFO) as captured:
            response = self._login_and_get(tenant_ids='1', search_text=CANARY)
        assert response.status_code == http_status.HTTP_200_OK
        assert len(captured.records) == 1
        line = captured.records[0].getMessage()
        assert f'user_id={self.staff_user}' in line
        assert 'tenant_ids=[1]' in line
        assert 'course_id=None' in line
        assert 'search_text=present' in line
        assert 'count=1' in line
        assert 'export=False' in line
        self._assert_no_canary(captured.records)

    def test_access_log_per_course_and_absent_search(self):
        """The per-course route logs its course and a missing search as absent"""
        self.login_user(self.staff_user)
        with self.assertLogs(LOGGER_NAME, level=logging.INFO) as captured:
            self.client.get(f'{self.url}{COURSE_T1}/')
        assert len(captured.records) == 1
        line = captured.records[0].getMessage()
        assert f'course_id={COURSE_T1}' in line
        assert 'search_text=absent' in line

    def test_access_log_on_export(self):
        """An export request leaves one record flagged as export, and the response is the task answer"""
        _invite(COURSE_T1, CANARY, self.base_time)
        self.login_user(self.staff_user)
        started = {'success': 'Task initiated successfully with id: 1', 'export_task_id': 1}
        with patch(
            'futurex_openedx_extensions.helpers.export_mixins.ExportCSVMixin.generate_csv_url_response',
            return_value=started,
        ):
            with self.assertLogs(LOGGER_NAME, level=logging.INFO) as captured:
                response = self.client.get(self.url, data={'download': 'csv', 'tenant_ids': '1', 'search_text': CANARY})
        assert response.status_code == http_status.HTTP_200_OK, response.data
        assert 'export_task_id' in response.data
        assert len(captured.records) == 1
        line = captured.records[0].getMessage()
        assert 'export=True' in line
        assert 'count=None' in line
        self._assert_no_canary(captured.records)

    def test_refused_export_leaves_no_record(self):
        """An export refused (here: too many running tasks) exposes nothing, so nothing is logged"""
        self.login_user(self.staff_user)
        with patch(
            'futurex_openedx_extensions.helpers.export_mixins.ExportCSVMixin.get_existing_incompleted_task_count',
            return_value=1000,
        ), self.assertNoLogs(LOGGER_NAME, level=logging.INFO):
            response = self.client.get(self.url, data={'download': 'csv', 'tenant_ids': '1'})
        assert response.status_code == http_status.HTTP_429_TOO_MANY_REQUESTS

    def test_no_access_record_without_data(self):
        """Denied, invalid and refused calls expose no rows, so they leave no access record"""
        with self.assertNoLogs(LOGGER_NAME, level=logging.INFO):
            self.client.get(self.url)  # anonymous
            self._login_and_get(20)  # no role
            self._login_and_get(status='nope')  # bad input

    def test_canary_never_in_any_logger_output(self):
        """The invitee email is not in ANY log output of a list call, an error, or an export request"""
        _invite(COURSE_T1, CANARY, self.base_time)
        with self.assertLogs(level=logging.DEBUG) as captured:
            logging.getLogger('futurex_openedx_extensions').debug('keep assertLogs happy')
            self._login_and_get(tenant_ids='1', search_text=CANARY)
            self._login_and_get(search_text=CANARY, status='bad')
        self._assert_no_canary(captured.records)

    @staticmethod
    def _assert_no_canary(records):
        """No record carries the canary, in the message, the arguments or the extras"""
        for record in records:
            assert CANARY not in record.getMessage()
            assert CANARY not in repr(record.__dict__)

    # ---- AC6 regression: the learners list does not know about invitations ----

    def test_learners_responses_equal_the_pre_change_snapshot(self):
        """
        The learners list, the course learners and the learner courses are byte-identical (timestamps aside) to what
        the code before this endpoint returned for the same seed, with a pile of invitations present.
        """
        for index in range(30):
            _invite(COURSE_T1, f'snap{index}@example.test', self.base_time)
        for user in get_user_model().objects.all()[:20]:
            _invite(COURSE_T1_B, user.email, self.base_time)
        self.login_user(self.staff_user)
        learners = reverse('fx_dashboard:learners')
        responses = {
            'learners-t1': self.client.get(learners, data={'tenant_ids': '1', 'page_size': 100}),
            'learners-t2': self.client.get(learners, data={'tenant_ids': '2', 'page_size': 100}),
            'learners-all-p1': self.client.get(learners, data={'page_size': 100}),
            'learners-course': self.client.get(
                reverse('fx_dashboard:learners-course', args=['course-v1:ORG1+5+5']), data={'page_size': 100},
            ),
            'learner-courses': self.client.get(reverse('fx_dashboard:learner-courses', args=['user15'])),
        }
        current = json.dumps({key: response.json() for key, response in responses.items()}, indent=1, sort_keys=True)
        current = re.sub(r'"\d{4}-\d\d-\d\dT[\d:.]+(Z|[+-]\d\d:\d\d)"', '"<ts>"', current)
        expected = (Path(__file__).parent / 'snapshots' / 'learners_before_pending_invitations.json').read_text()
        assert current.strip() == expected.strip()

    def test_learners_list_unchanged_by_invitations(self):
        """Seeding invitations changes neither the learners list nor its count"""
        url = self.url.replace('pending_invitations/', 'learners/')
        self.login_user(self.staff_user)
        before = self.client.get(url).json()
        CourseEnrollmentAllowed.objects.all().delete()
        for index in range(30):
            _invite(COURSE_T1, f'extra{index}@example.test', self.base_time)
        for user in get_user_model().objects.all()[:10]:
            _invite(COURSE_T1_B, user.email, self.base_time)
        after = self.client.get(url).json()
        assert before == after
        assert all('example.test' not in str(row.get('email')) for row in after['results'])


def test_parse_bool_param():
    """1 / 0 / absent"""
    assert parse_bool_param('x', None) is None
    assert parse_bool_param('x', '') is None
    assert parse_bool_param('x', '1') is True
    assert parse_bool_param('x', '0') is False
    with pytest.raises(FXCodedException):
        parse_bool_param('x', 'yes')


def test_parse_datetime_param():
    """Aware, naive (taken as UTC), absent and invalid values"""
    assert parse_datetime_param('x', None) is None
    assert parse_datetime_param('x', '2026-01-01T00:00:00') == datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
    assert parse_datetime_param('x', '2026-01-01T02:00:00+02:00') == datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
    with pytest.raises(FXCodedException):
        parse_datetime_param('x', 'tomorrow')


@pytest.mark.django_db
def test_flags_of_an_empty_page():
    """No rows, no queries"""
    with CaptureQueriesContext(connection) as context:
        assert get_invitation_flags([]) == {'accounts': set(), 'enrolled': set()}
    assert len(context) == 0


def test_get_related_id():
    """The related id is the course of the path form, and nothing for the tenant-wide route"""
    view = PendingInvitationsView()
    view.kwargs = {'course_id': COURSE_T1}
    assert view.get_related_id() == COURSE_T1
    view.kwargs = {}
    assert view.get_related_id() is None
