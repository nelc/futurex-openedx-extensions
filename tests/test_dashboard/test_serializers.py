"""Test serializers for dashboard app"""
from unittest.mock import Mock, patch

import pytest
from cms.djangoapps.course_creators.models import CourseCreator
from common.djangoapps.student.models import CourseAccessRole, CourseEnrollment, SocialLink, UserProfile
from custom_reg_form.models import ExtraInfo
from deepdiff import DeepDiff
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.db.models import Value
from django.utils.timezone import get_current_timezone, now, timedelta
from lms.djangoapps.grades.models import PersistentSubsectionGrade
from opaque_keys.edx.keys import UsageKey
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from openedx.core.djangoapps.user_api.accounts.serializers import AccountLegacyProfileSerializer

from futurex_openedx_extensions.dashboard.serializers import (
    CourseDetailsBaseSerializer,
    CourseDetailsSerializer,
    CourseScoreAndCertificateSerializer,
    DataExportTaskSerializer,
    LearnerBasicDetailsSerializer,
    LearnerCoursesDetailsSerializer,
    LearnerDetailsExtendedSerializer,
    LearnerDetailsForCourseSerializer,
    LearnerDetailsSerializer,
    LearnerEnrollmentSerializer,
    ReadOnlySerializer,
    UserRolesSerializer,
)
from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers.converters import dt_to_str
from futurex_openedx_extensions.helpers.models import DataExportTask
from futurex_openedx_extensions.helpers.roles import RoleType


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
    ).select_related('profile').select_related('extrainfo')


@pytest.fixture
def serializer_context():
    """Create a context for testing."""
    return {
        'request': Mock(
            fx_permission_info={
                'view_allowed_full_access_orgs': ['org1', 'org2'],
                'view_allowed_course_access_orgs': ['org3'],
                'view_allowed_any_access_orgs': ['org1', 'org2', 'org3'],
                'view_allowed_tenant_ids_any_access': [1, 3],
            },
            query_params={},
        )
    }


@pytest.fixture
def grading_context():
    """Create a grading context for testing."""
    with patch('futurex_openedx_extensions.dashboard.serializers.grading_context_for_course') as mock_grading_context:
        mock_grading_context.return_value = {
            'all_graded_subsections_by_type': {
                'Homework': [
                    {'subsection_block': Mock(
                        display_name='First Homework',
                        location=UsageKey.from_string('block-v1:ORG2+1+1+type@homework+block@1'),
                    )},
                    {'subsection_block': Mock(
                        display_name='Second Homework',
                        location=UsageKey.from_string('block-v1:ORG2+1+1+type@homework+block@2'),
                    )}
                ],
                'Exam': [
                    {'subsection_block': Mock(
                        display_name='The final exam',
                        location=UsageKey.from_string('block-v1:ORG2+1+1+type@homework+block@3'),
                    )},
                ],
            }
        }
        yield mock_grading_context


@pytest.mark.django_db
def test_data_export_task_serializer_for_notes_max_len_limit(base_data):  # pylint: disable=unused-argument
    """Verify the DataExportSerializer for notes max len limit."""
    user = get_user_model().objects.get(id=10)
    task = DataExportTask.objects.create(filename='test.csv', view_name='test', user=user, tenant_id=1)
    data = {'notes': 'A' * 256}
    serializer = DataExportTaskSerializer(instance=task, data=data)
    assert serializer.is_valid() is False
    assert 'notes' in serializer.errors
    assert serializer.errors['notes'] == ['Ensure this field has no more than 255 characters.']


@pytest.mark.django_db
def test_data_export_task_serializer_for_notes_validation(base_data):  # pylint: disable=unused-argument
    """Verify the DataExportSerializer for notes HTML tags validation."""
    user = get_user_model().objects.get(id=10)
    task = DataExportTask.objects.create(filename='test.csv', view_name='test', user=user, tenant_id=1)
    text = 'hello'
    text_with_html_tags = f'<h1>{text}</h1>'
    serializer = DataExportTaskSerializer(instance=task, data={'notes': text_with_html_tags})
    assert serializer.is_valid() is True
    assert serializer.validated_data['notes'] == '&lt;h1&gt;hello&lt;/h1&gt;'


