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
        'view_allowed_roles': ['org_course_creator_group'],
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
        'view_allowed_full_access_orgs': [],
        'view_allowed_course_access_orgs': ['org2'],
        'view_allowed_roles': ['instructor'],
    })
    course_role = CourseAccessRole.objects.get(user_id=4, org='org2')
    course_role.course_id = 'course-v1:ORG2+2+2'
    course_role.save()
    result = querysets.get_base_queryset_courses(fx_permission_info)
    assert result.count() == 1
    assert result.first().org.lower() == 'org2'


@pytest.mark.django_db
@pytest.mark.parametrize('sites, expected', [
    (['s1.sample.com'], True),
    (['s2.sample.com'], True),
    (['s3.sample.com'], False),
    (['s1.sample.com', 's2.sample.com'], True),
    (['s1.sample.com', 's3.sample.com'], True),
    (['s2.sample.com', 's3.sample.com'], True),
])
def test_get_has_site_login_queryset(base_data, sites, expected):  # pylint: disable=unused-argument
    """Verify get_has_site_login_queryset function."""
    result = get_user_model().objects.filter(
        username='user4',
    ).annotate(
        has_site_login=querysets.get_has_site_login_queryset(sites),
    )
    assert result.count() == 1
    assert result.first().has_site_login == expected
