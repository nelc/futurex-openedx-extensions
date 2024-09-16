"""Tests for courses details collectors"""
from unittest.mock import patch

import pytest
from common.djangoapps.student.models import CourseEnrollment
from completion.models import BlockCompletion
from django.utils.timezone import now, timedelta
from eox_nelp.course_experience.models import FeedbackCourse
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.dashboard.details.courses import (
    annotate_courses_rating_queryset,
    get_courses_queryset,
    get_learner_courses_info_queryset,
)


@pytest.mark.django_db
@pytest.mark.parametrize('orgs, search_text, expected_count', [
    (['org3', 'org8'], None, 5),
    (['org3'], None, 3),
    (['org8'], None, 2),
    (['org3'], 'Course 1', 1),
    (['org3'], 'Course 3', 1),
    (['org3'], 'course 3', 1),
    (['org3'], 'course 4', 0),
    (['ORGX'], None, 0),
    ([], None, 0),
])
def test_get_courses_queryset(
    base_data, fx_permission_info, orgs, search_text, expected_count
):  # pylint: disable=unused-argument
    """Verify that get_courses_queryset returns the correct QuerySet."""
    fx_permission_info['view_allowed_full_access_orgs'] = orgs
    assert get_courses_queryset(fx_permission_info, search_text).count() == expected_count


@pytest.mark.django_db
def test_get_courses_queryset_result_excludes_staff(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify that get_courses_queryset excludes staff users from enrollment, but not from certificates."""
    expected_results = {
        'course-v1:Org1+1+1': [1, 0, 2, 0],
        'course-v1:ORG1+2+2': [0, 0, 1, 0],
        'course-v1:ORG1+3+3': [0, 0, 0, 0],
        'course-v1:ORG1+4+4': [0, 0, 1, 0],
        'course-v1:ORG1+5+5': [3, 4, 5, 4],
        'course-v1:ORG2+1+1': [0, 0, 0, 0],
        'course-v1:ORG2+2+2': [0, 0, 0, 0],
        'course-v1:ORG2+3+3': [1, 0, 1, 0],
        'course-v1:ORG2+4+4': [6, 4, 7, 4],
        'course-v1:ORG2+5+5': [5, 3, 5, 3],
        'course-v1:ORG2+6+6': [5, 0, 5, 0],
        'course-v1:ORG2+7+7': [5, 3, 5, 3],
    }
    result_no_staff = get_courses_queryset(fx_permission_info)
    result_with_staff = get_courses_queryset(fx_permission_info, include_staff=True)

    for record in result_no_staff:
        assert record.enrolled_count == expected_results[str(record.id)][0], f'failed for: {record.id}'
        assert record.certificates_count == expected_results[str(record.id)][1], f'failed for: {record.id}'
    for record in result_with_staff:
        assert record.enrolled_count == expected_results[str(record.id)][2], f'failed for: {record.id}'
        assert record.certificates_count == expected_results[str(record.id)][3], f'failed for: {record.id}'


@pytest.mark.django_db
def test_get_courses_queryset_result_excludes_staff_inactive_enrollment(
    base_data, fx_permission_info
):  # pylint: disable=unused-argument
    """Verify that enrolled_count of get_courses_queryset is not including inactive enrollments."""
    enrollment = CourseEnrollment.objects.get(user_id=21, course_id='course-v1:ORG1+5+5')
    assert enrollment.is_active is True, 'bad test data'
    queryset = get_courses_queryset(fx_permission_info).filter(id='course-v1:ORG1+5+5')
    assert queryset.count() == 1, 'bad test data'
    assert queryset.first().enrolled_count == 3, 'bad test data'

    enrollment.is_active = False
    enrollment.save()
    assert get_courses_queryset(fx_permission_info).filter(id='course-v1:ORG1+5+5').first().enrolled_count == 2


@pytest.mark.django_db
def test_get_courses_queryset_gets_rating(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify that get_courses_queryset calls annotate_courses_rating_queryset."""
    with patch(
        'futurex_openedx_extensions.dashboard.details.courses.annotate_courses_rating_queryset'
    ) as mock_rating_queryset:
        get_courses_queryset(fx_permission_info)
        mock_rating_queryset.assert_called_once()


@pytest.mark.django_db
def test_annotate_courses_rating_queryset(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify that annotate_courses_rating_queryset returns the correct rating."""
    ratings = [3, 4, 5, 3, 4, 5, 3, 2, 5, 2, 4, 5]
    no_ratings = [0, 0, 0, 0, 0, 0]
    all_ratings = ratings + no_ratings
    course = CourseOverview.objects.get(id='course-v1:ORG1+5+5')
    for rating in all_ratings:
        FeedbackCourse.objects.create(
            course_id=course,
            rating_content=rating,
        )
    queryset = annotate_courses_rating_queryset(CourseOverview.objects.filter(org__in=['org1', 'org2']))
    for record in queryset:
        if record.id != course.id:
            continue
        assert record.rating_count == len(ratings)
        assert record.rating_total == sum(ratings)


@pytest.mark.django_db
def test_get_learner_courses_info_queryset(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify that get_learner_courses_info_queryset returns the correct QuerySet."""
    user_id = 23
    now_datetime = now()
    test_data = {
        'course-v1:ORG2+4+4': {
            'enrollment_date': now_datetime - timedelta(days=20),
            'activities': [4, 2, 7],
            'last_activity': now_datetime - timedelta(days=2),
        },
        'course-v1:ORG2+5+5': {
            'enrollment_date': now_datetime - timedelta(days=19),
            'activities': [],
            'last_activity': now_datetime - timedelta(days=19),
        },
    }
    for course_id, data in test_data.items():
        enrollment = CourseEnrollment.objects.get(user_id=user_id, course_id=course_id)
        enrollment.created = data['enrollment_date']
        enrollment.save()
        for days in data['activities']:
            BlockCompletion.objects.create(
                user_id=user_id,
                context_key=course_id,
                modified=now_datetime - timedelta(days=days),
            )

    result = get_learner_courses_info_queryset(fx_permission_info, user_id)

    assert result.count() == len(test_data)
    for record in result:
        course_id = str(record.id)
        assert course_id in test_data, f'failed for: {course_id}'
        assert record.related_user_id == user_id, f'failed for: {course_id}'
        assert record.enrollment_date == test_data[course_id]['enrollment_date'], f'failed for: {course_id}'
        assert record.last_activity == test_data[course_id]['last_activity'], f'failed for: {course_id}'
