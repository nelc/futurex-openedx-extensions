"""Tests for learner details collectors"""
from unittest.mock import Mock, patch

import pytest
from common.djangoapps.student.models import CourseEnrollment
from django.contrib.auth import get_user_model
from lms.djangoapps.grades.models import PersistentCourseGrade

from futurex_openedx_extensions.dashboard.details.learners import (
    get_certificates_count_for_learner_queryset,
    get_courses_count_for_learner_queryset,
    get_learner_info_queryset,
    get_learners_by_course_queryset,
    get_learners_enrollments_queryset,
    get_learners_queryset,
)
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from tests.fixture_helpers import get_tenants_orgs


@pytest.mark.django_db
@pytest.mark.parametrize('function_to_test, username, expected_count, assert_error_message', [
    ('courses', 'user4', 0, 'user4 should report zero courses in ORG1 and ORG2 because of being an org admin'),
    ('certificates', 'user4', 2, 'user4 should report all certificates regardless of being an org admin'),
    ('courses', 'user3', 1, 'user3 should report courses in ORG2 but not ORG1 because of course access role'),
    ('certificates', 'user3', 1, 'user3 should report all certificates regardless of course access role'),
    ('courses', 'user5', 2, 'user5 should report all courses in ORG1 and ORG2'),
    ('certificates', 'user5', 1, 'user5 should report all certificates regardless of course access role'),
])
def test_count_for_learner_queryset(
    base_data, fx_permission_info, function_to_test, username, expected_count, assert_error_message
):  # pylint: disable=unused-argument, too-many-arguments
    """
    Verify that get_certificates_count_for_learner_queryset and get_courses_count_for_learner_queryset
    return the correct QuerySet.
    """
    assert function_to_test in ['courses', 'certificates'], f'bad test data (function_to_test = {function_to_test})'

    queryset = get_user_model().objects.filter(username=username)
    assert queryset.count() == 1, f'bad test data (username = {username})'

    if function_to_test == 'courses':
        fnc = get_courses_count_for_learner_queryset
    else:
        fnc = get_certificates_count_for_learner_queryset
    queryset = get_user_model().objects.filter(username=username).annotate(
        result=fnc(fx_permission_info)
    )

    assert queryset.first().result == expected_count, f'{assert_error_message}. Check the test data for details.'


@pytest.mark.django_db
@pytest.mark.parametrize('username, expected_count', [
    ('user4', 4),
    ('user3', 3),
])
def test_get_courses_count_for_learner_queryset_with_staff(
    base_data, fx_permission_info, username, expected_count
):  # pylint: disable=unused-argument
    """
    Verify that get_certificates_count_for_learner_queryset and get_courses_count_for_learner_queryset
    return the correct QuerySet.
    """
    queryset = get_user_model().objects.filter(username=username)
    assert queryset.count() == 1, f'bad test data (username = {username})'

    queryset = get_user_model().objects.filter(username=username).annotate(
        result=get_courses_count_for_learner_queryset(fx_permission_info, include_staff=True)
    )

    assert queryset.first().result == expected_count


@pytest.mark.django_db
def test_get_courses_count_for_learner_queryset_inactive_enrollment(
    base_data, fx_permission_info
):  # pylint: disable=unused-argument
    """Verify that get_courses_count_for_learner_queryset returns the correct QuerySet for inactive enrollments."""
    user_id = 5
    queryset = get_user_model().objects.filter(id=user_id).annotate(
        result=get_courses_count_for_learner_queryset(fx_permission_info)
    )
    assert queryset.first().result == 2, 'bad test data, user5 should have 2 enrollments'
    enrollment = CourseEnrollment.objects.filter(user_id=5).first()
    enrollment.is_active = False
    enrollment.save()
    assert queryset.first().result == 1, 'inactive enrollments should be counted'


