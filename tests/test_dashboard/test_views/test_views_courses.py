"""Test views for the dashboard app - courses"""
# pylint: disable=duplicate-code
import json
from unittest.mock import Mock, patch

import ddt
import pytest
from common.djangoapps.student.models import CourseAccessRole
from django.contrib.auth import get_user_model
from django.urls import resolve
from django.utils.functional import SimpleLazyObject
from eox_nelp.course_experience.models import FeedbackCourse
from opaque_keys.edx.locator import CourseLocator, LibraryLocator
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from rest_framework import status as http_status

from futurex_openedx_extensions.helpers.filters import DefaultOrderingFilter
from tests.fixture_helpers import get_all_orgs
from tests.test_dashboard.test_mixins import BaseTestViewMixin


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
        with patch('futurex_openedx_extensions.dashboard.views.courses.get_courses_queryset') as mock_queryset:
            self.client.get(self.url)
            assert mock_queryset.call_args_list[0][1]['fx_permission_info']['view_allowed_full_access_orgs'] \
                   == get_all_orgs()
            assert mock_queryset.call_args_list[0][1]['search_text'] is None
            assert mock_queryset.call_args_list[0][1]['visible_filter'] is None

    def test_list_search(self):
        """Verify that the view filters the courses by search text"""
        self.login_user(self.staff_user)
        with patch('futurex_openedx_extensions.dashboard.views.courses.get_courses_queryset') as mock_queryset:
            self.client.get(self.url + '?tenant_ids=1&search_text=course')
            assert mock_queryset.call_args_list[0][1]['fx_permission_info']['view_allowed_tenant_ids_any_access'] == [1]
            assert mock_queryset.call_args_list[0][1]['search_text'] == 'course'
            assert mock_queryset.call_args_list[0][1]['visible_filter'] is None

    def test_list_visible_courses_only(self):
        """Verify that visible_courses_only=1 restricts the list to catalog-visible courses"""
        self.login_user(self.staff_user)
        with patch('futurex_openedx_extensions.dashboard.views.courses.get_courses_queryset') as mock_queryset:
            self.client.get(self.url + '?visible_courses_only=1')
            assert mock_queryset.call_args_list[0][1]['visible_filter'] is True

    def test_list_include_staff_parsing(self):
        """Verify that include_staff is enabled only by an explicit 1, since the string '0' is truthy in python"""
        self.login_user(self.staff_user)
        for value, expected in (('1', True), ('0', False), ('false', False)):
            with patch('futurex_openedx_extensions.dashboard.views.courses.get_courses_queryset') as mock_queryset:
                self.client.get(self.url + f'?include_staff={value}')
                assert mock_queryset.call_args_list[0][1]['include_staff'] is expected, \
                    f'unexpected include_staff parsing for value: {value}'

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
        with patch('futurex_openedx_extensions.dashboard.views.courses.get_courses_count_by_status') as mock_queryset:
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
