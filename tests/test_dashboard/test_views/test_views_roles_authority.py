"""
ADR 0009 addendum F2, rules R and A on `roles/v1/user_roles/`: a user outside the caller's reach looks exactly like an
unknown one, a caller needs the authority to DROP a role as much as to grant it, a failed update changes nothing, and
nobody changes their own roles.
"""
# pylint: disable=duplicate-code
from unittest.mock import Mock, patch

import pytest
from common.djangoapps.student.models import CourseAccessRole
from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import status as http_status

from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.roles import _dropped_roles_info, _verify_not_self
from tests.test_dashboard.test_mixins import BaseTestViewMixin
from tests.test_dashboard.test_views.test_views_write_scope import allow_writes

TENANT1_STAFF = 3  # tenant-wide staff of Org1 (tenant 1)
TENANT1_INSTRUCTOR = 4  # org-wide instructor of ORG1 and ORG2 (tenant 1), not staff
FOREIGN_USER = 9  # roles in tenant 2 only
BASE = '/api/fx/roles/v1/user_roles/'


def _real_user_lookup(user_key):
    """The platform lookup (a fake that always fails in the test mocks), by username or email"""
    return get_user_model().objects.get(Q(username=user_key) | Q(email=user_key))


def _roles(user_id):
    """The role rows of a user"""
    return sorted(
        (str(role), str(org), str(course_id))
        for role, org, course_id in CourseAccessRole.objects.filter(user_id=user_id).values_list(
            'role', 'org', 'course_id',
        )
    )


@pytest.mark.usefixtures('base_data')
class TestUserRolesAuthority(BaseTestViewMixin):
    """Rule A on PUT and POST, rule R on every username-taking write"""

    def setUp(self):
        """Real user lookup; staff and instructor may write on the roles view (rule W is not what is tested here)"""
        super().setUp()
        patcher = patch('futurex_openedx_extensions.helpers.users.get_user_by_username_or_email', _real_user_lookup)
        patcher.start()
        self.addCleanup(patcher.stop)
        allow_writes('user_roles', 'staff', 'instructor')

    def _put(self, caller, target, body):
        """PUT a role update of a user as another"""
        self.login_user(caller)
        return self.client.put(f'{BASE}user{target}/', body, format='json')

    def test_a_caller_without_authority_cannot_drop_a_tenant_staff_role(self):
        """An org instructor asking for a tenant-wide instructor role used to ERASE the staff user's roles"""
        before = _roles(TENANT1_STAFF)
        response = self._put(
            TENANT1_INSTRUCTOR, TENANT1_STAFF, {'tenant_id': 1, 'tenant_roles': ['instructor'], 'course_roles': {}},
        )
        assert response.status_code == http_status.HTTP_400_BAD_REQUEST
        assert response.data['reason'].startswith('(2001) Permission denied: cannot delete roles of user (user3)')
        assert _roles(TENANT1_STAFF) == before

    def test_a_failed_update_changes_nothing(self):
        """The add of a tenant-wide staff role is refused after the old roles were deleted: all of it is rolled back"""
        before = _roles(TENANT1_INSTRUCTOR)
        response = self._put(
            TENANT1_STAFF, TENANT1_INSTRUCTOR, {'tenant_id': 1, 'tenant_roles': ['staff'], 'course_roles': {}},
        )
        assert response.status_code == http_status.HTTP_400_BAD_REQUEST
        assert 'must be a system-staff or superuser' in response.data['reason']
        assert _roles(TENANT1_INSTRUCTOR) == before

    def test_a_staff_still_manages_the_roles_of_a_user_of_its_tenant(self):
        """The authority check is not a blanket refusal"""
        response = self._put(
            TENANT1_STAFF, TENANT1_INSTRUCTOR,
            {'tenant_id': 1, 'tenant_roles': ['data_researcher'], 'course_roles': {}},
        )
        assert response.status_code == http_status.HTTP_200_OK
        assert ('data_researcher', 'org1', 'None') in _roles(TENANT1_INSTRUCTOR)

    def test_nobody_updates_their_own_roles(self):
        """No self-grant, whatever the caller is allowed to grant others"""
        before = _roles(TENANT1_STAFF)
        response = self._put(
            TENANT1_STAFF, TENANT1_STAFF, {'tenant_id': 1, 'tenant_roles': ['staff', 'instructor'], 'course_roles': {}},
        )
        assert response.status_code == http_status.HTTP_400_BAD_REQUEST
        assert response.data['reason'].startswith('(2007)')
        assert _roles(TENANT1_STAFF) == before

    def test_nobody_grants_themselves_a_role_through_the_user_list(self):
        """POST naming the caller (by username or id) among the users fails for that entry only"""
        self.login_user(TENANT1_STAFF)
        before = _roles(TENANT1_STAFF)
        response = self.client.post(
            BASE,
            {'tenant_ids': [1], 'users': ['user3', TENANT1_STAFF, 'user5'], 'role': 'data_researcher',
             'tenant_wide': 1},
            format='json',
        )
        assert response.status_code == http_status.HTTP_201_CREATED
        failed = response.json()['failed']
        assert len(failed) == 2 and all(item['reason_code'] == FXExceptionCodes.ROLE_CREATE.value for item in failed)
        assert _roles(TENANT1_STAFF) == before