@pytest.mark.django_db
def test_get_learner_info_queryset(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify that get_learner_info_queryset returns the correct QuerySet."""
    user_id = 21
    queryset = get_learner_info_queryset(fx_permission_info, user_id)
    assert queryset.count() == 1, 'bad test data, user id (3) should be in the queryset'

    info = queryset.first()
    assert info.id == user_id, 'invalid data fetched!'
    assert hasattr(info, 'courses_count'), 'courses_count should be in the queryset'
    assert hasattr(info, 'certificates_count'), 'certificates_count should be in the queryset'


@pytest.mark.django_db
def test_get_learner_info_queryset_selecting_profile(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify that get_learner_info_queryset returns the correct QuerySet along with the related profile record."""
    with patch('django.db.models.query.QuerySet.select_related') as mocked_select_related:
        get_learner_info_queryset(fx_permission_info, 21)
    mocked_select_related.assert_called_once_with('profile')


@pytest.mark.django_db
def test_get_learner_info_queryset_invalid_user(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify that get_learner_info_queryset raises an exception for an invalid user."""
    with pytest.raises(FXCodedException) as exc_info:
        get_learner_info_queryset(fx_permission_info, 'invalid_user')
    assert exc_info.value.code == FXExceptionCodes.USER_NOT_FOUND.value


@pytest.mark.django_db
def test_get_learner_info_queryset_not_permitted(base_data):  # pylint: disable=unused-argument
    """Verify that get_learner_info_queryset raises an exception when the user is not permitted."""
    user_id = 21
    fx_permission_info = {
        'is_system_staff_user': False,
        'user': get_user_model().objects.get(id=3),
        'view_allowed_full_access_orgs': [],
        'view_allowed_course_access_orgs': ['org1', 'org2'],
        'view_allowed_any_access_orgs': ['org1', 'org2'],
        'view_allowed_tenant_ids_full_access': [],
        'view_allowed_tenant_ids_any_access': [1],
        'view_allowed_tenant_ids_partial_access': [1],
        'view_allowed_roles': ['staff'],
        'user_roles': {'staff': {'course_limited_access': ['course-v1:ORG1+5+5']}},
    }
    assert get_learner_info_queryset(fx_permission_info, user_id).count() == 1

    fx_permission_info['user_roles']['staff']['course_limited_access'] = ['course-v1:ORG1+3+3']
    with pytest.raises(FXCodedException) as exc_info:
        get_learner_info_queryset(fx_permission_info, user_id)
    assert exc_info.value.code == FXExceptionCodes.USER_QUERY_NOT_PERMITTED.value
    assert str(exc_info.value) == f'Caller (user3) is not permitted to query user (user{user_id}).'


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_ids, expected_count_with_staff, expected_count_without_staff', [
    ([7, 8], 26, 24),
    ([7], 20, 18),
])
def test_get_learners_queryset(
    base_data, fx_permission_info, tenant_ids, expected_count_with_staff, expected_count_without_staff,
):  # pylint: disable=unused-argument
    """Verify that get_learners_queryset returns the correct QuerySet."""
    fx_permission_info['is_system_staff_user'] = False
    fx_permission_info['user'] = Mock(id=3)
    fx_permission_info['view_allowed_full_access_orgs'] = get_tenants_orgs(tenant_ids)
    fx_permission_info['view_allowed_tenant_ids_full_access'] = tenant_ids
    fx_permission_info['view_allowed_tenant_ids_partial_access'] = []
    fx_permission_info['view_allowed_roles'] = ['staff']
    fx_permission_info['user_roles'] = {'staff': {'course_limited_access': []}}

    result = get_learners_queryset(fx_permission_info, include_staff=True)
    assert result.count() == expected_count_with_staff
    assert result.first().courses_count is not None, 'courses_count should be in the queryset'
    assert result.first().certificates_count is not None, 'certificates_count should be in the queryset'

    result = get_learners_queryset(fx_permission_info)
    assert result.count() == expected_count_without_staff


@pytest.mark.django_db
@pytest.mark.parametrize('enrollments_filter, expected_error_message', [
    ('not tuple or list', 'Enrollments filter must be a tuple or a list.'),
    ((1, 2, 3), 'Enrollments filter must be a tuple or a list of two integer values.'),
    ((1.0, 2), 'Enrollments filter must be a tuple or a list of two integer values.'),
])
def test_test_get_learners_queryset_enrollments_filter_invalid(
    base_data, fx_permission_info, enrollments_filter, expected_error_message,
):  # pylint: disable=unused-argument
    """Verify that get_learners_queryset raises an exception for an invalid enrollments filter."""
    with pytest.raises(FXCodedException) as exc_info:
        get_learners_queryset(
            fx_permission_info=fx_permission_info,
            enrollments_filter=enrollments_filter,
        )
    assert str(exc_info.value) == expected_error_message


@pytest.mark.django_db
@pytest.mark.parametrize('enrollments_filter, expected_ids', [
    ((-1, -1), [5, 15, 21, 22, 23, 24, 25, 28, 29, 30, 31, 32, 38, 39, 40, 41]),
    ((2, -1), [5, 15, 21, 22, 23, 24, 25, 40]),
    ((-1, 2), [5, 15, 22, 23, 24, 25, 28, 29, 30, 31, 32, 38, 39, 40, 41]),
    ((2, 2), [5, 15, 22, 23, 24, 25, 40]),
    ((3, 3), [21]),
    ((3, 100), [21]),
    ((4, 100), []),
    ((100, 3), []),
])
def test_test_get_learners_queryset_enrollments_filter(
    base_data, fx_permission_info, enrollments_filter, expected_ids,
):  # pylint: disable=unused-argument
    """Verify that get_learners_queryset returns the correct QuerySet when using enrollments filters."""
    assert list(get_learners_queryset(
        fx_permission_info=fx_permission_info,
    ).values_list('id', 'courses_count')) == [
        (5, 2), (15, 2), (21, 3), (22, 2), (23, 2), (24, 2), (25, 2), (28, 1),
        (29, 1), (30, 1), (31, 1), (32, 1), (38, 1), (39, 1), (40, 2), (41, 1),
    ], 'bad test data'

    assert list(get_learners_queryset(
        fx_permission_info=fx_permission_info,
        enrollments_filter=enrollments_filter,
    ).values_list('id', flat=True)) == expected_ids


@pytest.mark.django_db
def test_get_learners_by_course_queryset(base_data):  # pylint: disable=unused-argument
    """Verify that get_learners_by_course_queryset returns the correct QuerySet."""
    PersistentCourseGrade.objects.create(user_id=15, course_id='course-v1:ORG1+5+5', percent_grade=0.67)
    queryset = get_learners_by_course_queryset('course-v1:ORG1+5+5')
    assert queryset.count() == 3, 'unexpected test data'

    user15 = queryset.filter(id=15).first()
    assert user15.certificate_available is not None, 'certificate_available should be in the queryset'
    assert user15.course_score == 0.67, \
        'course_score should be in the queryset with value 0.67 for the first record (user15)'
    assert user15.active_in_course is False, \
        'active_in_course should be in the queryset with value True for the first record (user15)'

    user15.courseenrollment_set.update(is_active=False)
    assert get_learners_by_course_queryset('course-v1:ORG1+5+5').count() == 2, 'inactive enrollments should be counted'


@pytest.mark.django_db
def test_get_learners_by_course_queryset_include_staff(base_data):  # pylint: disable=unused-argument
    """Verify that get_learners_by_course_queryset returns the correct QuerySet."""
    queryset = get_learners_by_course_queryset('course-v1:ORG1+5+5')
    assert queryset.count() == 3, 'unexpected test data'

    queryset = get_learners_by_course_queryset('course-v1:ORG1+5+5', include_staff=True)
    assert queryset.count() == 5, 'unexpected test data'


@pytest.mark.django_db
def test_get_learners_enrollments_queryset_annotations(
    base_data, fx_permission_info
):  # pylint: disable=unused-argument
    """Verify that get_learners_by_course_queryset returns the correct QuerySet."""
    PersistentCourseGrade.objects.create(user_id=15, course_id='course-v1:ORG1+5+5', percent_grade=0.67)
    queryset = get_learners_enrollments_queryset(
        fx_permission_info=fx_permission_info,
        course_ids=['course-v1:ORG1+5+5'],
        user_ids=[15]
    )
    assert queryset.count() == 1, 'unexpected test data'
    assert queryset[0].certificate_available is not None, 'certificate_available should be in the queryset'
    assert queryset[0].course_score == 0.67, \
        'course_score should be in the queryset with value 0.67'
    assert queryset[0].active_in_course is False, \
        'active_in_course should be in the queryset with value True'

    enrollment = queryset[0]
    enrollment.is_active = False
    enrollment.save()
    assert get_learners_enrollments_queryset(
        fx_permission_info=fx_permission_info,
        course_ids=['course-v1:ORG1+5+5'],
        user_ids=[15],
    ).count() == 0, 'only active enrollments should be filtered'


@pytest.mark.django_db
@pytest.mark.parametrize(
    'course_search, learner_search, expected_count, usecase',
    [
        ('', '', 25, 'no search'),
        ('Course 5', '', 8, 'only course search'),
        ('', 'user15', 2, 'only user search'),
        ('Course 5', 'user15', 1, 'both course and user search'),
    ],
)
def test_get_learners_enrollments_queryset_for_course_and_learner_search(
    course_search, learner_search, expected_count, usecase, fx_permission_info,
):
    """Test get_learners_by_course_queryset result for accessible users and courses."""
    fx_permission_info['view_allowed_full_access_orgs'] = ['org1', 'org2']
    queryset = get_learners_enrollments_queryset(
        fx_permission_info=fx_permission_info,
        course_search=course_search,
        learner_search=learner_search
    )
    assert queryset.count() == expected_count, f'unexpected enrollment queryset count for case: {usecase}'


@pytest.mark.django_db
@pytest.mark.parametrize(
    'filter_user_ids, filter_course_ids, filter_usernames, expected_error, expected_count, usecase', [
        (None, None, None, '', 25, 'No filter'),
        ([21], None, None, '', 3, 'only user_ids filter'),
        (None, None, ['user21'], '', 3, 'only usernames filter'),
        ([21], None, ['user29'], '', 4, 'user_ids and usernames filter'),
        ([], ['course-v1:ORG1+5+5'], [], '', 3, 'only course_ids filter'),
        ([15, 29], ['course-v1:ORG1+5+5'], [], '', 1, 'both course_ids and user_ids filter'),
        ([15], ['course-v1:ORG1+5+5'], ['user21'], '', 2, 'course_ids, usernames and user_ids filter'),
        (
            [15], ['course-v1:ORG1+5+5'], ['user21', 'user15'], '', 2,
            'course_ids, usernames and user_ids filter, with repeated user in user ids and usernames'
        ),
        ([15, 29, 'not-int', 0.2], [], [], 'Invalid user ids: [\'not-int\', 0.2]', 0, 'invalid user ids.'),
        ([15, 29], ['course-v1:ORG1+5+5', 'invalid'], [], 'Invalid course ID format: invalid', 0, 'invalid course_ids'),
        ([], [], [11], 'Invalid usernames: [11]', 0, 'invalid usernames'),
    ]
)
def test_get_learners_enrollments_queryset_for_course_and_user_filters(
    filter_user_ids, filter_course_ids, filter_usernames, expected_error, expected_count, usecase, fx_permission_info,
):  # pylint: disable=too-many-arguments
    """Test get_learners_by_course_queryset result for user and course filters."""
    fx_permission_info['view_allowed_full_access_orgs'] = ['org1', 'org2']
    if expected_error:
        with pytest.raises(FXCodedException) as exc_info:
            queryset = get_learners_enrollments_queryset(
                fx_permission_info=fx_permission_info,
                course_ids=filter_course_ids,
                user_ids=filter_user_ids,
                usernames=filter_usernames,
            )
        assert str(exc_info.value) == expected_error
    else:
        queryset = get_learners_enrollments_queryset(
            fx_permission_info=fx_permission_info,
            course_ids=filter_course_ids,
            user_ids=filter_user_ids,
            usernames=filter_usernames,
        )
        assert queryset.count() == expected_count, f'unexpected enrollment queryset count for case: {usecase}'
