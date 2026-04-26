"""Test views for the dashboard app - learners"""
# pylint: disable=duplicate-code
import json
from unittest.mock import ANY, Mock, patch

import ddt
import pytest
from common.djangoapps.student.models import CourseAccessRole, CourseEnrollment
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import resolve
from django.utils.timezone import now, timedelta
from opaque_keys.edx.locator import CourseLocator
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from rest_framework import status as http_status

from futurex_openedx_extensions.dashboard import serializers
from futurex_openedx_extensions.dashboard.views.learners import LearnersEnrollmentView, LearnerUnenrollView
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.models import ViewAllowedRoles
from futurex_openedx_extensions.helpers.permissions import FXHasTenantCourseAccess
from tests.fixture_helpers import get_all_orgs
from tests.test_dashboard.test_mixins import BaseTestViewMixin, MockPatcherMixin


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
        with patch('futurex_openedx_extensions.dashboard.views.learners.get_learner_info_queryset') as mock_get_info:
            mock_get_info.return_value = Mock(first=Mock(return_value=user))
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        data = json.loads(response.content)
        self.assertDictEqual(data, serializers.LearnerDetailsExtendedSerializer(user).data)

    @patch('futurex_openedx_extensions.dashboard.views.learners.serializers.LearnerDetailsExtendedSerializer')
    def test_request_in_context(self, mock_serializer):
        """Verify that the view calls the serializer with the correct context"""
        request = self._get_request()
        view_class = self._get_view_class()
        mock_serializer.return_value = Mock(data={})

        with patch('futurex_openedx_extensions.dashboard.views.learners.get_learner_info_queryset') as mock_get_info:
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
        patch_path = 'futurex_openedx_extensions.dashboard.views.learners.get_learner_courses_info_queryset'
        with patch(patch_path) as mock_get_info:
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

    @patch('futurex_openedx_extensions.dashboard.views.learners.serializers.LearnerCoursesDetailsSerializer')
    def test_request_in_context(self, mock_serializer):
        """Verify that the view uses the correct serializer"""
        request = self._get_request()
        view_class = self._get_view_class()

        patch_path = 'futurex_openedx_extensions.dashboard.views.learners.get_learner_courses_info_queryset'
        with patch(patch_path) as mock_get_info:
            mock_get_info.return_value = Mock()
            view = view_class()
            view.request = request
            view.get(request, 'user10')

        mock_serializer.assert_called_once_with(
            mock_get_info.return_value,
            context={'request': request},
            many=True,
        )


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


