"""
ADR 0009 addendum F2, rule W: a write method (anything but GET/HEAD/OPTIONS) passes only through a role whose row on
the view has allow_write. One hostile case per write view: a role that may read but not write gets 403.
"""
# pylint: disable=duplicate-code
import importlib

import ddt
import pytest
from common.djangoapps.student.models import CourseAccessRole
from django.apps import apps
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status as http_status

from futurex_openedx_extensions.helpers.models import ViewAllowedRoles, ViewUserMapping
from futurex_openedx_extensions.helpers.roles import FXViewRoleInfoMixin, cache_refresh_course_access_roles
from tests.test_dashboard.test_mixins import BaseTestViewMixin

STAFF_USER = 3  # org-wide staff of Org1 (tenant 1)
COURSE = 'course-v1:ORG1+5+5'
REFUSAL = 'None of the roles of the user allows writing here'

# (view name, method, url, multipart body?)  one entry per write method of every write view
WRITE_CALLS = [
    ('courses_list', 'post', lambda: reverse('fx_dashboard:courses'), False),
    ('libraries_list', 'post', lambda: reverse('fx_dashboard:libraries'), False),
    ('categories_management', 'post', lambda: reverse('fx_dashboard:courses-categories'), False),
    ('category_detail', 'patch', lambda: '/api/fx/courses/v1/categories/c1/?tenant_ids=1', False),
    ('category_detail', 'delete', lambda: '/api/fx/courses/v1/categories/c1/?tenant_ids=1', False),
    ('categories_order', 'post', lambda: reverse('fx_dashboard:courses-categories-order'), False),
    ('course_categories', 'put', lambda: reverse('fx_dashboard:courses-course-categories', args=[COURSE]), False),
    ('course_certificates', 'put', lambda: reverse('fx_dashboard:courses-course-certificates', args=[COURSE]), False),
    ('theme_config_draft', 'put', lambda: reverse('fx_dashboard:theme-config-draft', args=[1]), False),
    ('theme_config_draft', 'delete', lambda: reverse('fx_dashboard:theme-config-draft', args=[1]), False),
    ('theme_config_publish', 'post', lambda: reverse('fx_dashboard:theme-config-publish'), False),
    ('theme_config_tenant', 'post', lambda: reverse('fx_dashboard:theme-config-tenant'), False),
    ('upload_file', 'post', lambda: reverse('fx_dashboard:file-upload'), True),
    ('tenant_assets', 'post', lambda: '/api/fx/assets/v1/tenant_assets/', True),
    ('tenant_assets', 'put', lambda: '/api/fx/assets/v1/tenant_assets/1/', True),
    ('tenant_assets', 'patch', lambda: '/api/fx/assets/v1/tenant_assets/1/', True),
    ('tenant_assets', 'delete', lambda: '/api/fx/assets/v1/tenant_assets/1/', True),
    ('exported_files_data', 'patch', lambda: '/api/fx/export/v1/tasks/1/', False),
    ('learner_unenroll', 'post', lambda: reverse('fx_dashboard:learners-unenroll'), False),
    ('user_roles', 'post', lambda: '/api/fx/roles/v1/user_roles/', False),
    ('user_roles', 'put', lambda: '/api/fx/roles/v1/user_roles/user9/', False),
    ('user_roles', 'delete', lambda: '/api/fx/roles/v1/user_roles/user9/?tenant_ids=1', False),
]


def write_capable_views():
    """
    The dashboard views that change data: {view name: roles allowed to write by default}. Read from the classes, not
    from the metaclass registry, which other tests reset.
    """
    result = {}
    for module_name in ('admin', 'categories', 'configs', 'courses', 'learners', 'misc', 'payments', 'roles'):
        module = importlib.import_module(f'futurex_openedx_extensions.dashboard.views.{module_name}')
        for view_class in vars(module).values():
            if not (isinstance(view_class, type) and issubclass(view_class, FXViewRoleInfoMixin)):
                continue
            writes = any(hasattr(view_class, handler) for handler in view_class.get_write_handlers())
            if view_class.__module__ == module.__name__ and view_class.fx_view_name and writes:
                result[view_class.fx_view_name] = sorted(
                    view_class.fx_default_read_write_roles or view_class.fx_default_read_only_roles
                )
    return result


def set_write_flag(view_name, role, allow_write):
    """Set the flag of one row of the roles table (created if missing) the way an operator would"""
    ViewAllowedRoles.objects.update_or_create(
        view_name=view_name, allowed_role=role, defaults={'allow_write': allow_write},
    )
    cache.clear()


