"""Tests for courses details collectors"""
import pytest
from eox_nelp.course_experience.models import FeedbackCourse
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.dashboard.details.courses import get_courses_queryset


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_ids, search_text, expected_count', [
    ([7, 8], None, 5),
    ([7], None, 3),
    ([8], None, 2),
    ([7], 'Course 1', 1),
    ([7], 'Course 3', 1),
    ([7], 'course 3', 1),
    ([7], 'course 4', 0),
    ([4], None, 0),
])
def test_get_courses_queryset(base_data, tenant_ids, search_text, expected_count):  # pylint: disable=unused-argument
    """Verify that get_courses_queryset returns the correct QuerySet."""
    assert get_courses_queryset(tenant_ids, search_text).count() == expected_count


@pytest.mark.django_db
def test_get_courses_queryset_result_excludes_staff(base_data):  # pylint: disable=unused-argument
    """Verify that get_courses_queryset excludes staff users from enrollment, but not from certificates."""
    expected_results = {
        'course-v1:ORG1+1+1': [1, 0],
        'course-v1:ORG1+2+2': [0, 0],
        'course-v1:ORG1+3+3': [0, 0],
        'course-v1:ORG1+4+4': [0, 0],
        'course-v1:ORG1+5+5': [3, 4],
        'course-v1:ORG2+1+1': [0, 0],
        'course-v1:ORG2+2+2': [0, 0],
        'course-v1:ORG2+3+3': [1, 0],
        'course-v1:ORG2+4+4': [6, 4],
        'course-v1:ORG2+5+5': [5, 3],
        'course-v1:ORG2+6+6': [5, 0],
        'course-v1:ORG2+7+7': [5, 3],
        }
    queryset = get_courses_queryset([1])
    for record in queryset:
        assert record.enrolled_count == expected_results[record.id][0]
        assert record.certificates_count == expected_results[record.id][1]


@pytest.mark.django_db
def test_get_courses_queryset_result_rating(base_data):  # pylint: disable=unused-argument
    """Verify that get_courses_queryset returns the correct rating."""
    ratings = [3, 4, 5, 3, 4, 5, 3, 2, 5, 2, 4, 5]
    no_ratings = [0, 0, 0, 0, 0, 0]
    all_ratings = ratings + no_ratings
    course = CourseOverview.objects.get(id='course-v1:ORG1+5+5')
    for rating in all_ratings:
        FeedbackCourse.objects.create(
            course_id=course,
            rating_content=rating,
        )
    queryset = get_courses_queryset([1])
    for record in queryset:
        if record.id != course.id:
            continue
        assert record.rating_count == len(ratings)
        assert record.rating_total == sum(ratings)