@pytest.mark.django_db
@patch('futurex_openedx_extensions.dashboard.serializers.get_exported_file_url')
def test_data_export_task_serializer_for_download_url(
    mocked_exported_file_url, base_data
):  # pylint: disable=unused-argument
    """Verify the DataExportSerializer for download_url."""
    mocked_exported_file_url.return_value = 'fake_download_url'
    user = get_user_model().objects.get(id=10)
    task = DataExportTask.objects.create(
        filename='test.csv',
        view_name='test',
        user=user, tenant_id=1,
        progress=1.1,
        status=DataExportTask.STATUS_COMPLETED
    )
    serializer = DataExportTaskSerializer(
        instance=task, context={'requested_optional_field_tags': ['download_url']}
    )
    assert serializer.data['download_url'] == 'fake_download_url'


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
def test_learner_basic_details_serializer_with_extra_info(base_data):  # pylint: disable=unused-argument
    """Verify that the LearnerBasicDetailsSerializer processes the extrainfo fields."""
    ExtraInfo.objects.create(
        user_id=10,
        national_id='1234567890',
    )
    queryset = get_dummy_queryset()
    data = LearnerBasicDetailsSerializer(queryset, many=True).data
    assert len(data) == 1
    assert data[0]['user_id'] == 10
    assert data[0]['national_id'] == '1234567890'


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
@pytest.mark.parametrize('arabic_first_name, arabic_last_name, arabic_name, expected_alt_name, use_case', [
    ('', '', '', '', 'all are empty.'),
    ('اسم', 'كامل', 'عربي', 'عربي', 'all are set, give priority to arabic name.'),
    ('اسم', 'كامل', '', 'اسم كامل', 'arabic name is empty, arabic full name should be used.'),
    ('', '', 'عربي', 'عربي', 'arabic full name is empty, arabic name should be used.'),
    ('', 'قديم', 'عربي', 'عربي', 'arabic fist name is empty, arabic name should be used.'),
    ('قديم', '', 'عربي', 'عربي', 'arabic last name is empty, arabic name should be used.'),
    ('', 'قديم', '', 'قديم', 'arabic fist name and arabic name is empty.'),
    ('قديم', '', '', 'قديم', 'arabic last name and arabic name is empty.'),
])
def test_learner_basic_details_serializer_arabic_name_as_alt_name(
    base_data, arabic_first_name, arabic_last_name, arabic_name, expected_alt_name, use_case
):  # pylint: disable=unused-argument, too-many-arguments
    """Verify that the LearnerBasicDetailsSerializer processes names as expected."""
    queryset = get_dummy_queryset()
    user = queryset.first()
    ExtraInfo.objects.create(
        user_id=user.id,
        arabic_first_name=arabic_first_name,
        arabic_last_name=arabic_last_name,
        arabic_name=arabic_name
    )
    serializer = LearnerBasicDetailsSerializer(queryset, many=True)
    data = serializer.data
    assert len(data) == 1
    assert data[0]['user_id'] == 10
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
def test_course_score_and_certificate_serializer_for_required_child_methods():
    """Verify that the CourseScoreAndCertificateSerializer for required child methods"""
    class TestSerializer(CourseScoreAndCertificateSerializer):
        """Serializer for learner details for a course."""
        class Meta:
            model = get_user_model()
            fields = CourseScoreAndCertificateSerializer.Meta.fields

    context = {'requested_optional_field_tags': ['certificate_url']}
    qs = get_dummy_queryset()
    with pytest.raises(NotImplementedError) as exc_info:
        serializer = TestSerializer(qs, many=True, context=context)
        assert len(serializer.data) == qs.count()

    assert str(exc_info.value) == 'Child class must implement _get_course_id method.'
    TestSerializer._get_user = Mock(return_value=qs[0])  # pylint: disable=protected-access
    with pytest.raises(NotImplementedError) as exc_info:
        serializer = TestSerializer(qs, many=True, context=context)
        assert len(serializer.data) == qs.count()

    assert str(exc_info.value) == 'Child class must implement _get_user method.'
    TestSerializer._get_course_id = Mock()  # pylint: disable=protected-access
    serializer = TestSerializer(qs, many=True, context=context)
    assert len(serializer.data) == qs.count()