@pytest.mark.parametrize('system_staff', [True, False])
def test_verify_not_self(system_staff):
    """Only system staff may name themselves (nothing to protect: they hold every role)"""
    user = Mock(id=7)
    with patch('futurex_openedx_extensions.helpers.roles.is_system_staff_user', return_value=system_staff):
        if system_staff:
            assert _verify_not_self(user, user, FXExceptionCodes.ROLE_UPDATE) is None
        else:
            with pytest.raises(FXCodedException):
                _verify_not_self(user, user, FXExceptionCodes.ROLE_UPDATE)
        assert _verify_not_self(user, Mock(id=8), FXExceptionCodes.ROLE_UPDATE) is None


def test_dropped_roles_info():
    """What an update drops is described in the shape the delete authority check reads"""
    info = _dropped_roles_info(5, {'tenant_roles': ['staff'], 'course_roles': {'staff': ['c1'], 'instructor': ['c2']}})
    assert info == {
        'staff': {'tenant_ids_full_access': [5], 'tenant_ids': [5]},
        'instructor': {'tenant_ids_full_access': [], 'tenant_ids': [5]},
    }


@pytest.mark.usefixtures('base_data')
class TestUserLookupIsUniform(BaseTestViewMixin):
    """Unknown, ambiguous and out-of-reach users answer the same 404 on every username-taking write"""

    def setUp(self):
        """Real user lookup; two accounts share one email"""
        super().setUp()
        patcher = patch('futurex_openedx_extensions.helpers.users.get_user_by_username_or_email', _real_user_lookup)
        patcher.start()
        self.addCleanup(patcher.stop)
        allow_writes('user_roles', 'staff')
        for name in ('dup_a', 'dup_b'):
            get_user_model().objects.create(username=name, email='dup@example.test')
        self.login_user(TENANT1_STAFF)

    @staticmethod
    def _answers(call):
        """The answer for a missing, an ambiguous and an out-of-reach user"""
        return [
            call(key) for key in ('no_such_user_xyz', 'dup@example.test', f'user{FOREIGN_USER}')
        ]

    def test_put_answers_the_same(self):
        """PUT: same status and body, no lookup message, no name echoed"""
        body = {'tenant_id': 1, 'tenant_roles': ['staff'], 'course_roles': {}}
        answers = self._answers(lambda key: self.client.put(f'{BASE}{key}/', body, format='json'))
        assert {answer.status_code for answer in answers} == {http_status.HTTP_404_NOT_FOUND}
        assert answers[0].data == answers[1].data == answers[2].data == {
            'reason': 'User not found or not permitted.', 'details': {},
        }

    def test_delete_answers_the_same(self):
        """DELETE: same"""
        answers = self._answers(lambda key: self.client.delete(f'{BASE}{key}/?tenant_ids=1'))
        assert {answer.status_code for answer in answers} == {http_status.HTTP_404_NOT_FOUND}
        assert answers[0].data == answers[1].data == answers[2].data

    def test_a_role_holder_of_the_callers_tenant_is_found(self):
        """The same call for a user that holds a role in the caller's tenant gets past the lookup"""
        response = self.client.delete(f'{BASE}user{TENANT1_STAFF + 1}/?tenant_ids=1')
        assert response.status_code != http_status.HTTP_404_NOT_FOUND or 'not permitted' not in response.data['reason']
