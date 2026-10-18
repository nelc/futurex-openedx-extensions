"""
ADR 0009 addendum F2, rule 3 (N1) on `roles/v1/user_roles/` POST: a refusal for a user outside the caller's reach looks
exactly like an unknown key and never carries the target's username or email, while the onboarding grant (a user who
holds roles only in another tenant) keeps working.
"""
# pylint: disable=duplicate-code
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status as http_status

from tests.test_dashboard.test_mixins import BaseTestViewMixin
from tests.test_dashboard.test_views.test_views_roles_authority import (
    BASE,
    FOREIGN_USER,
    TENANT1_INSTRUCTOR,
    TENANT1_STAFF,
    _real_user_lookup,
)
from tests.test_dashboard.test_views.test_views_write_scope import allow_writes


@pytest.mark.usefixtures('base_data')
class TestUserRolesPostIsUniform(BaseTestViewMixin):
    """Failures for a key the caller cannot see are one answer, whatever the cause"""

    def setUp(self):
        """Real user lookup; a duplicated email, an inactive foreign user; tenant staff is the caller"""
        super().setUp()
        patcher = patch('futurex_openedx_extensions.helpers.users.get_user_by_username_or_email', _real_user_lookup)
        patcher.start()
        self.addCleanup(patcher.stop)
        allow_writes('user_roles', 'staff')
        for name in ('dup_a', 'dup_b'):
            get_user_model().objects.create(username=name, email='dup@example.test')
        self.foreign = get_user_model().objects.get(id=FOREIGN_USER)
        self.inactive = get_user_model().objects.create(username='gone_x', email='gone_x@example.test', is_active=False)
        self.login_user(TENANT1_STAFF)

    def _post(self, users, role='staff'):
        """POST a tenant-wide role (staff needs system staff, so every existing target is refused)"""
        return self.client.post(
            BASE, {'tenant_ids': [1], 'users': users, 'role': role, 'tenant_wide': 1}, format='json',
        )

    def _failed(self, key, role='staff'):
        """The one failed entry of a single-key POST"""
        response = self._post([key], role)
        assert response.status_code == http_status.HTTP_201_CREATED
        failed = response.json()['failed']
        assert len(failed) == 1
        return failed[0], response.content.decode()

    def test_unknown_foreign_and_unreachable_keys_fail_identically(self):
        """By username: unknown, existing foreign, inactive foreign and ambiguous give the same entry"""
        shape = {
            key: self._failed(key)[0]
            for key in ('no_such_user_xyz', f'user{FOREIGN_USER}', 'gone_x', 'dup@example.test')
        }
        for key, entry in shape.items():
            assert entry == {
                'user_id': None,
                'username': key,
                'email': key,
                'reason_code': shape['no_such_user_xyz']['reason_code'],
                'reason_message': f'User with username/email ({key}) does not exist!',
            }

    def test_numeric_ids_fail_identically_and_never_echo_the_target(self):
        """By id: an unknown id and a real foreign id give the same entry, and the real identity is not in the body"""
        unknown, _ = self._failed(999999)
        foreign, raw = self._failed(FOREIGN_USER)
        assert unknown['reason_code'] == foreign['reason_code']
        assert foreign == {
            'user_id': FOREIGN_USER,
            'username': None,
            'email': None,
            'reason_code': unknown['reason_code'],
            'reason_message': f'User with ID ({FOREIGN_USER}) does not exist!',
        }
        assert self.foreign.username not in raw and self.foreign.email not in raw
        assert unknown == {**foreign, 'user_id': 999999, 'reason_message': 'User with ID (999999) does not exist!'}

    def test_inactive_and_ambiguous_users_by_id_do_not_leak_the_cause(self):
        """An inactive account read by id says it does not exist, not that it is inactive"""
        entry, raw = self._failed(self.inactive.id)
        assert entry['reason_message'] == f'User with ID ({self.inactive.id}) does not exist!'
        assert 'inactive' not in raw and 'not active' not in raw and self.inactive.email not in raw

    def test_a_user_the_caller_can_see_keeps_the_detailed_failure(self):
        """The caller already sees this user in its own tenant, so the real reason (and the name) stay useful"""
        entry, _ = self._failed(TENANT1_INSTRUCTOR)
        assert entry['username'] == f'user{TENANT1_INSTRUCTOR}'
        assert 'system-staff or superuser' in entry['reason_message']

    def test_onboarding_a_user_of_another_tenant_still_works(self):
        """The grant itself is the feature: a user holding roles only in tenant 2 gets the role in tenant 1"""
        response = self._post([FOREIGN_USER], role='data_researcher')
        assert response.status_code == http_status.HTTP_201_CREATED
        body = response.json()
        assert body['failed'] == [] and body['added'] + body['updated'] == [FOREIGN_USER]
