"""
ADR 0009 addendum F2, rule B: a tenant, course or user id taken from a request BODY or query is checked against the
caller's FULL-access reach before anything is created or changed, and an id out of reach reads exactly like one that
does not exist. One bad id in a list refuses the whole request.
"""
# pylint: disable=duplicate-code
from unittest.mock import patch

import ddt
import pytest
from common.djangoapps.student.models import CourseAccessRole
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status as http_status

from futurex_openedx_extensions.helpers.models import ViewAllowedRoles
from futurex_openedx_extensions.helpers.roles import cache_refresh_course_access_roles
from tests.test_dashboard.test_mixins import BaseTestViewMixin

TENANT1_STAFF = 3  # org-wide staff of Org1 (tenant 1)
PARTIAL_ACCESS = 11  # instructor of the single course ORG3+2+2 (tenant 2), nothing else
OTHER_TENANT = 2  # exists, out of TENANT1_STAFF's reach
MISSING_TENANT = 999  # does not exist
USER11_COURSE = 'course-v1:ORG3+2+2'


def allow_writes(view_name, *roles):
    """Register the roles for writes on a view through the roles table (the way an operator does)"""
    for role in roles:
        ViewAllowedRoles.objects.update_or_create(
            view_name=view_name, allowed_role=role, defaults={'allow_write': True},
        )
    cache.clear()


