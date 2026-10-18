"""
Object-level scope tests (ADR 0009): a course or user named in the URL, query or body is checked against the caller's
reach before anything is read or changed, and a foreign id answers exactly like a non-existent one.
"""
# pylint: disable=duplicate-code
import csv
from unittest.mock import patch

import ddt
import pytest
from common.djangoapps.student.models import CourseAccessRole, CourseEnrollment
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core.cache import cache
from django.db.models import Q
from django.urls import reverse
from eox_tenant.models import TenantConfig
from rest_framework import status as http_status

from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.export_csv import export_data_to_csv
from futurex_openedx_extensions.helpers.models import DataExportTask, ViewAllowedRoles
from tests.test_dashboard.test_mixins import BaseTestViewMixin

OWN_COURSE = 'course-v1:ORG1+5+5'  # tenant 1, 7 enrolled users
FOREIGN_COURSE = 'course-v1:ORG3+1+1'  # tenant 2, 6 enrolled users
SIBLING_COURSE = 'course-v1:ORG3+3+3'  # tenant 2, same org as user 11's only course
USER11_COURSE = 'course-v1:ORG3+2+2'  # the only course user 11 (course-level instructor, tenant 2) can reach
MISSING_COURSE = 'course-v1:ORG3+99+99'  # does not exist, in a real org
MISSING_ORG_COURSE = 'course-v1:NOSUCHORG+1+1'  # does not exist, in no org
TENANT1_STAFF = 3  # org-wide staff of Org1 (tenant 1)
PARTIAL_ACCESS = 11  # instructor of ORG3+2+2 only
SYSTEM_STAFF = 2
IN_SCOPE_LEARNER = 5  # signed up in tenant 1, not staff
FOREIGN_LEARNER = 44  # signed up and enrolled in tenant 2 only


def _real_user_lookup(user_key):
    """The platform lookup (a fake that always fails in the test mocks), by username or email"""
    return get_user_model().objects.get(Q(username=user_key) | Q(email=user_key))


def _allow_staff_writes(view_name):
    """Register the staff role for writes on a view, through the existing roles table"""
    ViewAllowedRoles.objects.update_or_create(view_name=view_name, allowed_role='staff', defaults={'allow_write': True})
    cache.clear()


def _same(first, second):
    """Status, body and the headers that matter are identical"""
    return first.status_code == second.status_code and first.data == second.data


