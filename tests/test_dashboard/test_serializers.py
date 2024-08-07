"""Test serializers for dashboard app"""
from unittest.mock import Mock, patch

import pytest
from common.djangoapps.student.models import SocialLink, UserProfile
from django.contrib.auth import get_user_model
from django.db.models import Value
from django.utils.timezone import get_current_timezone, now, timedelta
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from openedx.core.djangoapps.user_api.accounts.serializers import AccountLegacyProfileSerializer

from futurex_openedx_extensions.dashboard.serializers import (
    CourseDetailsBaseSerializer,
    CourseDetailsSerializer,
    LearnerBasicDetailsSerializer,
    LearnerCoursesDetailsSerializer,
    LearnerDetailsExtendedSerializer,
    LearnerDetailsForCourseSerializer,
    LearnerDetailsSerializer,
)
from futurex_openedx_extensions.helpers.constants import COURSE_STATUS_SELF_PREFIX, COURSE_STATUSES


def get_dummy_queryset(users_list=None):
    """Get a dummy queryset for testing."""
    if users_list is None:
        users_list = [10]
    return get_user_model().objects.filter(id__in=users_list).annotate(
        courses_count=Value(6),
        certificates_count=Value(2),
        certificate_available=Value(True),
        course_score=Value(0.67),
        active_in_course=Value(True),
    ).select_related('profile')


@pytest.mark.django_db
def test_learner_basic_details_serializer_no_profile(base_data):  # pylint: disable=unused-argument
    """Verify that the LearnerBasicDetailsSerializer is correctly defined."""
    queryset = get_dummy_queryset()
    data = LearnerBasicDetailsSerializer(queryset, many=True).data
    assert len(data) == 1
    assert data[0]['user_id'] == 10
    assert data[0]['full_name'] == ''
    assert data[0]['mobile_no'] is None
    assert data[0]['year_of_birth'] is None
    assert data[0]['gender'] is None


@pytest.mark.django_db
def test_learner_basic_details_serializer_with_profile(base_data):  # pylint: disable=unused-argument
    """Verify that the LearnerBasicDetailsSerializer processes the profile fields."""
    UserProfile.objects.create(
        user_id=10,
        name='Test User',
        phone_number='1234567890',
        gender='m',
        year_of_birth=1988,
    )
    queryset = get_dummy_queryset()
    data = LearnerBasicDetailsSerializer(queryset, many=True).data
    assert len(data) == 1
    assert data[0]['user_id'] == 10
    assert data[0]['full_name'] == 'Test User'
    assert data[0]['mobile_no'] == '1234567890'
    assert data[0]['year_of_birth'] == 1988
    assert data[0]['gender'] == 'm'


@pytest.mark.django_db
@pytest.mark.parametrize('first_name, last_name, profile_name, expected_full_name, expected_alt_name, use_case', [
    ('', '', '', '', '', 'all are empty'),
    ('', 'Doe', 'Alt John', 'Doe', 'Alt John', 'first name empty'),
    ('John', '', 'Alt John', 'John', 'Alt John', 'last name empty'),
    ('John', 'Doe', '', 'John Doe', '', 'profile name empty'),
    ('', '', 'Alt John', 'Alt John', '', 'first and last names empty'),
    ('John', 'John', 'Alt John', 'John John', 'Alt John', 'first and last names identical with no spaces'),
    ('John Doe', 'John Doe', 'Alt John', 'John Doe', 'Alt John', 'first and last names identical with spaces'),
    ('عربي', 'Doe', 'Alt John', 'عربي Doe', 'Alt John', 'Arabic name'),
    ('John', 'Doe', 'عربي', 'عربي', 'John Doe', 'Arabic alternative name'),
])
def test_learner_basic_details_serializer_full_name_alt_name(
    base_data, first_name, last_name, profile_name, expected_full_name, expected_alt_name, use_case
):  # pylint: disable=unused-argument, too-many-arguments
    """Verify that the LearnerBasicDetailsSerializer processes names as expected."""
    queryset = get_dummy_queryset()
    UserProfile.objects.create(
        user_id=10,
        name=profile_name,
    )
    user = queryset.first()
    user.first_name = first_name
    user.last_name = last_name
    user.save()

    serializer = LearnerBasicDetailsSerializer(queryset, many=True)
    data = serializer.data
    assert len(data) == 1
    assert data[0]['user_id'] == 10
    assert data[0]['full_name'] == expected_full_name, f'checking ({use_case}) failed'
    assert data[0]['alternative_full_name'] == expected_alt_name, f'checking ({use_case}) failed'


@pytest.mark.django_db
def test_learner_details_serializer(base_data):  # pylint: disable=unused-argument
    """Verify that the LearnerDetailsSerializer returns the needed fields"""
    queryset = get_dummy_queryset()
    data = LearnerDetailsSerializer(queryset, many=True).data
    assert len(data) == 1
    assert data[0]['enrolled_courses_count'] == 6
    assert data[0]['certificates_count'] == 2