@pytest.mark.django_db
@patch('futurex_openedx_extensions.dashboard.serializers.CourseScoreAndCertificateSerializer.collect_grading_info')
def test_learner_enrollments_serializer(mock_collect, base_data,):  # pylint: disable=unused-argument
    """Verify that the LearnerEnrollmentSerializer returns the needed fields."""
    queryset = CourseEnrollment.objects.filter(user_id=10, course_id='course-v1:ORG3+1+1').annotate(
        certificate_available=Value(True),
        course_score=Value(0.67),
        active_in_course=Value(True),
    )
    serializer = LearnerEnrollmentSerializer(queryset, context={
        'course_id': 'course-v1:ORG3+1+1'
    }, many=True)
    mock_collect.assert_called_once()
    data = serializer.data
    assert len(data) == 1
    assert data[0]['certificate_available'] is True
    assert data[0]['course_score'] == 0.67
    assert data[0]['active_in_course'] is True


@pytest.mark.django_db
@patch('futurex_openedx_extensions.dashboard.serializers.get_nafath_sites')
def test_learner_enrollments_serializer_for_nafath_id(mocked_get_nafath_sites):
    """Ensure LearnerEnrollmentSerializer correctly processes nafath_id based on social auth conditions."""
    site, _ = Site.objects.update_or_create(
        domain='s2.sample.com',
        defaults={'name': 's2.sample.com'}
    )
    mocked_get_nafath_sites.return_value = [site.domain]
    queryset = CourseEnrollment.objects.filter(user_id=10, course_id='course-v1:ORG3+1+1').annotate(
        certificate_available=Value(True),
        course_score=Value(0.67),
        active_in_course=Value(True),
    )
    context = {
        'course_id': 'course-v1:ORG3+1+1',
        'requested_optional_field_tags': ['nafath_id']
    }

    def assert_nafath_id(expected, msg):
        """Helper to serialize and assert nafath_id."""
        serializer = LearnerEnrollmentSerializer(queryset, context=context, many=True)
        assert serializer.data[0].get('nafath_id') == expected, msg

    assert_nafath_id('', 'nafath_id should be empty when no social auth exists')

    queryset[0].user.social_auth.create(provider='other_provider', extra_data={'uid': ['12345']})
    assert_nafath_id('', 'nafath_id should be empty for an incorrect provider')

    queryset[0].user.social_auth.create(provider=settings.FX_NAFATH_AUTH_PROVIDER, extra_data={'uid': ['12345']})
    assert_nafath_id('12345', 'nafath_id should be returned when the correct provider and single UID exist')

    social_auth = queryset[0].user.social_auth.get(provider=settings.FX_NAFATH_AUTH_PROVIDER)
    social_auth.extra_data = {'uid': ['12345', 'another-id']}
    social_auth.save()
    assert_nafath_id('', 'nafath_id should be empty when multiple UIDs are present')