@pytest.mark.usefixtures('base_data')
@ddt.ddt
class TestLearnersByCourseScope(BaseTestViewMixin):
    """F1: `learners/v1/learners/<course-id>/` and its export only ever serve courses inside the caller's scope"""
    VIEW_NAME = 'fx_dashboard:learners-course'

    def _get(self, user_id, course_id, **params):
        """Login and call the course route"""
        self.login_user(user_id)
        return self.client.get(reverse(self.view_name, args=[course_id]), data=params)

    def test_own_course_is_served(self):
        """The caller's own course lists its learners, the same rows the system staff sees"""
        response = self._get(TENANT1_STAFF, OWN_COURSE)
        assert response.status_code == http_status.HTTP_200_OK
        assert response.data['count'] == 3
        assert response.data == self._get(SYSTEM_STAFF, OWN_COURSE).data

    def test_system_staff_reaches_any_course(self):
        """The scope widens for system staff, so the foreign course below really holds learners"""
        assert self._get(SYSTEM_STAFF, FOREIGN_COURSE).data['count'] > 0

    @ddt.data(FOREIGN_COURSE, SIBLING_COURSE, 'course-v1:ORG6+1+1')
    def test_foreign_course_is_empty_and_identical_to_a_missing_one(self, course_id):
        """A course of another tenant (or of an org in no tenant) answers exactly like a non-existent course"""
        foreign = self._get(TENANT1_STAFF, course_id)
        missing = self._get(TENANT1_STAFF, MISSING_COURSE)
        assert foreign.status_code == http_status.HTTP_200_OK
        assert foreign.data['count'] == 0 and foreign.data['results'] == []
        assert _same(foreign, missing)
        assert _same(foreign, self._get(TENANT1_STAFF, MISSING_ORG_COURSE))

    @ddt.data(
        {'include_staff': '1'}, {'search_text': 'user'}, {'tenant_ids': '1'}, {'page_size': '100', 'page': '1'},
        {'omit_subsection_name': '1'},
    )
    def test_no_parameter_widens_the_scope(self, params):
        """Other query parameters cannot reach a foreign course"""
        response = self._get(TENANT1_STAFF, FOREIGN_COURSE, **params)
        assert response.status_code == http_status.HTTP_200_OK
        assert response.data['count'] == 0

    def test_foreign_tenant_in_the_query_is_a_tenant_refusal(self):
        """Naming a tenant the caller is not granted stays a 403, the role/tenant gate"""
        response = self._get(TENANT1_STAFF, FOREIGN_COURSE, tenant_ids='2')
        assert response.status_code == http_status.HTTP_403_FORBIDDEN

    def test_key_variants_do_not_slip_through(self):
        """A lower-cased key of a foreign course does not match anything the caller may see"""
        response = self._get(TENANT1_STAFF, FOREIGN_COURSE.lower())
        assert response.status_code == http_status.HTTP_200_OK
        assert response.data['count'] == 0

    def test_partial_access_caller_is_limited_to_its_course(self):
        """A course-level instructor reaches that course only, not its siblings in the same org and tenant"""
        assert self._get(PARTIAL_ACCESS, USER11_COURSE).data['count'] > 0
        sibling = self._get(PARTIAL_ACCESS, SIBLING_COURSE)
        assert sibling.status_code == http_status.HTTP_200_OK
        assert sibling.data['count'] == 0
        assert _same(sibling, self._get(PARTIAL_ACCESS, MISSING_COURSE))
        assert self._get(PARTIAL_ACCESS, OWN_COURSE).data['count'] == 0

    def test_other_errors_of_the_query_are_not_swallowed(self):
        """Only the out-of-scope answer becomes an empty list: any other failure stays loud (no silent fallback)"""
        self.login_user(TENANT1_STAFF)
        failure = FXCodedException(FXExceptionCodes.INVALID_INPUT, 'broken')
        with patch(
            'futurex_openedx_extensions.dashboard.views.learners.get_learners_by_course_queryset',
            side_effect=failure,
        ):
            response = self.client.get(reverse(self.view_name, args=[OWN_COURSE]))
        assert response.status_code >= http_status.HTTP_400_BAD_REQUEST

    def test_counts_never_include_out_of_scope_rows(self):
        """The foreign course's learners are not counted for the caller, in any shape"""
        learners = self._get(TENANT1_STAFF, FOREIGN_COURSE, page_size='100')
        assert learners.data['count'] == 0
        assert learners.data['next'] is None

    # ---- the CSV export: the request, and the replay inside the task ----

    def _start_export(self, user_id, course_id):
        """Start the export, capturing what is handed to the async task"""
        self.login_user(user_id)
        with patch('futurex_openedx_extensions.helpers.export_mixins.export_data_to_csv_task') as task, \
                patch('futurex_openedx_extensions.helpers.export_mixins.log_export_task'), \
                patch('django.core.handlers.wsgi.WSGIRequest.site', Site.objects.first(), create=True):
            response = self.client.get(
                reverse(self.view_name, args=[course_id]), data={'download': 'csv', 'tenant_ids': '1'},
            )
        return response, task.delay.call_args

    def test_export_request_of_a_foreign_course_is_identical_to_a_missing_one(self):
        """The export request does not tell a foreign course from a non-existent one"""
        foreign, _ = self._start_export(TENANT1_STAFF, FOREIGN_COURSE)
        missing, _ = self._start_export(TENANT1_STAFF, MISSING_COURSE)
        assert foreign.status_code == missing.status_code == http_status.HTTP_200_OK
        assert foreign.data.keys() == missing.data.keys()
        assert DataExportTask.objects.filter(user_id=TENANT1_STAFF).count() == 2

    @staticmethod
    def _replay(call_args):
        """Run the export task body for real with what the request handed over, return the CSV rows"""
        task_id, view_url, view_data, fx_permission_info, filename = call_args.args
        view_data['site_domain'] = Site.objects.first().domain
        written = {}

        def keep(local_path, *_args, **_kwargs):
            """Read the file the task would have uploaded"""
            with open(local_path, encoding='utf-8', newline='') as handle:
                written['rows'] = list(csv.DictReader(handle))

        with patch('futurex_openedx_extensions.helpers.export_csv._upload_file_to_storage', side_effect=keep):
            export_data_to_csv(task_id, view_url, view_data, fx_permission_info, filename)
        return written.get('rows', [])

    def test_export_replay_reapplies_the_requesters_scope(self):
        """The task re-runs the view with the requester's own permission info: own course has rows, foreign none"""
        _, own_call = self._start_export(TENANT1_STAFF, OWN_COURSE)
        _, foreign_call = self._start_export(TENANT1_STAFF, FOREIGN_COURSE)
        assert len(self._replay(own_call)) == 3
        assert self._replay(foreign_call) == []

    def test_export_task_is_the_requesters_own(self):
        """The task record belongs to the requester and carries their user id only"""
        _, call = self._start_export(TENANT1_STAFF, FOREIGN_COURSE)
        assert call.args[3]['user_id'] == TENANT1_STAFF
        assert DataExportTask.objects.get(id=call.args[0]).user_id == TENANT1_STAFF