@pytest.mark.django_db
def test_learner_details_for_course_serializer(base_data):  # pylint: disable=unused-argument
    """Verify that the LearnerDetailsForCourseSerializer returns the needed fields."""
    queryset = get_dummy_queryset()
    data = LearnerDetailsForCourseSerializer(queryset, many=True).data
    assert len(data) == 1
    assert data[0]['certificate_available'] is True
    assert data[0]['course_score'] == '0.67'
    assert data[0]['active_in_course'] is True


@pytest.mark.django_db
def test_learner_details_extended_serializer(base_data):  # pylint: disable=unused-argument
    """Verify that the LearnerDetailsExtendedSerializer returns the correct data."""
    queryset = get_dummy_queryset()
    profile = UserProfile.objects.create(
        user_id=10,
        city='Test City',
        bio='Test Bio',
        level_of_education='Test Level',
    )
    request = Mock(site=Mock(domain='https://an-example.com'))
    data = LearnerDetailsExtendedSerializer(queryset, many=True, context={'request': request}).data
    image_serialized = AccountLegacyProfileSerializer.get_profile_image(profile, queryset.first(), None)
    assert len(data) == 1
    assert data[0]['user_id'] == 10
    assert data[0]['city'] == 'Test City'
    assert data[0]['bio'] == 'Test Bio'
    assert data[0]['level_of_education'] == 'Test Level'
    assert data[0]['social_links'] == {}
    assert data[0]['image'] == image_serialized['image_url_large']
    assert data[0]['profile_link'] == 'https://an-example.com/u/user10/'
    assert image_serialized['has_image'] is False


@pytest.mark.django_db
def test_learner_details_extended_serializer_no_profile(base_data):  # pylint: disable=unused-argument
    """Verify that the LearnerDetailsExtendedSerializer returns the correct data when there is no profile."""
    queryset = get_dummy_queryset()
    data = LearnerDetailsExtendedSerializer(queryset, many=True).data
    assert len(data) == 1
    assert data[0]['user_id'] == 10
    assert data[0]['city'] is None
    assert data[0]['bio'] is None
    assert data[0]['level_of_education'] is None
    assert data[0]['social_links'] == {}
    assert data[0]['image'] is None
    assert data[0]['profile_link'] is None


@pytest.mark.django_db
def test_learner_details_extended_serializer_social_links(base_data):  # pylint: disable=unused-argument
    """Verify that the LearnerDetailsExtendedSerializer returns the social links."""
    queryset = get_dummy_queryset()
    profile = UserProfile.objects.create(user_id=10)
    SocialLink.objects.create(
        user_profile_id=profile.id,
        platform='facebook',
        social_link='https://facebook.com/test',
    )
    data = LearnerDetailsExtendedSerializer(queryset, many=True).data
    assert len(data) == 1
    assert data[0]['user_id'] == 10
    assert data[0]['social_links'] == {'facebook': 'https://facebook.com/test'}


@pytest.mark.django_db
def test_learner_details_extended_serializer_image(base_data):  # pylint: disable=unused-argument
    """Verify that the LearnerDetailsExtendedSerializer returns the profile image."""
    queryset = get_dummy_queryset([1])
    profile = UserProfile.objects.create(user_id=1)
    data = LearnerDetailsExtendedSerializer(queryset, many=True).data
    image_serialized = AccountLegacyProfileSerializer.get_profile_image(profile, queryset.first(), None)
    assert len(data) == 1
    assert data[0]['user_id'] == 1
    assert data[0]['image'] == image_serialized['image_url_large']
    assert image_serialized['has_image'] is True


@pytest.mark.django_db
def test_course_details_base_serializer(base_data):  # pylint: disable=unused-argument
    """Verify that the CourseDetailsBaseSerializer is correctly defined."""
    course = CourseOverview.objects.first()
    now_datetime = now()
    course.enrollment_start = now_datetime - timedelta(days=10)
    course.enrollment_end = now_datetime + timedelta(days=10)
    course.start = now_datetime - timedelta(days=5)
    course.end = now_datetime + timedelta(days=20)
    course.course_image_url = 'https://example.com/image.jpg'
    course.save()

    with patch('futurex_openedx_extensions.dashboard.serializers.get_tenants_by_org') as mock_get_tenants_by_org:
        mock_get_tenants_by_org.return_value = [1, 2]
        data = CourseDetailsBaseSerializer(course).data

    assert data['id'] == course.id
    assert data['self_paced'] == course.self_paced
    assert data['start_date'] == course.start
    assert data['end_date'] == course.end
    assert data['start_enrollment_date'] == course.enrollment_start
    assert data['end_enrollment_date'] == course.enrollment_end
    assert data['display_name'] == course.display_name
    assert data['image_url'] == 'https://example.com/image.jpg'
    assert data['org'] == course.org
    assert data['tenant_ids'] == [1, 2]


