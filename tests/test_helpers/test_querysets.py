"""Tests for querysets helpers"""
import pytest
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers.querysets import get_base_queryset_courses


@pytest.mark.django_db
def test_get_base_queryset_courses(base_data):  # pylint: disable=unused-argument
    """Verify get_base_queryset_courses function."""
    result = get_base_queryset_courses(["ORG1", "ORG2"])
    assert result.count() == 12
    for course in result:
        assert course.catalog_visibility == "both"


@pytest.mark.django_db
def test_get_base_queryset_courses_not_only_visible(base_data):  # pylint: disable=unused-argument
    """Verify get_base_queryset_courses function with only_visible=False."""
    course = CourseOverview.objects.filter(org="ORG1").first()
    assert course.catalog_visibility == "both", "Catalog visibility should be initialized as (both) for test courses"
    course.catalog_visibility = "none"
    course.save()

    result = get_base_queryset_courses(["ORG1", "ORG2"])
    assert result.count() == 11
    result = get_base_queryset_courses(["ORG1", "ORG2"], only_visible=False)
    assert result.count() == 12


@pytest.mark.django_db
def test_get_base_queryset_courses_only_active(base_data):  # pylint: disable=unused-argument
    """Verify get_base_queryset_courses function with only_active=True."""
    result = get_base_queryset_courses(["ORG1", "ORG2"], only_active=True)
    assert result.count() == 7
