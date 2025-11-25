"""Test serializers for dashboard app"""
# pylint: disable=too-many-lines
import copy
import os
from unittest.mock import MagicMock, Mock, patch

import pytest
from cms.djangoapps.course_creators.models import CourseCreator
from common.djangoapps.student.models import CourseAccessRole, CourseEnrollment, SocialLink, UserProfile
from custom_reg_form.models import ExtraInfo
from deepdiff import DeepDiff
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Value
from django.test import override_settings
from django.utils import timezone
from django.utils.timezone import get_current_timezone, now, timedelta
from lms.djangoapps.grades.models import PersistentSubsectionGrade
from opaque_keys.edx.keys import UsageKey
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from openedx.core.djangoapps.user_api.accounts.serializers import AccountLegacyProfileSerializer
from rest_framework.exceptions import ValidationError
from social_django.models import UserSocialAuth
from xmodule.modulestore.exceptions import DuplicateCourseError

from futurex_openedx_extensions.dashboard import serializers
from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers.converters import dt_to_str
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
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


@pytest.fixture
def sso_external_id_context():
    """Create a context for testing."""
    queryset = CourseEnrollment.objects.filter(user_id=10, course_id='course-v1:ORG3+1+1').annotate(
        certificate_available=Value(True),
        course_score=Value(0.67),
        active_in_course=Value(True),
    )
    queryset[0].user.social_auth.create(
        provider='tpa-saml',
        uid='site_slug:whatever',
        extra_data={'test_uid': ['12345']}
    )
    context = {
        'course_id': 'course-v1:ORG3+1+1',
        'requested_optional_field_tags': ['sso_external_id']
    }
    with patch('futurex_openedx_extensions.dashboard.serializers.get_sso_sites') as mocked_get_sso_sites:
        mocked_get_sso_sites.return_value = {
            's2.sample.com': [{
                'slug': 'site_slug',
                'entity_id': 'testing_entity_id1',
            }]
        }
        yield queryset, context, mocked_get_sso_sites


@pytest.mark.django_db
def test_data_export_task_serializer_for_notes_max_len_limit(base_data):  # pylint: disable=unused-argument
    """Verify the DataExportSerializer for notes max len limit."""
    user = get_user_model().objects.get(id=10)
    task = DataExportTask.objects.create(filename='test.csv', view_name='test', user=user, tenant_id=1)
    data = {'notes': 'A' * 256}
    serializer = serializers.DataExportTaskSerializer(instance=task, data=data)
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
    serializer = serializers.DataExportTaskSerializer(instance=task, data={'notes': text_with_html_tags})
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
    serializer = serializers.DataExportTaskSerializer(
        instance=task, context={'requested_optional_field_tags': ['download_url']}
    )
    assert serializer.data['download_url'] == 'fake_download_url'


@pytest.mark.django_db
def test_learner_basic_details_serializer_no_profile(base_data):  # pylint: disable=unused-argument
    """Verify that the LearnerBasicDetailsSerializer is correctly defined."""
    queryset = get_dummy_queryset()
    data = serializers.LearnerBasicDetailsSerializer(queryset, many=True).data
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
    data = serializers.LearnerBasicDetailsSerializer(queryset, many=True).data
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
    data = serializers.LearnerBasicDetailsSerializer(queryset, many=True).data
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

    serializer = serializers.LearnerBasicDetailsSerializer(queryset, many=True)
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
    serializer = serializers.LearnerBasicDetailsSerializer(queryset, many=True)
    data = serializer.data
    assert len(data) == 1
    assert data[0]['user_id'] == 10
    assert data[0]['alternative_full_name'] == expected_alt_name, f'checking ({use_case}) failed'


@pytest.mark.django_db
def test_learner_details_serializer(base_data):  # pylint: disable=unused-argument
    """Verify that the LearnerDetailsSerializer returns the needed fields"""
    queryset = get_dummy_queryset()
    data = serializers.LearnerDetailsSerializer(queryset, many=True).data
    assert len(data) == 1
    assert data[0]['enrolled_courses_count'] == 6
    assert data[0]['certificates_count'] == 2


@pytest.mark.django_db
def test_course_score_and_certificate_serializer_for_required_child_methods():
    """Verify that the CourseScoreAndCertificateSerializer for required child methods"""
    class TestSerializer(serializers.CourseScoreAndCertificateSerializer):
        """Serializer for learner details for a course."""
        class Meta:
            model = get_user_model()
            fields = serializers.CourseScoreAndCertificateSerializer.Meta.fields

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
    serializer = serializers.LearnerEnrollmentSerializer(queryset, context={
        'course_id': 'course-v1:ORG3+1+1'
    }, many=True)
    mock_collect.assert_called_once()
    data = serializer.data
    assert len(data) == 1
    assert data[0]['certificate_available'] is True
    assert data[0]['course_score'] == 0.67
    assert data[0]['active_in_course'] is True