@pytest.mark.usefixtures('base_data')
@ddt.ddt
class TestLearnerUnenrollView(BaseTestViewMixin):
    """Tests for LearnerUnenrollView"""
    VIEW_NAME = 'fx_dashboard:learners-unenroll'

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
        self.assertIn('user_key', response.data)
        self.assertEqual(str(response.data['user_key'][0]), 'This field is required.')

    def test_invalid_request_missing_course_id(self):
        """Test request with missing course_id"""
        self.login_user(self.staff_user)
        data = {
            'user_key': self.test_user.username,
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertIn('course_id', response.data)
        self.assertEqual(str(response.data['course_id'][0]), 'This field is required.')

    @ddt.data(
        ('user_id', lambda user: str(user.id)),
        ('username', lambda user: user.username),
        ('email', lambda user: user.email),
    )
    @ddt.unpack
    @patch('futurex_openedx_extensions.dashboard.serializers.get_user_by_key')
    def test_successful_unenroll_with_different_identifiers(
        self, _identifier_name, identifier_value_func, mock_get_user_by_key
    ):
        """Test successful unenrollment using different user identifiers"""
        mock_get_user_by_key.return_value = {
            'user': self.test_user,
            'error_code': None,
            'error_message': None
        }
        self.login_user(self.staff_user)
        data = {
            'course_id': self.test_course_id,
            'user_key': identifier_value_func(self.test_user),
        }

        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIn('Successfully unenrolled', response.data['message'])
        self.assertEqual(response.data['user_id'], self.test_user.id)
        self.assertEqual(response.data['username'], self.test_user.username)
        self.assertEqual(response.data['course_id'], self.test_course_id)
        self.enrollment.refresh_from_db()
        self.assertFalse(self.enrollment.is_active)

    @patch('futurex_openedx_extensions.dashboard.serializers.get_user_by_key')
    def test_unenroll_with_reason(self, mock_get_user_by_key):
        """Test unenrollment with a reason provided"""
        mock_get_user_by_key.return_value = {
            'user': self.test_user,
            'error_code': None,
            'error_message': None
        }
        self.login_user(self.staff_user)
        data = {
            'user_key': self.test_user.username,
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
            'user_key': 'nonexistent_user',
            'course_id': self.test_course_id,
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertTrue(any('User not found' in str(err) or 'nonexistent_user' in str(err) for err in response.data))

    def test_unenroll_course_not_found(self):
        """Test unenrollment when course doesn't exist"""
        self.login_user(self.staff_user)
        data = {
            'user_key': self.test_user.username,
            'course_id': 'course-v1:ORG1+999+999',
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data['reason'],
            'You do not have permission to unenroll learners from this course'
        )

    def test_unenroll_invalid_course_id_format(self):
        """Test unenrollment with invalid course ID format"""
        self.login_user(self.staff_user)
        data = {
            'user_key': self.test_user.username,
            'course_id': 'invalid-course-id',
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertIn('course_id', response.data)

    @patch('futurex_openedx_extensions.dashboard.serializers.get_user_by_key')
    def test_unenroll_user_not_enrolled(self, mock_get_user_by_key):
        """Test unenrollment when user is not enrolled in the course"""
        mock_get_user_by_key.return_value = {
            'user': self.test_user,
            'error_code': None,
            'error_message': None
        }
        self.login_user(self.staff_user)
        data = {
            'user_key': self.test_user.username,
            'course_id': 'course-v1:ORG1+3+3',  # Different from self.test_course_id (which is ORG1+2+2)
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertTrue(any('not enrolled' in str(err) for err in response.data))

    @patch('futurex_openedx_extensions.dashboard.serializers.get_user_by_key')
    def test_unenroll_already_unenrolled(self, mock_get_user_by_key):
        """Test unenrollment when user is already unenrolled"""
        mock_get_user_by_key.return_value = {
            'user': self.test_user,
            'error_code': None,
            'error_message': None
        }
        self.login_user(self.staff_user)
        self.enrollment.is_active = False
        self.enrollment.save()

        data = {
            'user_key': self.test_user.username,
            'course_id': self.test_course_id,
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertTrue(any('already unenrolled' in str(err) for err in response.data))

    def test_unenroll_invalid_course_id_format_no_org(self):
        """Test unenrollment with course ID that has no org"""
        self.login_user(self.staff_user)
        data = {
            'user_key': self.test_user.username,
            'course_id': 'course-v1:+1+1',  # Missing org
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertIn('course_id', response.data)

    def test_view_has_correct_permissions(self):
        """Test that the view has correct permission classes"""
        view = LearnerUnenrollView()
        self.assertIn(FXHasTenantCourseAccess, view.permission_classes)

    def test_view_configuration(self):
        """Test view configuration"""
        view = LearnerUnenrollView()
        self.assertEqual(view.fx_view_name, 'learner_unenroll')
        self.assertEqual(view.fx_default_read_write_roles, ['staff', 'instructor', 'org_course_creator_group'])
        self.assertEqual(view.fx_view_description, 'api/fx/learners/v1/unenroll: Unenroll a learner from a course')

    def test_unenroll_permission_denied_for_course_org(self):
        """Test permission denied when user doesn't have access to course org"""
        self.login_user(self.staff_user)
        test_course = 'course-v1:ORG1+3+3'
        CourseEnrollment.objects.create(
            user=self.test_user,
            course_id=test_course,
            is_active=True
        )
        original_post = LearnerUnenrollView.post

        def patched_post(view_self, request, *args, **kwargs):
            request.fx_permission_info['view_allowed_full_access_orgs'] = [
                'org2', 'org3', 'org8', 'org4', 'org5'  # org1 excluded
            ]
            return original_post(view_self, request, *args, **kwargs)

        with patch.object(LearnerUnenrollView, 'post', patched_post):
            data = {
                'user_key': self.test_user.username,
                'course_id': test_course,  # ORG1 not in allowed list
            }
            response = self.client.post(self.url, data, format='json')
            self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)
            self.assertIn(
                'You do not have permission to unenroll learners from this course',
                response.data['reason']
            )

    @patch('futurex_openedx_extensions.dashboard.serializers.get_user_by_key')
    @patch('futurex_openedx_extensions.dashboard.views.learners.get_course_search_queryset')
    def test_unenroll_with_course_specific_staff_access(self, mock_course_search, mock_get_user_by_key):
        """Test that user with course-specific staff access can unenroll learners"""
        mock_get_user_by_key.return_value = {
            'user': self.test_user,
            'error_code': None,
            'error_message': None
        }
        self.login_user(self.staff_user)
        test_course = 'course-v1:ORG2+3+3'
        CourseEnrollment.objects.create(
            user=self.test_user,
            course_id=test_course,
            is_active=True
        )
        course_key = CourseLocator.from_string(test_course)
        mock_course_search.return_value = CourseOverview.objects.filter(id=course_key)
        data = {
            'user_key': self.test_user.username,
            'course_id': test_course,
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIn('Successfully unenrolled', response.data['message'])

    @patch('futurex_openedx_extensions.dashboard.serializers.get_user_by_key')
    @patch('futurex_openedx_extensions.dashboard.views.learners.get_course_search_queryset')
    def test_unenroll_with_course_specific_instructor_access(self, mock_course_search, mock_get_user_by_key):
        """Test that user with course-specific instructor access can unenroll learners"""
        mock_get_user_by_key.return_value = {
            'user': self.test_user,
            'error_code': None,
            'error_message': None
        }
        self.login_user(self.staff_user)
        test_course = 'course-v1:ORG1+3+3'
        CourseEnrollment.objects.create(
            user=self.test_user,
            course_id=test_course,
            is_active=True
        )
        course_key = CourseLocator.from_string(test_course)
        mock_course_search.return_value = CourseOverview.objects.filter(id=course_key)

        data = {
            'user_key': self.test_user.username,
            'course_id': test_course,
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIn('Successfully unenrolled', response.data['message'])

    def test_unenroll_denied_without_course_specific_access(self):
        """Test that user without course-specific access is denied unenrollment"""
        self.login_user(self.staff_user)
        test_course = 'course-v1:ORG1+3+3'
        CourseEnrollment.objects.create(
            user=self.test_user,
            course_id=test_course,
            is_active=True
        )
        original_post = LearnerUnenrollView.post

        def patched_post(view_self, request, *args, **kwargs):
            request.fx_permission_info['view_allowed_full_access_orgs'] = []
            request.fx_permission_info['user_roles'] = {
                'staff': {
                    'course_limited_access': ['course-v1:ORG1+2+2'],
                    'orgs_of_courses': ['org1'],
                }
            }
            return original_post(view_self, request, *args, **kwargs)

        with patch.object(LearnerUnenrollView, 'post', patched_post):
            data = {
                'user_key': self.test_user.username,
                'course_id': test_course,
            }
            response = self.client.post(self.url, data, format='json')
            self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)
            self.assertIn(
                'You do not have permission to unenroll learners from this course',
                response.data['reason']
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
        with patch('futurex_openedx_extensions.dashboard.views.learners.get_learners_queryset') as mock_queryset:
            self.client.get(self.url)
            mock_queryset.assert_called_once()
            assert mock_queryset.call_args_list[0][1]['fx_permission_info']['view_allowed_full_access_orgs'] \
                   == get_all_orgs()
            assert mock_queryset.call_args_list[0][1]['search_text'] is None

    def test_search(self):
        """Verify that the view filters the learners by search text"""
        self.login_user(self.staff_user)
        with patch('futurex_openedx_extensions.dashboard.views.learners.get_learners_queryset') as mock_queryset:
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

    @patch('futurex_openedx_extensions.dashboard.views.learners.get_learners_queryset')
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
