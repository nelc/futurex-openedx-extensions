"""Tests for learners statistics."""
from unittest.mock import Mock

import pytest
from common.djangoapps.student.models import CourseEnrollment, UserSignupSource

from futurex_openedx_extensions.dashboard.statistics import learners


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_id, expected_result', [
    (1, {'org1': 4, 'org2': 17}),
    (2, {'org3': 13, 'org8': 6}),
    (3, {'org4': 4}),
    (7, {'org3': 13}),
    (8, {'org8': 6}),
])
def test_get_learners_count_having_enrollment_per_org(
    base_data, user1_fx_permission_info, tenant_id, expected_result
):  # pylint: disable=unused-argument
    """Test get_learners_count_having_enrollment_per_org function."""
    result = learners.get_learners_count_having_enrollment_per_org(user1_fx_permission_info, tenant_id)
    assert result.count() == len(expected_result), 'Wrong number of organizations returned'

    for result_tenant_id in result:
        assert result_tenant_id['org_lower_case'] in expected_result, \
            f'Unexpected org: {result_tenant_id["org_lower_case"]}'
        assert result_tenant_id['learners_count'] == expected_result[result_tenant_id['org_lower_case']], \
            f'Wrong learners count: {result_tenant_id["learners_count"]}, org: {result_tenant_id["org_lower_case"]}'


@pytest.mark.django_db
def test_get_learners_count_having_enrollment_per_org_inactive_enrollment(
    base_data, user1_fx_permission_info
):  # pylint: disable=unused-argument
    """Verify that inactive enrollments are not counted by get_learners_count_having_enrollment_per_org."""
    enrollment = CourseEnrollment.objects.get(user_id=21, course_id='course-v1:ORG1+5+5')
    assert enrollment.is_active is True, 'bad test data'
    tenant1_org1 = learners.get_learners_count_having_enrollment_per_org(
        user1_fx_permission_info, 1
    )
    assert tenant1_org1[0]['org_lower_case'] == 'org1', 'bad test data'
    assert tenant1_org1[0]['learners_count'] == 4, 'bad test data'

    enrollment.is_active = False
    enrollment.save()
    tenant1_org1 = learners.get_learners_count_having_enrollment_per_org(
        user1_fx_permission_info, 1
    )
    assert tenant1_org1[0]['org_lower_case'] == 'org1', 'bad test data'
    assert tenant1_org1[0]['learners_count'] == 3, 'inactive enrollment should not be counted'


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_id, expected_result', [
    (1, 17),
    (2, 16),
    (3, 4),
    (7, 13),
    (8, 6),
])
def test_get_learners_count_having_enrollment_for_tenant(
    base_data, user1_fx_permission_info, tenant_id, expected_result
):  # pylint: disable=unused-argument
    """Test get_learners_count_having_enrollment_for_tenant function."""
    result = learners.get_learners_count_having_enrollment_for_tenant(user1_fx_permission_info, tenant_id)
    assert result == expected_result, f'Wrong learners count: {result} for tenant: {tenant_id}'


@pytest.mark.django_db
def test_get_learners_count_having_enrollment_for_tenant_inactive_enrollment(
    base_data, user1_fx_permission_info
):  # pylint: disable=unused-argument
    """Verify that get_learners_count_having_enrollment_for_tenant is not counting inactive enrollments."""
    enrollments = CourseEnrollment.objects.filter(user_id=21, course__org__in=['org1', 'org2'])
    assert enrollments.filter(is_active=True).count() == 3, 'bad test data'
    assert enrollments.filter(is_active=False).count() == 0, 'bad test data'
    assert learners.get_learners_count_having_enrollment_for_tenant(user1_fx_permission_info, 1) == 17, \
        'bad test data'

    enrollments.update(is_active=False)
    assert learners.get_learners_count_having_enrollment_for_tenant(user1_fx_permission_info, 1) == 16, \
        'inactive enrollment should not be counted'


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_id, expected_result', [
    (1, 0),
    (2, 5),
    (3, 2),
    (7, 4),
    (8, 3),
])
def test_get_learners_count_having_no_enrollment(
    base_data, user1_fx_permission_info, tenant_id, expected_result
):  # pylint: disable=unused-argument
    """Test get_learners_count_having_no_enrollment function."""
    result = learners.get_learners_count_having_no_enrollment(user1_fx_permission_info, tenant_id)
    assert result == expected_result, f'Wrong learners count: {result} for tenant: {tenant_id}'