@pytest.mark.django_db
@patch('futurex_openedx_extensions.dashboard.serializers.import_from_path')
def test_learner_enrollments_serializer_for_sso_external_id(
    mocked_import_from_path, base_data, sso_external_id_context,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Ensure LearnerEnrollmentSerializer correctly processes sso_external_id based on social auth conditions."""
    def _dummy_processing(value):
        return 'processed_id'

    mocked_import_from_path.return_value = _dummy_processing
    queryset = sso_external_id_context[0]
    context = sso_external_id_context[1]

    def assert_sso_external_id(expected, msg):
        """Helper to serialize and assert sso_external_id."""
        serializer = serializers.LearnerEnrollmentSerializer(queryset, context=context, many=True)
        assert serializer.data[0].get('sso_external_id') == expected, msg

    UserSocialAuth.objects.all().delete()
    assert_sso_external_id('', 'sso_external_id should be empty when no social auth exists')

    uid = 'site_slug:whatever'

    queryset[0].user.social_auth.create(
        provider='other_provider',
        uid=uid,
        extra_data={'test_uid': 'an ID to be processed by external_id_extractor'}
    )
    assert_sso_external_id('', 'sso_external_id should be empty for an incorrect provider')
    mocked_import_from_path.assert_not_called()

    social_auth = queryset[0].user.social_auth.create(
        provider='tpa-saml',
        uid=uid,
        extra_data={'test_uid': 'an ID to be processed by external_id_extractor'}
    )
    assert_sso_external_id('processed_id', 'sso_external_id should be returned when the correct provider exists')

    mocked_import_from_path.reset_mock()
    mocked_import_from_path.return_value = _dummy_processing
    queryset[0].user.social_auth.create(
        provider='tpa-saml',
        uid='bad_uid',
        extra_data={'test_uid': 'this should be ignored because uid is bad'}
    )
    assert_sso_external_id('processed_id', 'sso_external_id should ignore incorrect UIDs, and return the correct one')

    mocked_import_from_path.reset_mock()
    mocked_import_from_path.return_value = _dummy_processing
    social_auth.extra_data = {}
    social_auth.save()
    assert_sso_external_id('', 'sso_external_id should empty when the external ID is not present')
    mocked_import_from_path.assert_not_called()

    social_auth.uid = 'other_site_slug:whatever'
    social_auth.extra_data = {'test_uid': 'should be ignored because the site slug is not the one we are looking for'}
    social_auth.save()
    assert_sso_external_id('', 'sso_external_id should be empty when no valid social auth exists')
    mocked_import_from_path.assert_not_called()


@pytest.mark.django_db
@patch('futurex_openedx_extensions.dashboard.serializers.import_from_path')
@pytest.mark.parametrize('key_to_remove, expected_result', [
    ('', '12345'),
    ('external_id_field', ''),
    ('external_id_extractor', ''),
])
def test_learner_enrollments_serializer_for_sso_external_id_bad_settings(
    mocked_import, key_to_remove, expected_result, base_data, sso_external_id_context, caplog,
):  # pylint: disable=unused-argument, redefined-outer-name, too-many-arguments
    """Verify that LearnerEnrollmentSerializer detects invalid FX_SSO_INFO settings."""
    def _dummy_processing(value):
        return '12345'

    mocked_import.return_value = _dummy_processing
    queryset = sso_external_id_context[0]
    context = sso_external_id_context[1]

    settings_override = copy.deepcopy(settings.FX_SSO_INFO)
    if key_to_remove:
        del settings_override['testing_entity_id1'][key_to_remove]
    with override_settings(FX_SSO_INFO=settings_override):
        serializer = serializers.LearnerEnrollmentSerializer(queryset, context=context, many=True)
        assert serializer.data[0].get('sso_external_id') == expected_result
    if key_to_remove:
        assert 'Bad (external_id_field) or (external_id_extractor) settings for Entity ID (testing_entity_id1)' \
            in caplog.text


@pytest.mark.django_db
@patch('futurex_openedx_extensions.dashboard.serializers.import_from_path')
def test_learner_enrollments_serializer_for_sso_external_id_import_failed(
    mocked_import, base_data, sso_external_id_context,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that LearnerEnrollmentSerializer handles import failure for external_id_extractor."""
    mocked_import.side_effect = ImportError('import failed')
    queryset = sso_external_id_context[0]
    context = sso_external_id_context[1]

    with pytest.raises(FXCodedException) as exc_info:
        _ = serializers.LearnerEnrollmentSerializer(queryset, context=context, many=True).data
    assert exc_info.value.code == FXExceptionCodes.BAD_CONFIGURATION_EXTERNAL_ID_EXTRACTOR.value
    assert str(exc_info.value) == \
        'Bad configuration: FX_SSO_INFO.testing_entity_id1.external_id_extractor. import failed'


@pytest.mark.django_db
@patch('futurex_openedx_extensions.dashboard.serializers.import_from_path')
def test_learner_enrollments_serializer_for_sso_external_id_extractor_exception(
    mocked_import, base_data, sso_external_id_context,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that LearnerEnrollmentSerializer return an empty string when external_id_extractor raises exception."""
    def none_failing_processing(value):
        return 'good'

    def _failing_processing(value):
        raise Exception('failed')

    queryset = sso_external_id_context[0]
    context = sso_external_id_context[1]

    mocked_import.return_value = none_failing_processing
    serializer = serializers.LearnerEnrollmentSerializer(queryset, context=context, many=True)
    assert serializer.data[0].get('sso_external_id') == 'good'

    mocked_import.return_value = _failing_processing
    serializer = serializers.LearnerEnrollmentSerializer(queryset, context=context, many=True)
    assert serializer.data[0].get('sso_external_id') == ''


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

    serializer = serializers.LearnerEnrollmentSerializer(queryset[0], context=context)
    data = serializer.data

    if is_course_id_in_context:
        assert 'earned - Homework 1: First Homework' in data.keys()
        assert 'earned - Homework 2: Second Homework' in data.keys()
    else:
        assert 'earned - Homework 1: First Homework' not in data.keys()
        assert 'earned - Homework 2: Second Homework' not in data.keys()


def test_learner_details_for_course_serializer_optional_fields():
    """Verify that the LearnerDetailsForCourseSerializer returns the correct optional fields."""
    serializer = serializers.LearnerDetailsForCourseSerializer(context={'course_id': 'course-v1:ORG2+1+1'})
    assert serializer.optional_field_names == ['progress', 'certificate_url', 'certificate_date', 'exam_scores']


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
    serializer = serializers.LearnerDetailsForCourseSerializer(
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
    serializer = serializers.LearnerDetailsForCourseSerializer(queryset, context={'course_id': 'course-v1:ORG2+1+1'})

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
    serializer = serializers.LearnerDetailsForCourseSerializer(
        queryset,
        context={
            'course_id': 'course-v1:ORG2+1+1',
            'requested_optional_field_tags': ['certificate_url'],
        },
        many=True,
    )
    assert serializer.data[0]['certificate_url'] == mock_get_certificate_url.return_value


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

    serializer = serializers.LearnerDetailsForCourseSerializer(
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
    data = serializers.LearnerDetailsExtendedSerializer(queryset, many=True, context={'request': request}).data
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
    data = serializers.LearnerDetailsExtendedSerializer(queryset, many=True).data
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
    data = serializers.LearnerDetailsExtendedSerializer(queryset, many=True).data
    assert len(data) == 1
    assert data[0]['user_id'] == 10
    assert data[0]['social_links'] == {'facebook': 'https://facebook.com/test'}


@pytest.mark.django_db
def test_learner_details_extended_serializer_image(base_data):  # pylint: disable=unused-argument
    """Verify that the LearnerDetailsExtendedSerializer returns the profile image."""
    queryset = get_dummy_queryset([1])
    profile = UserProfile.objects.create(user_id=1)
    data = serializers.LearnerDetailsExtendedSerializer(queryset, many=True).data
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
        data = serializers.CourseDetailsBaseSerializer(course).data

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

    data = serializers.CourseDetailsBaseSerializer(course).data
    assert data['status'] == expected_status

    course.self_paced = True
    course.save()
    data = serializers.CourseDetailsBaseSerializer(course).data
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
    data = serializers.CourseDetailsSerializer(course).data
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
    data = serializers.CourseDetailsSerializer(course).data
    assert data['rating'] == expected_rating


@pytest.mark.django_db
@patch('futurex_openedx_extensions.dashboard.serializers.CourseCategories')
@patch('futurex_openedx_extensions.dashboard.serializers.get_tenants_by_org')
def test_get_tenant_categories_returns_none_when_no_tenant(
    get_tenants_by_org_mock, course_categories_mock, base_data,
):  # pylint: disable=unused-argument
    """Verify get_tenant_categories returns None and does not cache when no tenant id."""
    get_tenants_by_org_mock.return_value = [None]

    serializer = serializers.CourseDetailsSerializer()
    course = CourseOverview.objects.first()
    result = serializer.get_tenant_categories(course)

    assert result is None
    assert serializer._tenant_categories == {}
    course_categories_mock.assert_not_called()


@pytest.mark.django_db
@patch('futurex_openedx_extensions.dashboard.serializers.CourseCategories')
@patch('futurex_openedx_extensions.dashboard.serializers.get_tenants_by_org')
def test_get_tenant_categories_caches_per_tenant(
    get_tenants_by_org_mock, course_categories_mock, base_data,
):  # pylint: disable=unused-argument
    """Verify get_tenant_categories creates and reuses a cached CourseCategories per tenant."""
    tenant_id = 'tenant-1'
    get_tenants_by_org_mock.return_value = [tenant_id]

    course_categories_instance = MagicMock(name='CourseCategoriesInstance')
    course_categories_mock.return_value = course_categories_instance

    serializer = serializers.CourseDetailsSerializer()
    course = CourseOverview.objects.first()

    result1 = serializer.get_tenant_categories(course)
    result2 = serializer.get_tenant_categories(course)

    assert result1 is course_categories_instance
    assert result2 is course_categories_instance
    course_categories_mock.assert_called_once_with(tenant_id)
    assert serializer._tenant_categories == {
        tenant_id: course_categories_instance,
    }


@pytest.mark.django_db
def test_get_categories_returns_empty_list_when_no_tenant_categories(base_data):  # pylint: disable=unused-argument
    """Verify get_categories returns an empty list when tenant_categories is falsy."""
    serializer = serializers.CourseDetailsSerializer()
    course = CourseOverview.objects.first()

    serializer.get_tenant_categories = MagicMock(return_value=None)

    result = serializer.get_categories(course)

    assert result == []


@pytest.mark.django_db
def test_get_categories_returns_keys_and_uses_str_id(base_data,):  # pylint: disable=unused-argument
    """Verify get_categories calls get_categories_for_course with str(obj.id) and returns its keys."""
    class FakeTenantCategories:
        def __init__(self):
            self.called_with = None

        def get_categories_for_course(self, course_id_arg):
            self.called_with = course_id_arg
            return {
                'cat_1': 'whatever',
                'cat_2': 'whatever',
            }

    fake_tenant_categories = FakeTenantCategories()

    serializer = serializers.CourseDetailsSerializer()
    course = CourseOverview.objects.first()

    serializer.get_tenant_categories = MagicMock(return_value=fake_tenant_categories)

    result = serializer.get_categories(course)

    assert fake_tenant_categories.called_with == str(course.id)
    assert result == ['cat_1', 'cat_2']


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

    request = Mock(site=Mock(), scheme='https')
    with patch(
        'futurex_openedx_extensions.dashboard.serializers.get_course_blocks_completion_summary',
        return_value=completion_summary,
    ):
        with patch(
            'futurex_openedx_extensions.dashboard.serializers.LearnerCoursesDetailsSerializer.get_certificate_url',
            return_value='https://s1.sample.com/courses/course-v1:dummy+key/certificate/'
        ):
            data = serializers.LearnerCoursesDetailsSerializer(course, context={'request': request}).data

    assert data['id'] == str(course.id)
    assert data['enrollment_date'] == dt_to_str(enrollment_date)
    assert data['last_activity'] == dt_to_str(last_activity)
    assert data['progress_url'] == \
           f'https://s1.sample.com/learning/course/{course.id}/progress/{course.related_user_id}/'
    assert data['grades_url'] == f'https://s1.sample.com/gradebook/{course.id}/'
    assert data['progress'] == completion_summary
    assert dict(data['grade']) == {
        'letter_grade': 'Fail',
        'percent': 0.4,
        'is_passing': False,
    }
    assert data['certificate_url'] == 'https://s1.sample.com/courses/course-v1:dummy+key/certificate/'


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
        serializer = serializers.UserRolesSerializer(user3, context=serializer_context)

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
        serializers.UserRolesSerializer(instance, context=serializer_context, many=many)

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
        serializer = serializers.UserRolesSerializer(user3, context=serializer_context)

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
    serializer = serializers.UserRolesSerializer(user3, context=serializer_context)
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
    serializer = serializers.UserRolesSerializer(user, context=serializer_context)
    assert serializer.data.get('global_roles', []) == []

    CourseAccessRole.objects.create(
        user_id=user.id,
        role=cs.COURSE_CREATOR_ROLE_GLOBAL,
    )
    serializer = serializers.UserRolesSerializer(user, context=serializer_context)
    assert serializer.data.get('global_roles', []) == []

    CourseCreator.objects.filter(user_id=user.id).update(all_organizations=True)
    serializer = serializers.UserRolesSerializer(user, context=serializer_context)
    assert serializer.data.get('global_roles', []) == [cs.COURSE_CREATOR_ROLE_GLOBAL]


@pytest.mark.django_db
def test_user_roles_serializer_construct_roles_data(
    base_data, serializer_context
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that the construct_roles_data method correctly returns the roles data."""
    user3 = get_user_model().objects.get(id=3)
    user4 = get_user_model().objects.get(id=4)

    serializer = serializers.UserRolesSerializer(context=serializer_context)
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
    assert serializers.UserRolesSerializer.parse_query_params({}) == {
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
        serializers.UserRolesSerializer.parse_query_params({
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
    serializer = serializers.ReadOnlySerializer(data={})
    with pytest.raises(ValueError) as exc_info:
        serializer.create({})
    assert str(exc_info.value) == 'This serializer is read-only and does not support object creation.'


def test_read_only_serializer_update():
    """Verify that the ReadOnlySerializer does not allow updating objects."""
    serializer = serializers.ReadOnlySerializer(data={})
    with pytest.raises(ValueError) as exc_info:
        serializer.update({}, {})
    assert str(exc_info.value) == 'This serializer is read-only and does not support object updates.'


@pytest.mark.parametrize('context, expected_error', [
    ({'request': Mock(fx_permission_info={'view_allowed_tenant_ids_full_access': [1, 2]})}, None),
    ({'request': Mock(fx_permission_info={})}, None),
    ({'request': Mock(spec=object)}, 'fx_permission_info is missing in the request context of the serializer!'),
    ({}, 'Unable to load fx_permission_info as request object is missing.'),
])
def test_fx_permission_info_serializer_mixin(context, expected_error):
    """
    Verify that the FxPermissionInfoSerializerMixin correctly reads fx_permission_info from context and raises an
    error if the something is missing.
    """
    class TestSerializer(
        serializers.FxPermissionInfoSerializerMixin,
        serializers.serializers.Serializer,
    ):  # pylint: disable=abstract-method
        """Test serializer to check fx_permission_info handling."""
        test_field = serializers.serializers.CharField()

    serializer = TestSerializer(data={'test_field': 'test_value'}, context=context)
    if expected_error:
        with pytest.raises(ValidationError) as exc_info:
            _ = serializer.fx_permission_info
        assert expected_error in str(exc_info.value)
    else:
        assert serializer.fx_permission_info == context['request'].fx_permission_info


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_id, allowed_tenants, expected_error', [
    (1, [1], None),
    (99, [1], 'Tenant with ID 99 does not exist.'),
    (1, [4], 'User does not have have required access for tenant (1).'),
])
def test_file_upload_serializer(tenant_id, allowed_tenants, expected_error):
    """Test validation of tenant_id in FileUploadSerializer"""
    request = None
    request = Mock(fx_permission_info={'view_allowed_tenant_ids_full_access': allowed_tenants})

    file_data = SimpleUploadedFile('test.png', b'file_content', content_type='image/png')
    serializer = serializers.FileUploadSerializer(
        data={'file': file_data, 'slug': 'test-slug', 'tenant_id': tenant_id}, context={'request': request})

    if expected_error:
        with pytest.raises(ValidationError):
            assert not serializer.is_valid(raise_exception=True)
        assert serializer.errors['tenant_id'][0] == expected_error
    else:
        assert serializer.is_valid()
        assert serializer.validated_data['tenant_id'] == tenant_id


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_id, allowed_tenants, payload_file, expected_error, error_key', [
    (1, [1], 'test.png', None, None),
    (1, [1], 'test.invalid', f'Invalid file type. Allowed types are {cs.ALLOWED_FILE_EXTENSIONS}.', 'file'),
    (1, [4], 'test.png', 'User does not have have required access for tenant (1).', 'tenant_id'),
])
def test_tenant_asset_serializer(
    tenant_id, allowed_tenants, payload_file, expected_error, error_key, base_data
):  # pylint: disable=unused-argument, too-many-arguments
    """Test validation of tenant_id in FileUploadSerializer"""
    request = None
    request = Mock(
        fx_permission_info={
            'view_allowed_tenant_ids_full_access': allowed_tenants,
            'is_system_staff_user': False,
        }
    )

    file_data = SimpleUploadedFile(payload_file, b'file_content', content_type='image/png')
    serializer = serializers.TenantAssetSerializer(
        data={'file': file_data, 'slug': 'test-slug', 'tenant_id': tenant_id}, context={'request': request}
    )

    if expected_error:
        with pytest.raises(ValidationError):
            assert not serializer.is_valid(raise_exception=True)
        assert serializer.errors[error_key][0] == expected_error
    else:
        assert serializer.is_valid()
        assert serializer.validated_data['tenant'].id == tenant_id


@pytest.mark.django_db
@pytest.mark.parametrize('is_system_staff, expected_allow, use_case', [
    (False, False, 'Non system staff user cannot create asset in the template tenant'),
    (True, True, 'System staff user can create asset in the template tenant'),
])
def test_tenant_asset_serializer_allow_template_tenant_id(
    is_system_staff, expected_allow, use_case, base_data, template_tenant,
):  # pylint: disable=unused-argument
    """Test that TenantAssetSerializer allows tenant_id to be None for template assets."""
    accessible_tenants = [1, 2]
    assert template_tenant.id not in accessible_tenants, 'bad test data'

    request = Mock(fx_permission_info={
        'is_system_staff_user': is_system_staff, 'view_allowed_tenant_ids_full_access': accessible_tenants,
    })
    file_data = SimpleUploadedFile('test.png', b'file_content', content_type='image/png')
    serializer = serializers.TenantAssetSerializer(
        data={
            'file': file_data,
            'slug': 'test-slug',
            'tenant_id': template_tenant.id,
        },
        context={'request': request},
    )

    assert expected_allow == serializer.is_valid(), use_case


@pytest.mark.django_db
@pytest.mark.parametrize('is_superuser, slug, expected_error', [
    (False, 'test-slug', None),
    (True, 'test-slug', None),
    (False, '_test-slug', 'Slug cannot start with an underscore unless the user is a system staff.'),
    (True, '_test-slug', None),
])
def test_tenant_asset_serializer_slug_validation(
    base_data, is_superuser, slug, expected_error,
):  # pylint: disable=unused-argument
    """Validate that only superusers and staff can create assets with slugs that start with '_'."""
    user = get_user_model().objects.get(id=1)
    user.is_superuser = is_superuser
    user.save()

    fx_permission_info = {
        'is_system_staff_user': is_superuser,
        'view_allowed_tenant_ids_full_access': [1],
    }

    request = Mock(user=user, fx_permission_info=fx_permission_info)
    file_data = SimpleUploadedFile('test.png', b'file_content', content_type='image/png')
    serializer = serializers.TenantAssetSerializer(
        data={'file': file_data, 'slug': slug, 'tenant_id': 1}, context={'request': request}
    )

    if expected_error:
        with pytest.raises(ValidationError):
            assert not serializer.is_valid(raise_exception=True)
        assert serializer.errors['slug'][0] == expected_error
    else:
        assert serializer.is_valid()


@pytest.mark.django_db
def test_tenant_asset_serializer_for_create_or_update():
    """Test create or update of serializer - when user tries to recreate existing tenant-slug asset."""
    fake_perm_info = {
        'view_allowed_tenant_ids_full_access': [1],
        'is_system_staff_user': False,
    }
    user1 = get_user_model().objects.get(id=1)
    user2 = get_user_model().objects.get(id=2)

    file1 = SimpleUploadedFile('file1.png', b'file content 1', content_type='image/png')
    file2 = SimpleUploadedFile('file2.png', b'file content 2', content_type='image/png')

    request = Mock(fx_permission_info=fake_perm_info, user=user1)
    serializer = serializers.TenantAssetSerializer(
        data={'file': file1, 'slug': 'test-slug', 'tenant_id': 1}, context={'request': request}
    )
    assert serializer.is_valid()
    returned_asset1 = serializer.save()
    assert returned_asset1.updated_by == user1

    request = Mock(fx_permission_info=fake_perm_info, user=user2)
    serializer = serializers.TenantAssetSerializer(
        data={'file': file2, 'slug': 'test-slug', 'tenant_id': 1}, context={'request': request}
    )
    assert serializer.is_valid()
    returned_asset2 = serializer.save()
    assert returned_asset2.updated_by == user2

    assert returned_asset1.id == returned_asset2.id
    assert returned_asset1.tenant.id == returned_asset2.tenant.id
    assert returned_asset1.slug == returned_asset2.slug

    assert returned_asset1.updated_by != returned_asset2.updated_by
    assert returned_asset1.updated_at != returned_asset2.updated_at
    assert returned_asset1.file.url != returned_asset2.file.url
    assert returned_asset1.file.name != returned_asset2.file.name

    default_storage.delete(returned_asset1.file.name)
    default_storage.delete(returned_asset2.file.name)
    os.rmdir('test_dir/1/config_files')


def test_library_serializer_update_raises_error():
    """test library serializer for update """
    serializer = serializers.LibrarySerializer()
    with pytest.raises(ValueError, match='This serializer does not support update.'):
        serializer.update(instance=object(), validated_data={})


@pytest.mark.parametrize('input_data, expected_output, test_case', [
    (
        {
            'values': {'theme_v2': {'header': 'data'}},
            'not_permitted': ['x', 'y'],
            'bad_keys': ['bad'],
            'revision_ids': {'theme_v2.header': 12345678901234567890}
        },
        {
            'values': {'theme_v2': {'header': 'data'}},
            'not_permitted': ['x', 'y'],
            'bad_keys': ['bad'],
            'revision_ids': {'theme_v2.header': '12345678901234567890'}
        },
        'converts revision_ids to strings'
    ),
    (
        {
            'values': {},
            'not_permitted': [],
            'bad_keys': [],
            'revision_ids': {}
        },
        {
            'values': {},
            'not_permitted': [],
            'bad_keys': [],
            'revision_ids': {}
        },
        'empty values with empty revision_ids'
    ),
    (
        {
            # omit revision_ids field entirely
            'values': {'test': 1},
            'not_permitted': [],
            'bad_keys': [],
        },
        {
            'values': {'test': 1},
            'not_permitted': [],
            'bad_keys': [],
            'revision_ids': {}
        },
        'missing revision_ids field should return empty dict'
    ),
])
def test_tenant_config_serializer(input_data, expected_output, test_case):
    """Verify TenantConfigSerializer serializes correctly with revision_ids as strings"""
    serializer = serializers.TenantConfigSerializer(instance=input_data)
    assert serializer.data == expected_output, test_case


def test_course_serializer_update_raises_error():
    """test CourseCreate serializer for update """
    serializer = serializers.CourseCreateSerializer()
    with pytest.raises(ValueError, match='This serializer does not support update.'):
        serializer.update(instance=object(), validated_data={})


@pytest.fixture
def valid_tenants():
    """Fixture to provide valid tenants for testing."""
    return {
        'default_org_per_tenant': {
            1: 'testorg',
        }
    }


@pytest.fixture
def valid_org_map():
    """Fixture to provide a valid organization map."""
    return {
        'testorg': [1],
    }


@pytest.fixture(autouse=True)
def fx_allowed_course_language_codes(settings):  # pylint: disable=redefined-outer-name
    """Fixture to set FX_ALLOWED_COURSE_LANGUAGE_CODES in settings."""
    settings.FX_ALLOWED_COURSE_LANGUAGE_CODES = ['en', 'ar']
    return settings


@pytest.fixture
def course_data():
    """Fixture to provide valid course data for testing."""
    time_now = timezone.now()
    return {
        'tenant_id': 1,
        'number': 'CS101',
        'run': '2023_Fall',
        'display_name': 'Test Course',
        'start': time_now,
        'end': time_now,
        'enrollment_start': time_now,
        'enrollment_end': time_now,
        'self_paced': True,
        'invitation_only': False,
        'language': 'en',
    }


@pytest.mark.parametrize(
    'tenant_id, org_map, expected_error, test_case',
    [
        (2, {'default_org_per_tenant': {1: 'testorg'}}, 'Invalid tenant_id', 'tenant_id not in default_orgs'),
        (1, {'default_org_per_tenant': {1: ''}}, 'No default organization', 'default_org empty'),
        (1, {'default_org_per_tenant': {1: 'testorg'}}, 'Invalid default organization', 'org/tenant mapping missing'),
    ]
)
def test_validate_tenant_id_errors(tenant_id, org_map, expected_error, test_case):
    """Verify tenant_id validation error handling for various misconfigurations."""
    serializer = serializers.CourseCreateSerializer()
    with patch('futurex_openedx_extensions.dashboard.serializers.get_all_tenants_info', return_value=org_map), \
         patch('futurex_openedx_extensions.dashboard.serializers.get_org_to_tenant_map', return_value={}):
        with pytest.raises(ValidationError) as exc:
            serializer.validate_tenant_id(tenant_id)
        assert expected_error in str(exc.value), test_case


@pytest.mark.parametrize(
    'number, should_pass, test_case',
    [
        ('CS101', True, 'valid'),
        ('cs-1_23', True, 'valid with underscore/hyphen'),
        ('cs!@#', False, 'invalid chars'),
        ('cs 123', False, 'space not allowed'),
    ]
)
def test_validate_number(number, should_pass, test_case):
    """Verify number field validation for allowed/disallowed patterns."""
    serializer = serializers.CourseCreateSerializer()
    if should_pass:
        assert serializer.validate_number(number) == number, test_case
    else:
        with pytest.raises(ValidationError, match='Invalid number'):
            serializer.validate_number(number)


@pytest.mark.parametrize(
    'run, should_pass, test_case',
    [
        ('2024_Fall', True, 'valid'),
        ('run-1', True, 'valid hyphen'),
        ('run!', False, 'invalid character'),
        ('run 1', False, 'space not allowed'),
    ]
)
def test_validate_run(run, should_pass, test_case):
    """Verify run field validation for allowed/disallowed patterns."""
    serializer = serializers.CourseCreateSerializer()
    if should_pass:
        assert serializer.validate_run(run) == run, test_case
    else:
        with pytest.raises(ValidationError, match='Invalid run'):
            serializer.validate_run(run)


@pytest.mark.parametrize(
    'default_org, number, run, should_raise, test_case',
    [
        ('a' * 10, 'b' * 10, 'c' * 10, False, 'max length ok'),
        ('a', 'b', 'c', False, 'very short'),
        ('a' * 100, 'b' * 100, 'c' * 100, True, 'exceeding max'),
    ]
)
def test_validate_course_id_length(default_org, number, run, should_raise, test_case):
    """Verify course ID total length constraint."""
    serializer = serializers.CourseCreateSerializer()
    serializer._default_org = default_org  # pylint: disable=protected-access
    attrs = {'number': number, 'run': run}
    max_len = serializers.CourseCreateSerializer.MAX_COURSE_ID_LENGTH
    if should_raise:
        with pytest.raises(
            ValidationError,
            match=f'Course ID is too long. The maximum length is {max_len} characters.',
        ):
            serializer.validate(attrs)
    else:
        assert serializer.validate(attrs) == attrs, test_case


@pytest.mark.parametrize(
    'dates, should_raise, test_case',
    [
        ({'start': timezone.now(), 'end': timezone.now() - timezone.timedelta(days=1)}, True, 'end before start'),
        (
            {
                'enrollment_start': timezone.now(),
                'enrollment_end': timezone.now() - timezone.timedelta(days=2)
            },
            True,
            'enrollment_end before enrollment_start',
        ),
        (
            {
                'start': timezone.now(),
                'enrollment_start': timezone.now() + timezone.timedelta(days=1)
            },
            True,
            'start before enrollment_start',
        ),
        (
            {
                'end': timezone.now(),
                'enrollment_end': timezone.now() + timezone.timedelta(days=1)
            },
            True,
            'end before enrollment_end',
        ),
        ({'start': timezone.now(), 'end': timezone.now() + timezone.timedelta(days=1)}, False, 'valid dates'),
    ]
)
def test_validate_dates(dates, should_raise, test_case):
    """Verify date validation rules between fields."""
    serializer = serializers.CourseCreateSerializer()
    serializer._default_org = 'org'  # pylint: disable=protected-access
    attrs = {'number': 'num', 'run': 'run'}
    attrs.update(dates)
    if should_raise:
        with pytest.raises(ValidationError) as exc:
            serializer.validate(attrs)
        assert 'cannot be before' in str(exc.value), test_case
    else:
        assert serializer.validate(attrs) == attrs, test_case


def test_get_absolute_url_requires_default_org(course_data):  # pylint: disable=redefined-outer-name
    """Verify get_absolute_url requires ._default_org set."""
    serializer = serializers.CourseCreateSerializer()
    serializer._validated_data = course_data  # pylint: disable=protected-access
    serializer._default_org = ''  # pylint: disable=protected-access
    with pytest.raises(ValidationError, match='Default organization is not set. Call validate_tenant_id first.'):
        serializer.get_absolute_url()


@patch('futurex_openedx_extensions.dashboard.serializers.relative_url_to_absolute_url')
@patch('futurex_openedx_extensions.dashboard.serializers.set_request_domain_by_org')
def test_get_absolute_url_success(
    _, mock_get_url, course_data,
):  # pylint: disable=redefined-outer-name
    """Verify get_absolute_url builds the correct URL."""
    serializer = serializers.CourseCreateSerializer(context={'request': MagicMock()})
    serializer._validated_data = course_data  # pylint: disable=protected-access
    serializer._default_org = 'org'  # pylint: disable=protected-access
    mock_get_url.return_value = 'the url'
    result_url = serializer.get_absolute_url()
    assert result_url == 'the url'


def test_update_not_implemented(course_data):  # pylint: disable=redefined-outer-name
    """Verify update() always raises ValueError."""
    serializer = serializers.CourseCreateSerializer()
    with pytest.raises(ValueError, match='does not support update'):
        serializer.update(MagicMock(), course_data)


@pytest.mark.django_db
@patch('futurex_openedx_extensions.dashboard.serializers.get_all_tenants_info')
@patch('futurex_openedx_extensions.dashboard.serializers.ensure_organization')
@patch('futurex_openedx_extensions.dashboard.serializers.add_organization_course')
@patch('futurex_openedx_extensions.dashboard.serializers.get_org_to_tenant_map')
@patch('futurex_openedx_extensions.dashboard.serializers.modulestore')
@patch('futurex_openedx_extensions.dashboard.serializers.CourseCreateSerializer.add_roles_and_permissions')
@patch('futurex_openedx_extensions.dashboard.serializers.CourseCreateSerializer.update_course_discussions_settings')
def test_create_success(
    _,
    __,
    mock_modulestore,
    mock_get_org_to_tenant_map,
    mock_add_organization_course,
    mock_ensure_organization,
    mock_get_all_tenants_info,
    course_data,
    valid_tenants,
    valid_org_map,
):  # pylint: disable=redefined-outer-name,too-many-arguments
    """Verify successful course creation, with all external calls patched."""
    serializer = serializers.CourseCreateSerializer(context={'request': MagicMock(user=MagicMock(id=123))})

    mock_get_all_tenants_info.return_value = valid_tenants
    mock_ensure_organization.return_value = {'org': 'org'}
    mock_add_organization_course.return_value = None
    mock_get_org_to_tenant_map.return_value = valid_org_map

    mock_modulestore_instance = MagicMock()
    mock_modulestore_instance.default_modulestore.get_modulestore_type.return_value = 'type'
    mock_modulestore_instance.default_store.return_value.__enter__.return_value = None
    created_course = MagicMock()
    mock_modulestore_instance.create_course.return_value = created_course
    mock_modulestore.return_value = mock_modulestore_instance

    result = serializer.create(course_data)
    assert result == created_course, 'new course returned'


@pytest.mark.django_db
@patch('futurex_openedx_extensions.dashboard.serializers.get_all_tenants_info')
@patch('futurex_openedx_extensions.dashboard.serializers.ensure_organization')
@patch('futurex_openedx_extensions.dashboard.serializers.add_organization_course')
@patch('futurex_openedx_extensions.dashboard.serializers.get_org_to_tenant_map')
@patch('futurex_openedx_extensions.dashboard.serializers.modulestore')
@patch('futurex_openedx_extensions.dashboard.serializers.CourseCreateSerializer.add_roles_and_permissions')
@patch('futurex_openedx_extensions.dashboard.serializers.CourseCreateSerializer.update_course_discussions_settings')
def test_create_duplicate_course_error(
    _,
    __,
    mock_modulestore,
    mock_get_org_to_tenant_map,
    mock_add_organization_course,
    mock_ensure_organization,
    mock_get_all_tenants_info,
    course_data,
    valid_tenants,
    valid_org_map,
):  # pylint: disable=too-many-arguments,redefined-outer-name
    """Verify DuplicateCourseError during create raises ValidationError."""
    serializer = serializers.CourseCreateSerializer(context={'request': MagicMock(user=MagicMock(id=123))})

    mock_get_all_tenants_info.return_value = valid_tenants
    mock_ensure_organization.return_value = {'org': 'org'}
    mock_add_organization_course.return_value = None
    mock_get_org_to_tenant_map.return_value = valid_org_map

    mock_modulestore_instance = MagicMock()
    mock_modulestore_instance.default_modulestore.get_modulestore_type.return_value = 'type'
    mock_modulestore_instance.default_store.return_value.__enter__.return_value = None
    mock_modulestore_instance.create_course.side_effect = DuplicateCourseError('Course already exists')
    mock_modulestore.return_value = mock_modulestore_instance

    with pytest.raises(ValidationError, match='already exists'):
        serializer.create(course_data)


@pytest.mark.django_db
@patch('futurex_openedx_extensions.dashboard.serializers.get_all_tenants_info')
@patch('futurex_openedx_extensions.dashboard.serializers.ensure_organization')
@patch('futurex_openedx_extensions.dashboard.serializers.get_org_to_tenant_map')
@patch('futurex_openedx_extensions.dashboard.serializers.DuplicateCourseError', Exception)
def test_create_organization_missing_raises_validation_error(
    mock_get_org_to_tenant_map,
    mock_ensure_organization,
    mock_get_all_tenants_info,
    course_data,
    valid_tenants,
    valid_org_map,
):  # pylint: disable=too-many-arguments, redefined-outer-name
    """Verify create() raises ValidationError if ensure_organization fails."""
    serializer = serializers.CourseCreateSerializer(context={'request': MagicMock(user=MagicMock(id=123))})

    mock_get_all_tenants_info.return_value = valid_tenants
    mock_ensure_organization.side_effect = Exception('no org')
    mock_get_org_to_tenant_map.return_value = valid_org_map

    with pytest.raises(
        ValidationError,
        match='Organization does not exist. Please add the organization before proceeding.'
    ):
        serializer.create(course_data)


def test_category_serializer_category_context_missing():
    """Verify that CategorySerializer raises error if 'categories' missing in context."""
    with pytest.raises(ValidationError) as exc_info:
        serializers.CategorySerializer(context={'request': MagicMock(method='GET')})
    assert 'categories dictionary is missing from context' in str(exc_info)


def test_category_serializer_no_full_access():
    """Verify that CategorySerializer raises error if user lacks full access."""
    request = Mock(fx_permission_info={
        'view_allowed_tenant_ids_full_access': [],
    })
    serializer_context = {'request': request, 'categories': {}}

    serializer = serializers.CategorySerializer(
        data={
            'label': {'en': 'Category 1'},
            'tenant_id': 1,
        },
        context=serializer_context,
    )
    with pytest.raises(ValidationError) as exc_info:
        serializer.is_valid(raise_exception=True)
    assert 'User does not have required access for tenant (1)' in str(exc_info)


def test_category_serializer_update_not_implemented():
    """Verify that CategorySerializer update() raises ValueError."""
    serializer = serializers.CategorySerializer()
    with pytest.raises(ValueError, match='This serializer does not support update.'):
        serializer.update(instance=object(), validated_data={})


def test_categories_order_serializer_no_full_access():
    """Verify that CategoriesOrderSerializer raises error if user lacks full access."""
    request = Mock(fx_permission_info={
        'view_allowed_tenant_ids_full_access': [],
    })
    serializer_context = {'request': request, 'categories': {}}

    serializer = serializers.CategoriesOrderSerializer(
        data={
            'label': {'en': 'Category 1'},
            'tenant_id': 1,
        },
        context=serializer_context,
    )
    with pytest.raises(ValidationError) as exc_info:
        serializer.is_valid(raise_exception=True)
    assert 'User does not have required access for tenant (1)' in str(exc_info)