@pytest.mark.usefixtures('base_data')
@ddt.ddt
class TestUserKeyScope(BaseTestViewMixin):
    """A user named in the URL answers 404 with one message, whether foreign, unknown, inactive or ambiguous"""

    def setUp(self):
        """Use a real username/email lookup"""
        super().setUp()
        patcher = patch('futurex_openedx_extensions.helpers.users.get_user_by_username_or_email', _real_user_lookup)
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _user(user_id):
        """The user row"""
        return get_user_model().objects.get(id=user_id)

    @ddt.data('fx_dashboard:learner-info', 'fx_dashboard:learner-courses')
    def test_foreign_unknown_and_inactive_are_indistinguishable(self, view_name):
        """Username and email of a foreign user, an unknown key and a foreign inactive user give the same 404"""
        foreign = self._user(FOREIGN_LEARNER)
        inactive = self._user(61)
        assert not inactive.is_active
        self.login_user(TENANT1_STAFF)
        missing = self.client.get(reverse(view_name, args=['no_such_user_xyz']))
        assert missing.status_code == http_status.HTTP_404_NOT_FOUND
        for key in (foreign.username, foreign.email, inactive.username, inactive.email):
            response = self.client.get(reverse(view_name, args=[key]))
            assert _same(response, missing), key
            assert foreign.username not in str(response.data) or key == foreign.username

    def test_an_inactive_user_inside_the_scope_is_reported_inactive(self):
        """Only after the scope check does the caller learn that its own learner is inactive"""
        user = self._user(IN_SCOPE_LEARNER)
        user.is_active = False
        user.save()
        self.login_user(TENANT1_STAFF)
        response = self.client.get(reverse('fx_dashboard:learner-info', args=[user.username]))
        assert response.status_code == http_status.HTTP_400_BAD_REQUEST
        assert 'not active' in response.data['reason']

    def test_own_learner_is_served(self):
        """A learner of the caller's tenant is served as before"""
        self.login_user(TENANT1_STAFF)
        response = self.client.get(reverse('fx_dashboard:learner-info', args=[self._user(IN_SCOPE_LEARNER).username]))
        assert response.status_code == http_status.HTTP_200_OK


@pytest.mark.usefixtures('base_data')
@ddt.ddt
class TestListFiltersScope(BaseTestViewMixin):
    """course_ids / user_ids / usernames on the list views are intersected with the caller's reach"""

    @ddt.data(
        'fx_dashboard:learners-enrollements', 'fx_dashboard:courses-feedback',
    )
    def test_foreign_course_ids_return_nothing_and_look_like_missing_ones(self, view_name):
        """A foreign course_ids value returns no row, exactly like a non-existent course"""
        self.login_user(TENANT1_STAFF)
        url = reverse(view_name)
        foreign = self.client.get(url, data={'course_ids': FOREIGN_COURSE})
        missing = self.client.get(url, data={'course_ids': MISSING_COURSE})
        assert foreign.status_code == http_status.HTTP_200_OK
        assert foreign.data['count'] == 0
        assert _same(foreign, missing)

    def test_mixed_course_ids_keep_only_the_callers_own(self):
        """Own and foreign course ids together: only the own course's rows come back"""
        self.login_user(TENANT1_STAFF)
        url = reverse('fx_dashboard:learners-enrollements')
        own = self.client.get(url, data={'course_ids': OWN_COURSE, 'page_size': 100}).data
        mixed = self.client.get(url, data={'course_ids': f'{OWN_COURSE},{FOREIGN_COURSE}', 'page_size': 100}).data
        assert own['count'] > 0
        assert mixed['count'] == own['count']
        assert {row['course_id'] for row in mixed['results']} == {OWN_COURSE}

    @ddt.data('user_ids', 'usernames')
    def test_foreign_users_are_not_listed(self, parameter):
        """Naming learners of another tenant lists none of their enrollments"""
        self.login_user(TENANT1_STAFF)
        foreign = self._user_value(FOREIGN_LEARNER, parameter)
        response = self.client.get(reverse('fx_dashboard:learners-enrollements'), data={parameter: foreign})
        assert response.status_code == http_status.HTTP_200_OK
        assert response.data['count'] == 0

    @staticmethod
    def _user_value(user_id, parameter):
        """The id or username of a user"""
        user = get_user_model().objects.get(id=user_id)
        return user.id if parameter == 'user_ids' else user.username

    def test_partial_access_caller_cannot_list_a_sibling_course(self):
        """A course-level role lists its own course's enrollments only"""
        self.login_user(PARTIAL_ACCESS)
        url = reverse('fx_dashboard:learners-enrollements')
        sibling = self.client.get(url, data={'course_ids': SIBLING_COURSE})
        assert sibling.data['count'] == 0
        assert self.client.get(url, data={'course_ids': USER11_COURSE}).data['count'] > 0


