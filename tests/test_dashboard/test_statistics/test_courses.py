"""Tests for courses statistics."""
import pytest
from eox_nelp.course_experience.models import FeedbackCourse
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.dashboard.statistics import courses
from futurex_openedx_extensions.helpers.constants import COURSE_STATUSES
from futurex_openedx_extensions.helpers.tenants import get_course_org_filter_list
from tests.base_test_data import _base_data


@pytest.mark.django_db
def test_get_courses_count(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify get_courses_count function."""
    all_tenants = _base_data['tenant_config'].keys()
    fx_permission_info['view_allowed_full_access_orgs'] = get_course_org_filter_list(
        list(all_tenants)
    )['course_org_filter_list']
    result = courses.get_courses_count(fx_permission_info)
    orgs_in_result = [org['org'] for org in result]

    for tenant_id in all_tenants:
        course_org_filter_list = get_course_org_filter_list([tenant_id])['course_org_filter_list']
        for org in course_org_filter_list:
            expected_count = _base_data['course_overviews'].get(org, 0)
            assert (
                expected_count != 0 and {
                    'org': org, 'courses_count': _base_data['course_overviews'].get(org, 0)
                } in result or
                expected_count == 0 and org not in orgs_in_result
            ), f'Missing org: {org} in tenant: {tenant_id} results'


@pytest.mark.django_db
def test_get_courses_count_by_status(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify get_courses_count_by_status function."""
    result = courses.get_courses_count_by_status(fx_permission_info)
    assert list(result) == [
        {'self_paced': False, 'status': COURSE_STATUSES['active'], 'courses_count': 6},
        {'self_paced': False, 'status': COURSE_STATUSES['archived'], 'courses_count': 3},
        {'self_paced': False, 'status': COURSE_STATUSES['upcoming'], 'courses_count': 2},
        {'self_paced': True, 'status': COURSE_STATUSES['active'], 'courses_count': 1}
    ]


@pytest.mark.django_db
def test_get_courses_ratings(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify that get_courses_ratings returns the correct QuerySet."""
    ratings = {
        'course-v1:ORG1+5+5': [3, 4, 5, 3, 4, 5, 3, 2, 5, 2, 4, 5],
        'course-v1:ORG2+4+4': [1, 2, 3, 4, 5, 1, 2, 3, 4, 5],
        'course-v1:ORG2+5+5': [1, 5, 5, 5, 5, 2, 4, 3, 4, 5],
    }
    for course_id, rating in ratings.items():
        course = CourseOverview.objects.get(id=course_id)
        for rate in rating:
            FeedbackCourse.objects.create(
                course_id=course,
                rating_content=rate,
            )

    result = courses.get_courses_ratings(fx_permission_info)
    assert result['total_rating'] == 114
    assert result['total_count'] == 32
    assert result['courses_count'] == 3
    assert result['rating_1_count'] == 3
    assert result['rating_2_count'] == 5
    assert result['rating_3_count'] == 6
    assert result['rating_4_count'] == 7
    assert result['rating_5_count'] == 11
