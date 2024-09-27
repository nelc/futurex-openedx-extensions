"""Tests for learner details collectors"""
from unittest.mock import patch

import pytest
from common.djangoapps.student.models import CourseEnrollment, UserProfile
from django.contrib.auth import get_user_model
from lms.djangoapps.grades.models import PersistentCourseGrade

from futurex_openedx_extensions.dashboard.details.learners import (
    get_certificates_count_for_learner_queryset,
    get_courses_count_for_learner_queryset,
    get_learner_info_queryset,
    get_learners_by_course_queryset,
    get_learners_queryset,
    get_learners_search_queryset,
)
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
    queryset = get_learner_info_queryset(fx_permission_info, 3)
    assert queryset.count() == 1, 'bad test data, user id (3) should be in the queryset'

    info = queryset.first()
    assert info.username == 'user3', 'invalid data fetched!'
    assert hasattr(info, 'courses_count'), 'courses_count should be in the queryset'
    assert hasattr(info, 'certificates_count'), 'certificates_count should be in the queryset'


@pytest.mark.django_db
def test_get_learner_info_queryset_selecting_profile(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify that get_learner_info_queryset returns the correct QuerySet along with the related profile record."""
    with patch('django.db.models.query.QuerySet.select_related') as mocked_select_related:
        get_learner_info_queryset(fx_permission_info, 3)
    mocked_select_related.assert_called_once_with('profile')


@pytest.mark.django_db
@pytest.mark.parametrize('search_text, expected_count', [
    (None, 64),
    ('user', 64),
    ('user4', 11),
    ('example', 64),
])
def test_get_learners_search_queryset(base_data, search_text, expected_count):  # pylint: disable=unused-argument
    """Verify that get_learners_search_queryset returns the correct QuerySet."""
    assert get_learners_search_queryset(search_text=search_text).count() == expected_count


@pytest.mark.django_db
def test_get_learners_search_queryset_name(base_data):  # pylint: disable=unused-argument
    """Verify that get_learners_search_queryset returns the correct QuerySet when searching in profile name."""
    assert get_learners_search_queryset(search_text='hn D').count() == 0
    UserProfile.objects.create(user_id=10, name='John Doe')
    assert get_learners_search_queryset(search_text='hn D').count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize('filter_name, true_count', [
    ('superuser_filter', 2),
    ('staff_filter', 2),
    ('active_filter', 67),
])
def test_get_learners_search_queryset_active_filter(
    base_data, filter_name, true_count
):  # pylint: disable=unused-argument
    """Verify that get_learners_search_queryset returns the correct QuerySet when active_filters is used"""
    kwargs = {
        'superuser_filter': None,
        'staff_filter': None,
        'active_filter': None,
    }
    assert get_learners_search_queryset(**kwargs).count() == 70, 'unexpected test data'
    kwargs[filter_name] = True
    assert get_learners_search_queryset(**kwargs).count() == true_count
    kwargs[filter_name] = False
    assert get_learners_search_queryset(**kwargs).count() == 70 - true_count


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_ids, expected_count_no_staff, expected_count_include_staff', [
    ([7, 8], 22, 26),
    ([7], 17, 20),
    ([4], 0, 0),
])
def test_get_learners_queryset(
    base_data, fx_permission_info, tenant_ids, expected_count_no_staff, expected_count_include_staff,
):  # pylint: disable=unused-argument
    """Verify that get_learners_queryset returns the correct QuerySet."""
    fx_permission_info['view_allowed_full_access_orgs'] = get_tenants_orgs(tenant_ids)
    fx_permission_info['permitted_tenant_ids'] = tenant_ids
    result = get_learners_queryset(fx_permission_info)
    assert result.count() == expected_count_no_staff
    if expected_count_no_staff > 0:
        assert result.first().courses_count is not None, 'courses_count should be in the queryset'
        assert result.first().certificates_count is not None, 'certificates_count should be in the queryset'
    assert get_learners_queryset(fx_permission_info, include_staff=True).count() == expected_count_include_staff


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