@pytest.mark.django_db
@patch('futurex_openedx_extensions.dashboard.serializers.get_course_blocks_completion_summary')
@pytest.mark.parametrize('is_course_id_in_context, optional_field_tags', [
    (True, ['exam_scores']),
    (True, ['__all__']),
    (True, ['csv_export']),
    (False, ['exam_scores']),
    (False, ['__all__']),
    (False, ['csv_export']),
])
def test_learner_enrollment_serializer_exam_scores(
    mock_get_completion, is_course_id_in_context, optional_field_tags, grading_context, base_data,
):  # pylint: disable=unused-argument, redefined-outer-name
    """
    Verify that the LearnerEnrollmentSerializer returns exam_scores
    only when course_id is set in serializer_context
    """
    queryset = CourseEnrollment.objects.filter(course_id='course-v1:ORG2+1+1').annotate(
        certificate_available=Value(True),
        course_score=Value(0.67),
        active_in_course=Value(True),
    )
    PersistentSubsectionGrade.objects.create(
        user_id=queryset[0].user.id,
        course_id='course-v1:ORG2+1+1',
        usage_key='block-v1:ORG2+1+1+type@homework+block@1',
        earned_graded=0,
        possible_graded=0,
        earned_all=77.0,
        possible_all=88.0,
    )
    PersistentSubsectionGrade.objects.create(
        user_id=queryset[0].user.id,
        course_id='course-v1:ORG2+1+1',
        usage_key='block-v1:ORG2+1+1+type@homework+block@2',
        earned_graded=0,
        possible_graded=0,
        earned_all=9.0,
        possible_all=10.0,
        first_attempted=now() - timedelta(days=1),
    )
    mock_get_completion.return_value = {'complete_count': 2, 'incomplete_count': 1, 'locked_count': 1}
    context = {'requested_optional_field_tags': optional_field_tags}

    if is_course_id_in_context:
        context.update({'course_id': 'course-v1:ORG2+1+1'})

    serializer = LearnerEnrollmentSerializer(queryset[0], context=context)
    data = serializer.data

    if is_course_id_in_context:
        assert 'earned - Homework 1: First Homework' in data.keys()
        assert 'earned - Homework 2: Second Homework' in data.keys()
    else:
        assert 'earned - Homework 1: First Homework' not in data.keys()
        assert 'earned - Homework 2: Second Homework' not in data.keys()


def test_learner_details_for_course_serializer_optional_fields():
    """Verify that the LearnerDetailsForCourseSerializer returns the correct optional fields."""
    serializer = LearnerDetailsForCourseSerializer(context={'course_id': 'course-v1:ORG2+1+1'})
    assert serializer.optional_field_names == ['progress', 'certificate_url', 'exam_scores']