@pytest.mark.django_db
def test_get_learners_count_having_no_enrollment_without_full_access_to_tenant():
    """Test get_learners_count_having_no_enrollment function without full access to tenant."""
    tenant_id = 2
    fx_permission_info = {
        'user': Mock(username='dummy'),
        'is_system_staff_user': True,
        'user_roles': [],
        'permitted_tenant_ids': [tenant_id],
        'view_allowed_roles': [],
        'view_allowed_full_access_orgs': ['org3', 'org8'],
        'view_allowed_course_access_orgs': [],
    }
    assert learners.get_learners_count_having_no_enrollment(fx_permission_info, tenant_id) > 0
    fx_permission_info.update({
        'is_system_staff_user': False,
        'view_allowed_full_access_orgs': ['org3'],
        'view_allowed_course_access_orgs': ['org8'],
    })
    assert learners.get_learners_count_having_no_enrollment(fx_permission_info, tenant_id) == 0


@pytest.mark.django_db
def test_get_learners_count_having_no_enrollment_inactive_enrollment(
    base_data, user1_fx_permission_info
):  # pylint: disable=unused-argument
    """Verify that get_learners_count_having_no_enrollment is counting inactive enrollments correctly."""
    user_id = 5
    enrollments = CourseEnrollment.objects.filter(user_id=user_id, course__org__in=['org1', 'org2'])
    signup = UserSignupSource.objects.filter(user_id=user_id, site='s1.sample.com')
    assert enrollments.filter(is_active=True).count() == 2, 'bad test data'
    assert enrollments.filter(is_active=False).count() == 0, 'bad test data'
    assert signup.count() == 1, 'bad test data'
    assert learners.get_learners_count_having_no_enrollment(user1_fx_permission_info, 1) == 0, 'bad test data'

    enrollment = enrollments.first()
    enrollment.is_active = False
    enrollment.save()
    assert learners.get_learners_count_having_no_enrollment(user1_fx_permission_info, 1) == 0, \
        'having inactive enrollments should not include the user from the count if there are other active enrollments'

    enrollments.update(is_active=False)
    assert learners.get_learners_count_having_no_enrollment(user1_fx_permission_info, 1) == 1, \
        'users with at least one inactive enrollment, and no active enrollments should be counted'

    signup.delete()
    assert learners.get_learners_count_having_no_enrollment(user1_fx_permission_info, 1) == 1, \
        'users with at least one inactive enrollment, and no active enrollments '\
        'should be counted even if they have no signup source'


@pytest.mark.django_db
def test_get_learners_count(base_data, user1_fx_permission_info):  # pylint: disable=unused-argument
    """Test get_learners_count function."""
    result = learners.get_learners_count(user1_fx_permission_info)
    assert result == {
        1: {'learners_count': 17, 'learners_count_no_enrollment': 0, 'learners_count_per_org': {'org1': 4, 'org2': 17}},
        2: {'learners_count': 16, 'learners_count_no_enrollment': 5, 'learners_count_per_org': {'org3': 13, 'org8': 6}},
        3: {'learners_count': 4, 'learners_count_no_enrollment': 2, 'learners_count_per_org': {'org4': 4}},
        7: {'learners_count': 13, 'learners_count_no_enrollment': 4, 'learners_count_per_org': {'org3': 13}},
        8: {'learners_count': 6, 'learners_count_no_enrollment': 3, 'learners_count_per_org': {'org8': 6}}
    }, f'Wrong learners count: {result}'
