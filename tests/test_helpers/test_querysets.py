"""Tests for querysets helpers"""
import pytest
from common.djangoapps.student.models import CourseAccessRole
from django.contrib.auth import get_user_model
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers import querysets


@pytest.mark.django_db
def test_get_base_queryset_courses(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify get_base_queryset_courses function."""
    result = querysets.get_base_queryset_courses(fx_permission_info)
    assert result.count() == 12
    for course in result:
        assert course.catalog_visibility == 'both'


@pytest.mark.django_db
def test_get_base_queryset_courses_non_staff(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify get_base_queryset_courses function for non-staff user."""
    fx_permission_info.update({
        'user': get_user_model().objects.get(username='user4'),
        'is_system_staff_user': False,
        'view_allowed_roles': ['instructor'],
    })

    result = querysets.get_base_queryset_courses(fx_permission_info)
    assert result.count() == 12
    for course in result:
        assert course.catalog_visibility == 'both'


@pytest.mark.django_db
def test_get_base_queryset_courses_visible_filter(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify get_base_queryset_courses function with visible_filter."""
    course = CourseOverview.objects.filter(org='org1').first()
    assert course.catalog_visibility == 'both', 'Catalog visibility should be initialized as (both) for test courses'
    course.catalog_visibility = 'none'
    course.save()

    result = querysets.get_base_queryset_courses(fx_permission_info)
    assert result.count() == 11
    result = querysets.get_base_queryset_courses(fx_permission_info, visible_filter=False)
    assert result.count() == 1
    result = querysets.get_base_queryset_courses(fx_permission_info, visible_filter=None)
    assert result.count() == 12


@pytest.mark.django_db
def test_get_base_queryset_courses_active_filter(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify get_base_queryset_courses function with active_filter."""
    result = querysets.get_base_queryset_courses(fx_permission_info)
    assert result.count() == 12
    result = querysets.get_base_queryset_courses(fx_permission_info, active_filter=True)
    assert result.count() == 7
    result = querysets.get_base_queryset_courses(fx_permission_info, active_filter=False)
    assert result.count() == 5


@pytest.mark.django_db
def test_get_base_queryset_courses_limited_course_roles(
    base_data, fx_permission_info
):  # pylint: disable=unused-argument
    """Verify get_base_queryset_courses function with limited course roles."""
    fx_permission_info.update({
        'user': get_user_model().objects.get(username='user4'),
        'is_system_staff_user': False,
        'view_allowed_full_access_orgs': ['org2'],
        'view_allowed_course_access_orgs': [],
        'view_allowed_any_access_orgs': ['org2'],
        'view_allowed_roles': ['staff'],
    })
    course_id = 'course-v1:ORG2+2+2'
    assert CourseAccessRole.objects.filter(user_id=4, org='org2', role='staff').count() == 0
    assert CourseAccessRole.objects.filter(user_id=4, org='org2', course_id=course_id).count() == 0
    assert querysets.get_base_queryset_courses(fx_permission_info).count() == 0

    CourseAccessRole.objects.create(
        user_id=4, org='org2', role='instructor', course_id=course_id,
    )
    assert querysets.get_base_queryset_courses(fx_permission_info).count() == 0

    course_role = CourseAccessRole.objects.create(
        user_id=4, org='org2', role='staff', course_id=course_id,
    )
    result = querysets.get_base_queryset_courses(fx_permission_info)
    assert result.count() == 1
    assert result.first().org.lower() == course_role.org.lower()
    assert result.first().id == course_role.course_id


@pytest.mark.django_db
def test_get_base_queryset_courses_global_roles(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify get_base_queryset_courses function with global roles."""
    fx_permission_info.update({
        'user': get_user_model().objects.get(username='user4'),
        'is_system_staff_user': False,
        'view_allowed_full_access_orgs': ['org2'],
        'view_allowed_course_access_orgs': [],
        'view_allowed_any_access_orgs': ['org2'],
        'view_allowed_roles': ['staff', 'support'],
    })
    assert CourseAccessRole.objects.filter(user_id=4, org='org2', role__in=['staff', 'support']).count() == 0
    assert querysets.get_base_queryset_courses(fx_permission_info).count() == 0

    CourseAccessRole.objects.create(user_id=4, role='support')
    result = querysets.get_base_queryset_courses(fx_permission_info)
    org2_courses = [course.id for course in CourseOverview.objects.filter(org='org2')]
    assert result.count() == len(org2_courses)
    for course in result:
        assert course.id in org2_courses


@pytest.mark.django_db
@pytest.mark.parametrize('argument_name, bad_value, expected_error_msg', [
    ('ref_user_id', None, 'Invalid ref_user_id type (NoneType)'),
    ('ref_org', 0, 'Invalid ref_org type (int)'),
    ('ref_course_id', 0, 'Invalid ref_course_id type (int)'),
])
def test_check_staff_exist_queryset_invalid(argument_name, bad_value, expected_error_msg):
    """Verify check_staff_exist_queryset function with invalid input."""
    arguments = {
        'ref_user_id': 'user_id',
        'ref_org': 'org',
        'ref_course_id': 'course_id',
    }
    arguments.update({argument_name: bad_value})

    with pytest.raises(ValueError) as exc_info:
        querysets.check_staff_exist_queryset(**arguments)
    assert str(exc_info.value) == expected_error_msg