@pytest.mark.usefixtures('base_data')
@ddt.ddt
class TestWriteNeedsAllowWrite(BaseTestViewMixin):
    """A write method needs a role with allow_write on the view; reading never does"""

    def _call(self, method, url, multipart):
        """Issue the call as the tenant-1 staff user"""
        self.login_user(STAFF_USER)
        return getattr(self.client, method)(url, {}, format='multipart' if multipart else 'json')

    @ddt.data(*WRITE_CALLS)
    @ddt.unpack
    def test_read_only_role_cannot_write(self, view_name, method, url, multipart):
        """The staff role is listed on the view but its flag is off: 403 with the write refusal"""
        set_write_flag(view_name, 'staff', False)
        response = self._call(method, url(), multipart)
        assert response.status_code == http_status.HTTP_403_FORBIDDEN
        assert response.json() == {'reason': REFUSAL} or view_name == 'theme_config_tenant', response.content

    @ddt.data(*[case for case in WRITE_CALLS if case[0] != 'theme_config_tenant'])
    @ddt.unpack
    def test_the_same_call_passes_the_gate_when_the_flag_is_on(self, view_name, method, url, multipart):
        """With allow_write on the same row, the call gets past the permission gate (it may fail later, on input)"""
        set_write_flag(view_name, 'staff', True)
        response = self._call(method, url(), multipart)
        assert response.status_code != http_status.HTTP_403_FORBIDDEN or response.json() != {'reason': REFUSAL}

    def test_a_view_without_roles_stays_closed_to_non_system_staff(self):
        """theme_config_tenant lists no role at all: the caller is refused whatever the flags say"""
        response = self._call('post', reverse('fx_dashboard:theme-config-tenant'), False)
        assert response.status_code == http_status.HTTP_403_FORBIDDEN

    def test_reading_does_not_need_the_flag(self):
        """GET on a view whose row has allow_write off still works"""
        set_write_flag('learners_list', 'staff', False)
        self.login_user(STAFF_USER)
        assert self.client.get(reverse('fx_dashboard:learners')).status_code == http_status.HTTP_200_OK

    def test_system_staff_is_not_subject_to_the_flag(self):
        """System staff reach every write; the roles table is for everyone else"""
        set_write_flag('categories_order', 'staff', False)
        self.login_user(self.staff_user)
        response = self.client.post(reverse('fx_dashboard:courses-categories-order'), {}, format='json')
        assert response.status_code == http_status.HTTP_400_BAD_REQUEST  # past the gate, refused on the empty body

    def test_another_role_with_the_flag_is_enough(self):
        """The flag is per role: a caller holding any role with allow_write on the view may write"""
        CourseAccessRole.objects.create(user_id=STAFF_USER, role='instructor', org='org1')
        cache_refresh_course_access_roles(STAFF_USER)
        set_write_flag('categories_order', 'staff', False)
        set_write_flag('categories_order', 'instructor', True)
        response = self._call('post', reverse('fx_dashboard:courses-categories-order'), False)
        assert response.status_code == http_status.HTTP_400_BAD_REQUEST

    def test_a_role_mapped_to_the_user_for_the_view_stays_usable(self):
        """ViewUserMapping is an explicit per-user, per-view grant: it is not filtered by the table flag"""
        set_write_flag('categories_order', 'staff', False)
        CourseAccessRole.objects.create(user_id=STAFF_USER, role='fx_api_access', org='org1')
        cache_refresh_course_access_roles(STAFF_USER)
        ViewUserMapping.objects.create(user_id=STAFF_USER, view_name='categories_order', enabled=True)
        cache.clear()
        response = self._call('post', reverse('fx_dashboard:courses-categories-order'), False)
        assert response.status_code == http_status.HTTP_400_BAD_REQUEST  # past the gate, refused on the empty body


def test_every_write_view_has_a_hostile_case():
    """A new write view fails here until it is added to WRITE_CALLS, so none ships without its hostile test"""
    assert set(write_capable_views()) == {view_name for view_name, *_ in WRITE_CALLS}


def test_the_frozen_map_matches_the_declared_defaults():
    """The migration's frozen map equals what the views declare today (a drift shows up here)"""
    module = importlib.import_module('futurex_openedx_extensions.helpers.migrations.0013_backfill_view_allow_write')
    frozen = {view_name: sorted(roles) for view_name, roles in module.WRITE_ROLES.items()}
    # theme_config_tenant lists no role at all, so there is nothing to backfill for it
    assert {name: roles for name, roles in write_capable_views().items() if roles} == frozen


@pytest.mark.usefixtures('db')
class TestBackfillMigration:
    """Migration 0013: untouched rows of write-capable views get the flag, operator-edited rows are left alone"""

    @staticmethod
    def _run():
        """Run the migration function on the real models"""
        module = importlib.import_module('futurex_openedx_extensions.helpers.migrations.0013_backfill_view_allow_write')
        module.backfill_allow_write(apps, None)

    @staticmethod
    def _flags():
        """(view, role) -> allow_write"""
        return {
            (row.view_name, row.allowed_role): row.allow_write for row in ViewAllowedRoles.objects.all()
        }

    def test_backfill(self):
        """Seeded rows are lifted by declared write roles; edited rows, other roles and read-only views are not"""
        ViewAllowedRoles.objects.bulk_create([  # bulk_create leaves no history: a row the package seeded
            ViewAllowedRoles(view_name='category_detail', allowed_role='staff'),
            ViewAllowedRoles(view_name='category_detail', allowed_role='org_course_creator_group'),
            ViewAllowedRoles(view_name='category_detail', allowed_role='instructor'),  # not a declared writer
            ViewAllowedRoles(view_name='courses_list', allowed_role='data_researcher'),  # listed role, no RW declared
            ViewAllowedRoles(view_name='learners_list', allowed_role='staff'),  # read-only view
        ])
        ViewAllowedRoles.objects.create(view_name='user_roles', allowed_role='org_course_creator_group')  # history

        self._run()

        assert self._flags() == {
            ('category_detail', 'staff'): True,
            ('category_detail', 'org_course_creator_group'): True,
            ('category_detail', 'instructor'): False,
            ('courses_list', 'data_researcher'): True,
            ('learners_list', 'staff'): False,
            ('user_roles', 'org_course_creator_group'): False,  # saved through the ORM: an operator touched it
        }

    def test_backfill_is_idempotent_and_never_lowers(self):
        """A second run changes nothing, and a flag an operator turned on stays on"""
        ViewAllowedRoles.objects.create(view_name='tenant_assets', allowed_role='staff', allow_write=True)
        ViewAllowedRoles.objects.bulk_create([
            ViewAllowedRoles(view_name='tenant_assets', allowed_role='fx_api_access_global'),
        ])
        self._run()
        first = self._flags()
        self._run()
        assert self._flags() == first == {
            ('tenant_assets', 'staff'): True,
            ('tenant_assets', 'fx_api_access_global'): True,
        }