@pytest.mark.django_db
@pytest.mark.parametrize('omit_subsection_name, display_name_included', [
    ('absent', True),
    ('1', False),
    ('not 1', True),
])
def test_learner_details_for_course_serializer_collect_grading_info(
    grading_context, omit_subsection_name, display_name_included, base_data,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that the LearnerDetailsForCourseSerializer.collect_grading_info works fine."""
    queryset = get_dummy_queryset()
    context = {
        'course_id': 'course-v1:ORG2+1+1',
        'requested_optional_field_tags': ['exam_scores'],
    }
    if omit_subsection_name != 'absent':
        context['omit_subsection_name'] = omit_subsection_name
    serializer = LearnerDetailsForCourseSerializer(
        queryset,
        context=context,
    )

    expected_grading_info = {
        '0': {
            'header_name': 'Homework 1: First Homework' if display_name_included else 'Homework 1',
            'location': 'block-v1:ORG2+1+1+type@homework+block@1',
        },
        '1': {
            'header_name': 'Homework 2: Second Homework' if display_name_included else 'Homework 2',
            'location': 'block-v1:ORG2+1+1+type@homework+block@2',
        },
        '2': {
            'header_name': 'Exam: The final exam' if display_name_included else 'Exam',
            'location': 'block-v1:ORG2+1+1+type@homework+block@3',
        }
    }

    assert all(isinstance(value['location'], str) for _, value in serializer.grading_info.items())
    assert all(isinstance(key, str) for key in serializer.subsection_locations)
    assert not DeepDiff(serializer.grading_info, expected_grading_info, ignore_order=True)
    assert not DeepDiff(serializer.subsection_locations, {
        'block-v1:ORG2+1+1+type@homework+block@1': '0',
        'block-v1:ORG2+1+1+type@homework+block@2': '1',
        'block-v1:ORG2+1+1+type@homework+block@3': '2',
    }, ignore_order=True)


@pytest.mark.django_db
def test_learner_details_for_course_serializer_collect_grading_info_not_used(
    base_data,
):  # pylint: disable=unused-argument
    """
    Verify that the LearnerDetailsForCourseSerializer.collect_grading_info does nothing when exam_scores field
    is not requested.
    """
    queryset = get_dummy_queryset()
    serializer = LearnerDetailsForCourseSerializer(queryset, context={'course_id': 'course-v1:ORG2+1+1'})

    assert not serializer.grading_info
    assert not serializer.subsection_locations
    serializer.collect_grading_info()
    assert not serializer.grading_info
    assert not serializer.subsection_locations


@pytest.mark.django_db
@patch('futurex_openedx_extensions.dashboard.serializers.get_certificate_url')
def test_learner_details_for_course_serializer_certificate_url(
    mock_get_certificate_url, base_data,
):  # pylint: disable=unused-argument
    """Verify that the LearnerDetailsForCourseSerializer returns the correct certificate_url."""
    queryset = get_dummy_queryset()
    mock_get_certificate_url.return_value = 'https://example.com/courses/course-v1:ORG2+1+1/certificate/'
    serializer = LearnerDetailsForCourseSerializer(
        queryset,
        context={
            'course_id': 'course-v1:ORG2+1+1',
            'requested_optional_field_tags': ['certificate_url'],
        },
        many=True,
    )
    assert serializer.data[0]['certificate_url'] == mock_get_certificate_url.return_value


@pytest.mark.django_db
@patch('futurex_openedx_extensions.dashboard.serializers.get_course_blocks_completion_summary')
@pytest.mark.parametrize('progress_values, expected_result', [
    ([0, 0, 0], 0.0),
    ([0, 0, 0], 0.0),
    ([2, 1, 2], 0.4),
    ([3, 2, 2], 0.4286),
])
def test_learner_details_for_course_serializer_progress(
    mock_get_completion, progress_values, expected_result, base_data,
):  # pylint: disable=unused-argument
    """Verify that the LearnerDetailsForCourseSerializer returns the correct certificate_url."""
    queryset = get_dummy_queryset()
    mock_get_completion.return_value = {
        'complete_count': progress_values[0],
        'incomplete_count': progress_values[1],
        'locked_count': progress_values[2],
    }
    serializer = LearnerDetailsForCourseSerializer(
        queryset,
        context={
            'course_id': 'course-v1:ORG2+1+1',
            'requested_optional_field_tags': ['progress'],
        },
        many=True,
    )
    assert serializer.data[0]['progress'] == expected_result


@pytest.mark.django_db
@pytest.mark.parametrize('many', [True, False])
def test_learner_details_for_course_serializer_exam_scores(
    many, grading_context, base_data,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that the LearnerDetailsForCourseSerializer returns the correct exam_scores."""
    queryset = get_dummy_queryset()
    PersistentSubsectionGrade.objects.create(
        user_id=queryset[0].id,
        course_id='course-v1:ORG2+1+1',
        usage_key='block-v1:ORG2+1+1+type@homework+block@1',
        earned_graded=0,
        possible_graded=0,
        earned_all=77.0,
        possible_all=88.0,
    )
    PersistentSubsectionGrade.objects.create(
        user_id=queryset[0].id,
        course_id='course-v1:ORG2+1+1',
        usage_key='block-v1:ORG2+1+1+type@homework+block@2',
        earned_graded=0,
        possible_graded=0,
        earned_all=9.0,
        possible_all=10.0,
        first_attempted=now() - timedelta(days=1),
    )

    serializer = LearnerDetailsForCourseSerializer(
        queryset if many else queryset.first(),
        context={
            'course_id': 'course-v1:ORG2+1+1',
            'requested_optional_field_tags': ['exam_scores'],
        },
        many=many,
    )

    data = serializer.data[0] if many else serializer.data
    assert data['earned - Homework 1: First Homework'] == 'no attempt'
    assert data['earned - Homework 2: Second Homework'] == 9.0
    assert data['earned - Exam: The final exam'] == 'no attempt'


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
    request = Mock(site=Mock(domain='an-example.com'), scheme='https')
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

    assert data['id'] == str(course.id)
    assert data['self_paced'] == course.self_paced
    assert data['start_date'] == dt_to_str(course.start)
    assert data['end_date'] == dt_to_str(course.end)
    assert data['start_enrollment_date'] == dt_to_str(course.enrollment_start)
    assert data['end_enrollment_date'] == dt_to_str(course.enrollment_end)
    assert data['display_name'] == course.display_name
    assert data['image_url'] == 'https://example.com/image.jpg'
    assert data['org'] == course.org
    assert data['tenant_ids'] == [1, 2]


@pytest.mark.django_db
@pytest.mark.parametrize('start_date, end_date, expected_status', [
    (None, None, cs.COURSE_STATUSES['active']),
    (None, now() + timedelta(days=10), cs.COURSE_STATUSES['active']),
    (now() - timedelta(days=10), None, cs.COURSE_STATUSES['active']),
    (now() - timedelta(days=10), now() + timedelta(days=10), cs.COURSE_STATUSES['active']),
    (now() - timedelta(days=10), now() - timedelta(days=5), cs.COURSE_STATUSES['archived']),
    (now() + timedelta(days=10), now() + timedelta(days=20), cs.COURSE_STATUSES['upcoming']),
    (now() + timedelta(days=10), None, cs.COURSE_STATUSES['upcoming']),
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
    assert data['status'] == f'{cs.COURSE_STATUS_SELF_PREFIX}{expected_status}'


@pytest.mark.django_db
def test_course_details_serializer(base_data):  # pylint: disable=unused-argument
    """Verify that the CourseDetailsSerializer is correctly defined."""
    course = CourseOverview.objects.first()
    course.rating_total = None
    course.rating_count = None
    course.enrolled_count = 10
    course.active_count = 5
    course.certificates_count = 3
    course.completion_rate = 0.3
    course.save()
    data = CourseDetailsSerializer(course).data
    assert data['id'] == str(course.id)
    assert data['enrolled_count'] == course.enrolled_count
    assert data['active_count'] == course.active_count
    assert data['certificates_count'] == course.certificates_count
    assert data['completion_rate'] == course.completion_rate


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
    course.completion_rate = 1
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

    request = Mock(site=Mock(domain='test.com'), scheme='https')
    with patch(
        'futurex_openedx_extensions.dashboard.serializers.get_course_blocks_completion_summary',
        return_value=completion_summary,
    ):
        with patch(
            'futurex_openedx_extensions.dashboard.serializers.LearnerCoursesDetailsSerializer.get_certificate_url',
            return_value='https://test.com/courses/course-v1:dummy+key/certificate/'
        ):
            data = LearnerCoursesDetailsSerializer(course, context={'request': request}).data

    assert data['id'] == str(course.id)
    assert data['enrollment_date'] == dt_to_str(enrollment_date)
    assert data['last_activity'] == dt_to_str(last_activity)
    assert data['progress_url'] == f'https://test.com/learning/course/{course.id}/progress/{course.related_user_id}/'
    assert data['grades_url'] == f'https://test.com/gradebook/{course.id}/'
    assert data['progress'] == completion_summary
    assert dict(data['grade']) == {
        'letter_grade': 'Fail',
        'percent': 0.4,
        'is_passing': False,
    }
    assert data['certificate_url'] == 'https://test.com/courses/course-v1:dummy+key/certificate/'


@pytest.mark.django_db
def test_user_roles_serializer_init(
    base_data, serializer_context
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that the UserRolesSerializer is correctly defined."""
    user3 = get_user_model().objects.get(id=3)

    with patch(
        'futurex_openedx_extensions.dashboard.serializers.UserRolesSerializer.construct_roles_data'
    ) as mock_construct_roles_data:
        mock_construct_roles_data.return_value = {3: {}}
        serializer = UserRolesSerializer(user3, context=serializer_context)

    assert mock_construct_roles_data.called
    assert mock_construct_roles_data.call_args[0][0] == [user3]
    assert serializer.orgs_filter == ['org1', 'org2', 'org3']
    assert serializer.permitted_tenant_ids == \
           serializer_context['request'].fx_permission_info['view_allowed_tenant_ids_any_access']
    assert serializer.data == {
        'user_id': user3.id,
        'email': user3.email,
        'username': user3.username,
        'national_id': '11223344556677',
        'full_name': '',
        'alternative_full_name': '',
        'global_roles': [],
        'tenants': {}
    }


@pytest.mark.django_db
@pytest.mark.parametrize('instance, many', [
    ([], True),
    (None, True),
    (None, False),
])
def test_user_roles_serializer_init_no_construct_call(
    base_data, serializer_context, instance, many
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that the UserRolesSerializer does not call construct_roles_data if the instance is empty."""
    with patch(
        'futurex_openedx_extensions.dashboard.serializers.UserRolesSerializer.construct_roles_data'
    ) as mock_construct_roles_data:
        UserRolesSerializer(instance, context=serializer_context, many=many)

    mock_construct_roles_data.assert_not_called()


@pytest.mark.django_db
def test_user_roles_serializer_get_org_tenants(
    base_data, serializer_context
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that the UserRolesSerializer correctly gets the org tenants and caches it in _org_tenant."""
    user3 = get_user_model().objects.get(id=3)
    with patch(
        'futurex_openedx_extensions.dashboard.serializers.get_tenants_by_org'
    ) as mock_get_tenants_by_org, patch(
        'futurex_openedx_extensions.dashboard.serializers.UserRolesSerializer.construct_roles_data'
    ) as mock_construct_roles_data:
        mock_construct_roles_data.return_value = {
            3: {
                1: {
                    'tenant_roles': ['instructor'],
                    'course_roles': {},
                },
            },
        }
        serializer = UserRolesSerializer(user3, context=serializer_context)

        mock_get_tenants_by_org.return_value = [1, 2]
        assert isinstance(serializer._org_tenant, dict)  # pylint: disable=protected-access
        assert not serializer._org_tenant  # pylint: disable=protected-access
        assert serializer.get_org_tenants('org1') == [1, 2]
        assert serializer._org_tenant == {'org1': [1, 2]}  # pylint: disable=protected-access
        mock_get_tenants_by_org.assert_called_once()

        mock_get_tenants_by_org.reset_mock()
        assert serializer.get_org_tenants('org1') == [1, 2]
        mock_get_tenants_by_org.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize('role, is_valid_global_role', [
    ('support', True),
    ('staff', False),
])
def test_user_roles_serializer_for_global_roles(
    base_data, serializer_context, role, is_valid_global_role,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that the UserRolesSerializer correctly returns global role list"""
    user3 = get_user_model().objects.get(id=3)

    # create global role for user
    CourseAccessRole.objects.create(
        user_id=user3.id,
        role=role
    )
    serializer = UserRolesSerializer(user3, context=serializer_context)
    assert serializer.data.get('global_roles', []) == ([role] if is_valid_global_role else [])


@pytest.mark.django_db
def test_user_roles_serializer_for_global_roles_creator(
    base_data, serializer_context, empty_course_creator,
):  # pylint: disable=unused-argument, redefined-outer-name
    """
    Verify that the UserRolesSerializer does not report course-creator as a global role unless all related
    data are correctly filled.
    """
    user = get_user_model().objects.get(id=empty_course_creator.user_id)
    serializer = UserRolesSerializer(user, context=serializer_context)
    assert serializer.data.get('global_roles', []) == []

    CourseAccessRole.objects.create(
        user_id=user.id,
        role=cs.COURSE_CREATOR_ROLE_GLOBAL,
    )
    serializer = UserRolesSerializer(user, context=serializer_context)
    assert serializer.data.get('global_roles', []) == []

    CourseCreator.objects.filter(user_id=user.id).update(all_organizations=True)
    serializer = UserRolesSerializer(user, context=serializer_context)
    assert serializer.data.get('global_roles', []) == [cs.COURSE_CREATOR_ROLE_GLOBAL]


@pytest.mark.django_db
def test_user_roles_serializer_construct_roles_data(
    base_data, serializer_context
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that the construct_roles_data method correctly returns the roles data."""
    user3 = get_user_model().objects.get(id=3)
    user4 = get_user_model().objects.get(id=4)

    serializer = UserRolesSerializer(context=serializer_context)
    assert not serializer.roles_data

    serializer.construct_roles_data([user3, user4])
    assert serializer.roles_data == {
        3: {
            1: {
                'tenant_roles': ['staff'],
                'course_roles': {
                    'course-v1:ORG1+3+3': ['instructor'],
                    'course-v1:ORG1+4+4': ['instructor']
                }
            }
        },
        4: {
            1: {
                'tenant_roles': ['instructor'],
                'course_roles': {
                    'course-v1:ORG1+4+4': ['staff']
                }
            }
        }
    }


@pytest.mark.django_db
def test_user_roles_serializer_parse_query_params_defaults(
    base_data, serializer_context
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that the parse_query_params method correctly parses the query parameters."""
    assert UserRolesSerializer.parse_query_params({}) == {
        'search_text': '',
        'course_ids_filter': [],
        'roles_filter': [],
        'active_filter': None,
        'excluded_role_types': [],
        'include_hidden_roles': False,
    }


@pytest.mark.parametrize('excluded_role_types, result_excluded_role_types', [
    (None, []),
    ('', []),
    ('global', [RoleType.GLOBAL]),
    ('invalid,entry', []),
    ('tenant', [RoleType.ORG_WIDE]),
    ('course', [RoleType.COURSE_SPECIFIC]),
    ('global,course', [RoleType.COURSE_SPECIFIC, RoleType.GLOBAL]),
    ('tenant,course', [RoleType.ORG_WIDE, RoleType.COURSE_SPECIFIC]),
    ('global,tenant,course', [RoleType.ORG_WIDE, RoleType.COURSE_SPECIFIC, RoleType.GLOBAL]),
])
def test_user_roles_serializer_parse_query_params_values(excluded_role_types, result_excluded_role_types):
    """Verify that the parse_query_params method correctly parses the query parameters."""
    assert not DeepDiff(
        UserRolesSerializer.parse_query_params({
            'search_text': 'user99',
            'only_course_ids': 'course-v1:ORG99+88+88,another-course',
            'only_roles': 'staff,instructor',
            'active_users_filter': '1',
            'excluded_role_types': excluded_role_types,
            'include_hidden_roles': False,
        }),
        {
            'search_text': 'user99',
            'course_ids_filter': ['course-v1:ORG99+88+88', 'another-course'],
            'roles_filter': ['staff', 'instructor'],
            'active_filter': True,
            'excluded_role_types': result_excluded_role_types,
            'include_hidden_roles': False,
        },
        ignore_order=True,
    )


def test_read_only_serializer_create():
    """Verify that the ReadOnlySerializer does not allow creating objects."""
    serializer = ReadOnlySerializer(data={})
    with pytest.raises(ValueError) as exc_info:
        serializer.create({})
    assert str(exc_info.value) == 'This serializer is read-only and does not support object creation.'


def test_read_only_serializer_update():
    """Verify that the ReadOnlySerializer does not allow updating objects."""
    serializer = ReadOnlySerializer(data={})
    with pytest.raises(ValueError) as exc_info:
        serializer.update({}, {})
    assert str(exc_info.value) == 'This serializer is read-only and does not support object updates.'