@pytest.mark.usefixtures('base_data')
@ddt.ddt
class TestCreateTenantInBody(BaseTestViewMixin):
    """Course and library creation: the body tenant_id must be inside the caller's full-access reach"""

    def setUp(self):
        """Staff and instructor may write on both views"""
        super().setUp()
        allow_writes('courses_list', 'staff', 'instructor')
        allow_writes('libraries_list', 'staff', 'instructor')
        # both tenants fully configured, so only the caller's reach can refuse tenant 2
        for target, value in (
            ('get_all_tenants_info', {'default_org_per_tenant': {1: 'org1', 2: 'org3'}}),
            ('get_org_to_tenant_map', {'org1': [1], 'org3': [2]}),
        ):
            patcher = patch(f'futurex_openedx_extensions.dashboard.serializers.{target}', return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def _body(tenant_id):
        """A complete, otherwise valid, creation body"""
        return {'tenant_id': tenant_id, 'number': '77', 'run': '1', 'display_name': 'x'}

    @ddt.data('fx_dashboard:courses', 'fx_dashboard:libraries')
    def test_out_of_reach_and_missing_tenant_give_one_identical_400(self, view_name):
        """Another tenant and a non-existent one answer with the same status and the same error on tenant_id"""
        self.login_user(TENANT1_STAFF)
        with patch('futurex_openedx_extensions.dashboard.serializers.modulestore') as store:
            other = self.client.post(reverse(view_name), self._body(OTHER_TENANT))
            missing = self.client.post(reverse(view_name), self._body(MISSING_TENANT))
        assert other.status_code == missing.status_code == http_status.HTTP_400_BAD_REQUEST
        assert list(other.json()['errors']) == list(missing.json()['errors']) == ['tenant_id']
        assert other.json()['errors']['tenant_id'][0].replace('2', 'N') == \
            missing.json()['errors']['tenant_id'][0].replace('999', 'N')
        store.assert_not_called()  # nothing was created

    @ddt.data('fx_dashboard:courses', 'fx_dashboard:libraries')
    def test_course_level_access_is_not_enough_to_create(self, view_name):
        """A course-level instructor of tenant 2 cannot create in tenant 2: creating needs FULL access"""
        self.login_user(PARTIAL_ACCESS)
        with patch('futurex_openedx_extensions.dashboard.serializers.modulestore') as store:
            response = self.client.post(reverse(view_name), self._body(OTHER_TENANT))
        assert response.status_code == http_status.HTTP_400_BAD_REQUEST
        assert list(response.json()['errors']) == ['tenant_id']
        store.assert_not_called()

    def test_own_tenant_still_creates_a_library(self):
        """The same call for the caller's own tenant reaches the creation"""
        self.login_user(TENANT1_STAFF)
        response = self.client.post(reverse('fx_dashboard:libraries'), self._body(1))
        assert response.status_code == http_status.HTTP_201_CREATED

    def test_system_staff_creates_in_any_tenant(self):
        """System staff reach is every tenant"""
        self.login_user(self.staff_user)
        response = self.client.post(reverse('fx_dashboard:libraries'), self._body(OTHER_TENANT))
        assert response.status_code == http_status.HTTP_201_CREATED


@pytest.mark.usefixtures('base_data')
class TestCourseCategoriesTenantReach(BaseTestViewMixin):
    """Course categories live in the tenant's config: a course-level grant elsewhere cannot write them"""

    def setUp(self):
        """User 11: org-wide staff in tenant 1, course-level staff in tenant 2"""
        super().setUp()
        CourseAccessRole.objects.create(user_id=PARTIAL_ACCESS, role='staff', org='org1')
        CourseAccessRole.objects.create(user_id=PARTIAL_ACCESS, role='staff', org='org3', course_id=USER11_COURSE)
        cache_refresh_course_access_roles(PARTIAL_ACCESS)
        allow_writes('course_categories', 'staff')

    def test_course_of_a_partially_reached_tenant_reads_like_a_missing_course(self):
        """The course is inside the caller's course scope, but its tenant is not fully reachable: 404, no write"""
        self.login_user(PARTIAL_ACCESS)
        url = reverse('fx_dashboard:courses-course-categories', args=[USER11_COURSE])
        with patch('futurex_openedx_extensions.dashboard.views.categories.CourseCategories') as manager:
            partial = self.client.put(url, {'categories': []}, format='json')
            missing = self.client.put(
                reverse('fx_dashboard:courses-course-categories', args=['course-v1:ORG3+99+99']),
                {'categories': []}, format='json',
            )
        assert partial.status_code == missing.status_code == http_status.HTTP_404_NOT_FOUND
        assert partial.data['reason'].replace(USER11_COURSE, 'C') == missing.data['reason'].replace(
            'course-v1:ORG3+99+99', 'C',
        )
        manager.assert_not_called()


@pytest.mark.usefixtures('base_data')
class TestUrlTenantNeedsFullAccess(BaseTestViewMixin):
    """The draft config of a tenant named in the URL needs full access to that tenant"""

    def setUp(self):
        """User 11: org-wide staff in tenant 1, course-level staff in tenant 2"""
        super().setUp()
        CourseAccessRole.objects.create(user_id=PARTIAL_ACCESS, role='staff', org='org1')
        CourseAccessRole.objects.create(user_id=PARTIAL_ACCESS, role='staff', org='org3', course_id=USER11_COURSE)
        cache_refresh_course_access_roles(PARTIAL_ACCESS)
        allow_writes('theme_config_draft', 'staff')

    def test_partially_reached_tenant_is_refused_for_every_method(self):
        """GET, PUT and DELETE on tenant 2 are 403, exactly like a tenant the caller has nothing in"""
        self.login_user(PARTIAL_ACCESS)
        url = reverse('fx_dashboard:theme-config-draft', args=[2])
        for call in (self.client.get, self.client.delete):
            assert call(url).status_code == http_status.HTTP_403_FORBIDDEN
        assert self.client.put(url, {'key': 'a', 'reset': True}, format='json').status_code == \
            http_status.HTTP_403_FORBIDDEN
        assert self.client.get(reverse('fx_dashboard:theme-config-draft', args=[1])).status_code == \
            http_status.HTTP_200_OK


@pytest.mark.usefixtures('base_data')
class TestRoleWritesNameOnlyReachableTenants(BaseTestViewMixin):
    """user_roles POST and DELETE: one tenant out of reach refuses the whole request"""
    BASE = '/api/fx/roles/v1/user_roles/'

    def setUp(self):
        """Staff may write on the roles view; the caller also holds a course-level staff role in tenant 2"""
        super().setUp()
        allow_writes('user_roles', 'staff')
        CourseAccessRole.objects.create(user_id=TENANT1_STAFF, role='staff', org='org3', course_id=USER11_COURSE)
        cache_refresh_course_access_roles(TENANT1_STAFF)
        self.login_user(TENANT1_STAFF)

    def test_post_with_one_foreign_tenant_in_the_list_changes_nothing(self):
        """tenant_ids=[1, 2]: the caller reaches 1 only, so the request is refused as a whole"""
        before = CourseAccessRole.objects.count()
        with patch('futurex_openedx_extensions.dashboard.views.roles.add_course_access_roles') as add:
            response = self.client.post(
                self.BASE, {'tenant_ids': [1, OTHER_TENANT], 'users': ['user6'], 'role': 'instructor',
                            'tenant_wide': 1}, format='json',
            )
            missing = self.client.post(
                self.BASE, {'tenant_ids': [1, MISSING_TENANT], 'users': ['user6'], 'role': 'instructor',
                            'tenant_wide': 1}, format='json',
            )
        assert response.status_code == missing.status_code == http_status.HTTP_403_FORBIDDEN
        add.assert_not_called()
        assert CourseAccessRole.objects.count() == before

    def test_delete_with_one_foreign_tenant_in_the_query_is_refused(self):
        """tenant_ids=1,2 on DELETE is refused before any lookup"""
        with patch('futurex_openedx_extensions.dashboard.views.roles.delete_course_access_roles') as delete:
            response = self.client.delete(f'{self.BASE}user9/?tenant_ids=1,2')
        assert response.status_code == http_status.HTTP_403_FORBIDDEN
        delete.assert_not_called()
