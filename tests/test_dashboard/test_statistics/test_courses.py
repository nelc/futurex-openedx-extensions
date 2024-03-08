"""Tests for courses statistics."""
import pytest
from django.utils.timezone import now, timedelta
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.dashboard.statistics import courses
from futurex_openedx_extensions.helpers.tenants import get_course_org_filter_list
from tests.base_test_data import _base_data


@pytest.mark.django_db
def test_get_courses_count(base_data):
    """Verify get_courses_count function."""
    all_tenants = _base_data["tenant_config"].keys()
    result = courses.get_courses_count(all_tenants)
    orgs_in_result = [org["org"] for org in result]

    for tenant_id in all_tenants:
        course_org_filter_list = get_course_org_filter_list([tenant_id])["course_org_filter_list"]
        for org in course_org_filter_list:
            expected_count = _base_data["course_overviews"].get(org, 0)
            assert (
                expected_count != 0 and {
                    "org": org, "courses_count": _base_data["course_overviews"].get(org, 0)
                } in result or
                expected_count == 0 and org not in orgs_in_result
            ), f'Missing org: {org} in tenant: {tenant_id} results'


@pytest.mark.django_db
@pytest.mark.parametrize('start_diff, end_diff, expected_org1_count', [
    (None, None, 5),
    (None, 1, 5),
    (None, -1, 4),
    (1, None, 4),
    (-1, None, 5),
    (1, 2, 4),
    (-1, 1, 5),
    (-2, -1, 4),
])
def test_get_courses_count_only_active(base_data, start_diff, end_diff, expected_org1_count):
    """Verify get_courses_count function with only_active=True."""
    course = CourseOverview.objects.filter(org="ORG1").first()
    assert course.start is None
    assert course.end is None

    if start_diff is not None:
        course.start = now() + timedelta(days=start_diff)
    if end_diff is not None:
        course.end = now() + timedelta(days=end_diff)
    course.save()
    expected_result = [
        {'org': 'ORG1', 'courses_count': expected_org1_count},
        {'org': 'ORG2', 'courses_count': 7},
    ]

    result = courses.get_courses_count([1], only_active=True)
    assert expected_result == list(result), f'Wrong result: {result}'


@pytest.mark.django_db
def test_get_courses_count_only_visible(base_data):
    """Verify get_courses_count function with only_visible=True."""
    course = CourseOverview.objects.filter(org="ORG1").first()
    assert course.visible_to_staff_only is False
    course.visible_to_staff_only = True
    course.save()
    expected_result = [
        {'org': 'ORG1', 'courses_count': 4},
        {'org': 'ORG2', 'courses_count': 7},
    ]

    result = courses.get_courses_count([1], only_visible=True)
    assert expected_result == list(result), f'Wrong result: {result}'
