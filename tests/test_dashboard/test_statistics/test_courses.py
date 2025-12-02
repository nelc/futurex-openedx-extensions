"""Tests for courses statistics."""
from datetime import datetime
from unittest.mock import patch

import pytest
from common.djangoapps.student.models import CourseEnrollment
from django.db.models import CharField, Value
from eox_nelp.course_experience.models import FeedbackCourse
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.dashboard.statistics import courses
from futurex_openedx_extensions.helpers.constants import COURSE_STATUSES
from futurex_openedx_extensions.helpers.tenants import get_course_org_filter_list
from tests.base_test_data import _base_data
from tests.fixture_helpers import d_t


@pytest.mark.django_db
def test_get_courses_count(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify get_courses_count function."""
    all_tenants = _base_data['tenant_config'].keys()
    fx_permission_info['view_allowed_full_access_orgs'] = get_course_org_filter_list(
        list(all_tenants), ignore_invalid_tenant_ids=True,
    )['course_org_filter_list']
    fx_permission_info['view_allowed_any_access_orgs'] = fx_permission_info['view_allowed_full_access_orgs']
    result = courses.get_courses_count(fx_permission_info)
    orgs_in_result = [org['org_lower_case'] for org in result]

    for tenant_id in all_tenants:
        course_org_filter_list = get_course_org_filter_list(
            [tenant_id], ignore_invalid_tenant_ids=True,
        )['course_org_filter_list']
        for org in course_org_filter_list:
            expected_count = 0
            for data_org, course_index_range in _base_data['course_overviews'].items():
                if org == data_org.lower() and course_index_range is not None:
                    expected_count += course_index_range[1] - course_index_range[0] + 1
            assert (
                expected_count != 0 and {
                    'org_lower_case': org, 'courses_count': expected_count
                } in result or
                expected_count == 0 and org not in orgs_in_result
            ), f'Missing org: {org} in tenant: {tenant_id} results'


@pytest.mark.django_db
def test_get_enrollments_count(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify get_enrollments_count function."""
    result = courses.get_enrollments_count(fx_permission_info, include_staff=True)

    assert list(result) == [
        {'org_lower_case': 'org1', 'enrollments_count': 9},
        {'org_lower_case': 'org2', 'enrollments_count': 23},
    ]

    result = courses.get_enrollments_count(fx_permission_info)

    assert list(result) == [
        {'org_lower_case': 'org1', 'enrollments_count': 4},
        {'org_lower_case': 'org2', 'enrollments_count': 22},
    ]


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

    result = courses.get_courses_ratings(tenant_id=1)
    assert result['total_rating'] == 114
    assert result['courses_count'] == 3
    assert result['rating_1_count'] == 3
    assert result['rating_2_count'] == 5
    assert result['rating_3_count'] == 6
    assert result['rating_4_count'] == 7
    assert result['rating_5_count'] == 11


@pytest.mark.django_db
def test_get_courses_ratings_no_rating(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify that get_courses_ratings returns the correct QuerySet when there are no ratings."""
    expected_keys = ['total_rating', 'courses_count'] + [
        f'rating_{i}_count' for i in range(1, 6)
    ]
    result = courses.get_courses_ratings(tenant_id=1)
    assert set(result.keys()) == set(expected_keys)
    assert all(result[key] is not None for key in expected_keys)
    assert all(result[key] == 0 for key in expected_keys)


@pytest.mark.django_db
@patch('futurex_openedx_extensions.dashboard.statistics.courses.get_valid_duration')
@patch('futurex_openedx_extensions.dashboard.statistics.courses._get_enrollments_count')
@patch('futurex_openedx_extensions.dashboard.statistics.courses.annotate_period')
def test_get_enrollments_count_aggregated_calls(
    mock_annotate_period, mock_get_enrollments_count, mock_get_valid_duration,
):
    """Verify get_enrollments_count_aggregated calls other function with the right argument."""
    mock_get_valid_duration.return_value = (None, None)
    mock_get_enrollments_count.return_value = CourseEnrollment.objects.all()
    mock_annotate_period.return_value = mock_get_enrollments_count.return_value.annotate(
        period=Value('', output_field=CharField()),
    )
    fx_permission_info = {'dummy_fx_info': {}}
    period = 'dummy_period'
    date_from = 'dummy_date_from'
    date_to = 'dummy_date_to'
    favors_backward = 'dummy_favors_backward'
    max_chunks = 'dummy_max_chunks'
    visible_filter = 'dummy_visible_filter'
    active_filter = 'dummy_active_filter'
    include_staff = 'dummy_include_staff'

    courses.get_enrollments_count_aggregated(
        fx_permission_info=fx_permission_info,
        visible_filter=visible_filter,
        active_filter=active_filter,
        include_staff=include_staff,
        aggregate_period=period,
        date_from=date_from,
        date_to=date_to,
        favors_backward=favors_backward,
        max_period_chunks=max_chunks,
    )
    mock_get_valid_duration.assert_called_once_with(
        period=period,
        date_from=date_from,
        date_to=date_to,
        favors_backward=favors_backward,
        max_chunks=max_chunks,
    )
    mock_get_enrollments_count.assert_called_once_with(
        fx_permission_info,
        visible_filter=visible_filter,
        active_filter=active_filter,
        include_staff=include_staff,
    )
    mock_annotate_period.assert_called_once_with(
        query_set=mock_get_enrollments_count.return_value,
        period=period,
        field_name='created',
    )


@pytest.mark.django_db
@pytest.mark.parametrize('date_from, date_to, expected_result', [
    (d_t('2020-12-26'), d_t('2021-03-21'), [
        {'period': '2020-12-26', 'enrollments_count': 5},
        {'period': '2021-02-14', 'enrollments_count': 2},
        {'period': '2021-03-21', 'enrollments_count': 12}
    ]),
    (d_t('2020-01-01'), d_t('2021-01-01'), [
        {'period': '2020-12-26', 'enrollments_count': 5},
    ]),
    (d_t('2022-03-21'), d_t('2022-12-26'), []),
    (d_t('2022-12-26'), d_t('2022-03-21'), []),
])
def test_get_enrollments_count_aggregated_result(
    date_from, date_to, expected_result, base_data, fx_permission_info,
):  # pylint: disable=unused-argument
    """Verify get_enrollments_count_aggregated function."""
    def _is_unusable_enrollment(_enrollment):
        """Check if an enrollment is unusable."""
        return (
            _enrollment.user.is_staff or
            _enrollment.user.is_superuser or
            not _enrollment.user.is_active or
            _enrollment.is_active is False
        )

    assert CourseEnrollment.objects.count() == 73, 'bad test data'
    test_data = [
        (5, '2020-12-26'),
        (2, '2021-02-14'),
        (12, '2021-03-21'),
    ]
    enrollment_id = 1
    for data in test_data:
        count = data[0]
        while count > 0:
            enrollment = CourseEnrollment.objects.get(id=enrollment_id)
            enrollment_id += 1
            if _is_unusable_enrollment(enrollment):
                continue
            enrollment.created = data[1]
            enrollment.save()
            count -= 1

    result, calculated_from, calculated_to = courses.get_enrollments_count_aggregated(
        fx_permission_info,
        include_staff=True,
        date_from=date_from,
        date_to=date_to,
        aggregate_period='day',
        max_period_chunks=-1,
    )
    assert result.count() == len(expected_result)
    assert list(result) == expected_result
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    assert calculated_from == datetime.combine(date_from, datetime.min.time())
    assert calculated_to == datetime.combine(date_to, datetime.max.time())


@pytest.mark.django_db
def testcache_name_courses_rating():
    """Verify that cache key generation works correctly with different parameters."""
    key1 = courses.cache_name_courses_rating(1, True, True)
    key2 = courses.cache_name_courses_rating(1, True, False)
    key3 = courses.cache_name_courses_rating(1, False, True)
    key4 = courses.cache_name_courses_rating(2, True, True)
    key5 = courses.cache_name_courses_rating(1, None, None)
    keys = [key1, key2, key3, key4, key5]
    assert len(keys) == len(set(keys)), 'Cache keys should be unique for different parameters'

    assert key1 == 'fx_courses_ratings_t1_vTrue_aTrue'
    assert key2 == 'fx_courses_ratings_t1_vTrue_aFalse'
    assert key3 == 'fx_courses_ratings_t1_vFalse_aTrue'
    assert key4 == 'fx_courses_ratings_t2_vTrue_aTrue'
    assert key5 == 'fx_courses_ratings_t1_vNone_aNone'