@pytest.mark.django_db
@pytest.mark.parametrize('start_date, end_date, expected_status', [
    (None, None, COURSE_STATUSES['active']),
    (None, now() + timedelta(days=10), COURSE_STATUSES['active']),
    (now() - timedelta(days=10), None, COURSE_STATUSES['active']),
    (now() - timedelta(days=10), now() + timedelta(days=10), COURSE_STATUSES['active']),
    (now() - timedelta(days=10), now() - timedelta(days=5), COURSE_STATUSES['archived']),
    (now() + timedelta(days=10), now() + timedelta(days=20), COURSE_STATUSES['upcoming']),
    (now() + timedelta(days=10), None, COURSE_STATUSES['upcoming']),
])
def test_course_details_base_serializer_status(
    base_data, start_date, end_date, expected_status
):  # pylint: disable=unused-argument
    """Verify that the CourseDetailsBaseSerializer returns the correct status."""
    course = CourseOverview.objects.first()
    course.self_paced = False
    course.start = start_date
    course.end = end_date
    course.save()

    data = CourseDetailsBaseSerializer(course).data
    assert data['status'] == expected_status

    course.self_paced = True
    course.save()
    data = CourseDetailsBaseSerializer(course).data
    assert data['status'] == f'{COURSE_STATUS_SELF_PREFIX}{expected_status}'


@pytest.mark.django_db
def test_course_details_serializer(base_data):  # pylint: disable=unused-argument
    """Verify that the CourseDetailsSerializer is correctly defined."""
    course = CourseOverview.objects.first()
    course.rating_total = None
    course.rating_count = None
    course.enrolled_count = 10
    course.active_count = 5
    course.certificates_count = 3
    course.save()
    data = CourseDetailsSerializer(course).data
    assert data['id'] == course.id
    assert data['enrolled_count'] == course.enrolled_count
    assert data['active_count'] == course.active_count
    assert data['certificates_count'] == course.certificates_count


@pytest.mark.django_db
@pytest.mark.parametrize('rating_total, rating_count, expected_rating', [
    (None, None, 0),
    (10, 0, 0),
    (0, 10, 0),
    (15, 5, 3),
    (17, 6, 2.8),
    (170, 59, 2.9),
])
def test_course_details_serializer_rating(
    base_data, rating_total, rating_count, expected_rating
):  # pylint: disable=unused-argument
    """Verify that the CourseDetailsSerializer returns the correct rating."""
    assert rating_total is None or rating_total == int(rating_total), 'bad test data, rating_total should be an integer'
    assert rating_count is None or rating_count == int(rating_count), 'bad test data, rating_count should be an integer'

    course = CourseOverview.objects.first()
    course.rating_total = rating_total
    course.rating_count = rating_count
    course.enrolled_count = 1
    course.active_count = 1
    course.certificates_count = 1
    course.save()
    data = CourseDetailsSerializer(course).data
    assert data['rating'] == expected_rating


@pytest.mark.django_db
def test_learner_courses_details_serializer(base_data):  # pylint: disable=unused-argument
    """Verify that the LearnerCoursesDetailsSerializer is correctly defined."""
    enrollment_date = (now() - timedelta(days=10)).astimezone(get_current_timezone())
    last_activity = (now() - timedelta(days=5)).astimezone(get_current_timezone())

    course = CourseOverview.objects.first()
    course.enrollment_date = enrollment_date
    course.last_activity = last_activity
    course.related_user_id = 44

    completion_summary = {
        'complete_count': 9,
        'incomplete_count': 3,
        'locked_count': 1,
    }

    request = Mock(site=Mock(domain='https://test.com'))
    with patch(
        'futurex_openedx_extensions.dashboard.serializers.get_course_blocks_completion_summary'
    ) as mock_get_completion_summary:
        with patch(
            'futurex_openedx_extensions.dashboard.serializers.get_certificates_for_user_by_course_keys'
        ) as mock_get_certificates:
            mock_get_completion_summary.return_value = completion_summary
            mock_get_certificates.return_value = {
                course.id: {
                    'download_url': 'https://test.com/courses/course-v1:dummy+key/certificate/',
                }
            }
            data = LearnerCoursesDetailsSerializer(course, context={'request': request}).data

    assert data['id'] == course.id
    assert data['enrollment_date'] == enrollment_date.isoformat()
    assert data['last_activity'] == last_activity.isoformat()
    assert data['progress_url'] == f'https://test.com/learning/course/{course.id}/progress/{course.related_user_id}/'
    assert data['grades_url'] == f'https://test.com/gradebook/{course.id}/'
    assert data['progress'] == completion_summary
    assert dict(data['grade']) == {
        'letter_grade': 'Fail',
        'percent': 0.4,
        'is_passing': False,
    }
    assert data['certificate_url'] == 'https://test.com/courses/course-v1:dummy+key/certificate/'