@pytest.mark.usefixtures('base_data')
class TestUnenrollScope(BaseTestViewMixin):
    """The unenroll body (user_key, course_id) is scoped, and its errors never identify a user"""
    VIEW_NAME = 'fx_dashboard:learners-unenroll'

    def setUp(self):
        """Real user lookup, and the staff role registered for writes on this view"""
        super().setUp()
        patcher = patch('futurex_openedx_extensions.helpers.users.get_user_by_username_or_email', _real_user_lookup)
        patcher.start()
        self.addCleanup(patcher.stop)
        _allow_staff_writes('learner_unenroll')

    def _post(self, user_id, user_key, course_id):
        """Login and unenroll"""
        self.login_user(user_id)
        return self.client.post(self.url, {'user_key': user_key, 'course_id': course_id}, format='json')

    def test_foreign_course_is_refused_like_a_missing_one(self):
        """A course outside the scope answers 403, like a non-existent course"""
        user = get_user_model().objects.get(id=FOREIGN_LEARNER)
        foreign = self._post(TENANT1_STAFF, user.username, FOREIGN_COURSE)
        missing = self._post(TENANT1_STAFF, user.username, MISSING_COURSE)
        assert foreign.status_code == missing.status_code == http_status.HTTP_403_FORBIDDEN
        assert foreign.data == missing.data
        assert CourseEnrollment.objects.get(user=user, course_id=FOREIGN_COURSE).is_active

    def test_user_errors_do_not_identify_anyone(self):
        """Unknown key, and a real user not enrolled here, answer identically and never carry the username"""
        stranger = get_user_model().objects.get(id=FOREIGN_LEARNER)  # exists, not enrolled in OWN_COURSE
        unknown = self._post(TENANT1_STAFF, 'no_such_user_xyz', OWN_COURSE)
        not_enrolled = self._post(TENANT1_STAFF, stranger.email, OWN_COURSE)
        assert unknown.status_code == not_enrolled.status_code == http_status.HTTP_400_BAD_REQUEST
        assert str(unknown.data) == str(not_enrolled.data)
        assert stranger.username not in str(not_enrolled.data) and stranger.email not in str(not_enrolled.data)

    def test_own_learner_is_unenrolled(self):
        """The normal case still works"""
        user = get_user_model().objects.get(id=15)
        response = self._post(TENANT1_STAFF, user.username, OWN_COURSE)
        assert response.status_code == http_status.HTTP_200_OK
        assert not CourseEnrollment.objects.get(user=user, course_id=OWN_COURSE).is_active


@pytest.mark.usefixtures('base_data')
@ddt.ddt
class TestCourseWritesScope(BaseTestViewMixin):
    """Course writes by path: foreign and non-existent courses give the same 404"""

    def setUp(self):
        """Register the staff role for writes on both views"""
        super().setUp()
        _allow_staff_writes('course_categories')
        _allow_staff_writes('course_certificates')

    @ddt.data(
        ('fx_dashboard:courses-course-categories', {'categories': []}),
        ('fx_dashboard:courses-course-certificates', {'enabled': True}),
    )
    @ddt.unpack
    def test_foreign_course_is_404_like_a_missing_one(self, view_name, body):
        """PUT on a course outside the scope"""
        self.login_user(TENANT1_STAFF)
        foreign = self.client.put(reverse(view_name, args=[FOREIGN_COURSE]), body, format='json')
        missing = self.client.put(reverse(view_name, args=[MISSING_COURSE]), body, format='json')
        assert foreign.status_code == http_status.HTTP_404_NOT_FOUND
        assert foreign.data['reason'].replace(FOREIGN_COURSE, '') == missing.data['reason'].replace(MISSING_COURSE, '')


@pytest.mark.usefixtures('base_data')
class TestExportTaskScope(BaseTestViewMixin):
    """An export task id is reachable by its owner only"""
    VIEW_NAME = 'fx_dashboard:data-export-tasks-list'

    @staticmethod
    def _task(user_id):
        """A task of the given user"""
        return DataExportTask.objects.create(
            filename='x.csv', view_name='learners_list', user_id=user_id, tenant=TenantConfig.objects.get(id=1),
        )

    def test_other_users_task_is_a_plain_404(self):
        """Read and patch of somebody else's task answer like a non-existent id"""
        task = self._task(SYSTEM_STAFF)
        self.login_user(TENANT1_STAFF)
        detail = 'fx_dashboard:data-export-tasks-detail'
        other = self.client.get(reverse(detail, args=[task.id]))
        missing = self.client.get(reverse(detail, args=[task.id + 1000]))
        assert other.status_code == http_status.HTTP_404_NOT_FOUND
        assert _same(other, missing)
        patched = self.client.patch(reverse(detail, args=[task.id]), {'notes': 'x'}, format='json')
        assert patched.status_code == http_status.HTTP_404_NOT_FOUND
        task.refresh_from_db()
        assert task.notes == ''

    def test_list_holds_only_the_callers_tasks(self):
        """Tasks of other users never appear in a list"""
        self._task(SYSTEM_STAFF)
        mine = self._task(TENANT1_STAFF)
        self.login_user(TENANT1_STAFF)
        response = self.client.get(self.url)
        assert [row['id'] for row in response.data['results']] == [mine.id]


@pytest.mark.usefixtures('base_data')
class TestUserRolesScope(BaseTestViewMixin):
    """
    The roles API names a user in the path to GRANT roles, so a user is looked up globally by design (ADR 0009
    exception, documented). What is scoped is the authority: reading, changing and deleting roles only ever reach
    the caller's own tenants.
    """
    BASE = '/api/fx/roles/v1/user_roles/'

    def setUp(self):
        """Real user lookup, and the staff role registered on the roles view (read and write)"""
        super().setUp()
        patcher = patch('futurex_openedx_extensions.helpers.users.get_user_by_username_or_email', _real_user_lookup)
        patcher.start()
        self.addCleanup(patcher.stop)
        _allow_staff_writes('user_roles')
        self.login_user(TENANT1_STAFF)

    @staticmethod
    def _roles(user_id):
        """The role rows of a user"""
        return sorted(
            (str(role), str(org), str(course_id))
            for role, org, course_id in CourseAccessRole.objects.filter(user_id=user_id).values_list(
                'role', 'org', 'course_id',
            )
        )

    def test_retrieve_foreign_user_is_a_plain_404_like_a_missing_one(self):
        """A user whose roles are all in another tenant is not found, exactly like an unknown username"""
        foreign = self.client.get(f'{self.BASE}user9/', data={'tenant_ids': '1'})
        missing = self.client.get(f'{self.BASE}no_such_user_xyz/', data={'tenant_ids': '1'})
        assert foreign.status_code == missing.status_code == http_status.HTTP_404_NOT_FOUND
        assert foreign.data == missing.data

    def test_update_cannot_change_roles_in_a_foreign_tenant(self):
        """A caller without authority over tenant 2 changes nothing there"""
        before = self._roles(9)
        response = self.client.put(
            f'{self.BASE}user9/', {'tenant_id': 2, 'tenant_roles': ['staff'], 'course_roles': {}}, format='json',
        )
        assert response.status_code == http_status.HTTP_403_FORBIDDEN
        assert self._roles(9) == before

    def test_update_inside_the_callers_tenant_still_works(self):
        """The same call for the caller's own tenant is not blocked by the scope check (it reaches the role logic)"""
        response = self.client.put(
            f'{self.BASE}user9/', {'tenant_id': 1, 'tenant_roles': [], 'course_roles': {}}, format='json',
        )
        assert response.status_code == http_status.HTTP_400_BAD_REQUEST  # empty update, refused by the role logic
        assert 'empty data' in response.data['reason']

    def test_delete_cannot_reach_a_foreign_tenant(self):
        """Naming a tenant the caller is not granted is a tenant refusal, and nothing is deleted"""
        before = self._roles(9)
        response = self.client.delete(f'{self.BASE}user9/?tenant_ids=2')
        assert response.status_code == http_status.HTTP_403_FORBIDDEN
        assert self._roles(9) == before

    def test_create_cannot_grant_in_a_foreign_tenant(self):
        """Granting a role in another tenant is refused, and nothing is created"""
        before = self._roles(6)
        response = self.client.post(
            self.BASE, {'tenant_ids': [2], 'users': ['user6'], 'role': 'instructor', 'tenant_wide': 1}, format='json',
        )
        assert response.status_code == http_status.HTTP_403_FORBIDDEN  # ADR 0009 rule B: the whole request is refused
        assert self._roles(6) == before


@pytest.mark.usefixtures('base_data')
class TestCategoryDetailScope(BaseTestViewMixin):
    """A category lives inside one tenant's config, so the tenant gate is its scope"""

    def test_foreign_tenant_is_a_tenant_refusal(self):
        """Reading, changing or deleting a category of a tenant the caller is not granted is a 403"""
        _allow_staff_writes('category_detail')
        self.login_user(TENANT1_STAFF)
        url = '/api/fx/courses/v1/categories/any_category/'
        assert self.client.get(url, data={'tenant_ids': '2'}).status_code == http_status.HTTP_403_FORBIDDEN
        assert self.client.patch(
            url + '?tenant_ids=2', {'label': 'x'}, format='json',
        ).status_code == http_status.HTTP_403_FORBIDDEN
        assert self.client.delete(url + '?tenant_ids=2').status_code == http_status.HTTP_403_FORBIDDEN


@pytest.mark.usefixtures('base_data')
class TestAccessibleTenantsV2Scope(BaseTestViewMixin):
    """`accessible/v2/info/?username_or_email=` only ever returns tenants the caller reaches itself"""
    VIEW_NAME = 'fx_dashboard:accessible-info-v2'

    def setUp(self):
        """Real user lookup"""
        super().setUp()
        patcher = patch(
            'futurex_openedx_extensions.dashboard.views.admin.get_user_by_username_or_email', _real_user_lookup,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        # the view ships with no default role: it is opened to roles through the roles table
        ViewAllowedRoles.objects.update_or_create(view_name='accessible_info', allowed_role='staff')
        cache.clear()

    def _ask(self, caller, key):
        """Ask for the tenants of a user"""
        self.login_user(caller)
        return self.client.get(self.url, data={'username_or_email': key})

    def test_a_user_with_no_tenant_in_common_looks_like_an_unknown_one(self):
        """User 10 reaches tenants 2 and 3 only: for a tenant-1 caller that is an empty answer, like a missing user"""
        foreign = self._ask(TENANT1_STAFF, 'user10')
        missing = self._ask(TENANT1_STAFF, 'no_such_user_xyz')
        assert foreign.status_code == missing.status_code == http_status.HTTP_200_OK
        assert foreign.json() == missing.json() == {}

    def test_only_shared_tenants_are_returned(self):
        """User 9 reaches tenants 1, 2 and 7: a tenant-1 caller sees tenant 1 only"""
        assert set(self._ask(TENANT1_STAFF, 'user9').json()) == {'1'}

    def test_system_staff_sees_every_tenant_of_the_user(self):
        """The scope widens for system staff, as everywhere else"""
        assert set(self._ask(SYSTEM_STAFF, 'user9').json()) == {'1', '2', '7'}

    @patch('futurex_openedx_extensions.dashboard.views.categories.CourseCategories')
    def test_courses_in_the_body_are_intersected_with_the_scope(self, manager):
        """A foreign course id in a PATCH body is refused exactly like a non-existent one; an own course is kept"""
        _allow_staff_writes('category_detail')
        self.login_user(TENANT1_STAFF)
        url = '/api/fx/courses/v1/categories/any_category/?tenant_ids=1'
        foreign = self.client.patch(url, {'courses': [FOREIGN_COURSE]}, format='json')
        missing = self.client.patch(url, {'courses': ['course-v1:ORG1+99+99']}, format='json')
        assert foreign.status_code == missing.status_code == http_status.HTTP_400_BAD_REQUEST
        assert str(foreign.data['courses'][0]).replace(FOREIGN_COURSE, '') == \
            str(missing.data['courses'][0]).replace('course-v1:ORG1+99+99', '')
        manager.return_value.set_courses_for_category.assert_not_called()

        own = self.client.patch(url, {'courses': [OWN_COURSE]}, format='json')
        assert own.status_code == http_status.HTTP_204_NO_CONTENT
        manager.return_value.set_courses_for_category.assert_called_once()
