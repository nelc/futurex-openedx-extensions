"""Tests for querysets helpers"""
import pytest
from django.contrib.auth import get_user_model
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers import querysets


@pytest.mark.django_db
def test_get_base_queryset_courses(base_data):  # pylint: disable=unused-argument
    """Verify get_base_queryset_courses function."""
    result = querysets.get_base_queryset_courses(["ORG1", "ORG2"])
    assert result.count() == 12
    for course in result:
        assert course.catalog_visibility == "both"


@pytest.mark.django_db
def test_get_base_queryset_courses_visible_filter(base_data):  # pylint: disable=unused-argument
    """Verify get_base_queryset_courses function with visible_filter."""
    course = CourseOverview.objects.filter(org="ORG1").first()
    assert course.catalog_visibility == "both", "Catalog visibility should be initialized as (both) for test courses"
    course.catalog_visibility = "none"
    course.save()

    result = querysets.get_base_queryset_courses(["ORG1", "ORG2"])
    assert result.count() == 11
    result = querysets.get_base_queryset_courses(["ORG1", "ORG2"], visible_filter=False)
    assert result.count() == 1
    result = querysets.get_base_queryset_courses(["ORG1", "ORG2"], visible_filter=None)
    assert result.count() == 12


@pytest.mark.django_db
def test_get_base_queryset_courses_active_filter(base_data):  # pylint: disable=unused-argument
    """Verify get_base_queryset_courses function with active_filter."""
    result = querysets.get_base_queryset_courses(["ORG1", "ORG2"])
    assert result.count() == 12
    result = querysets.get_base_queryset_courses(["ORG1", "ORG2"], active_filter=True)
    assert result.count() == 7
    result = querysets.get_base_queryset_courses(["ORG1", "ORG2"], active_filter=False)
    assert result.count() == 5


@pytest.mark.django_db
@pytest.mark.parametrize("sites, expected", [
    (["s1.sample.com"], True),
    (["s2.sample.com"], True),
    (["s3.sample.com"], False),
    (["s1.sample.com", "s2.sample.com"], True),
    (["s1.sample.com", "s3.sample.com"], True),
    (["s2.sample.com", "s3.sample.com"], True),
])
def test_get_has_site_login_queryset(base_data, sites, expected):  # pylint: disable=unused-argument
    """Verify get_has_site_login_queryset function."""
    result = get_user_model().objects.filter(
        username="user4",
    ).annotate(
        has_site_login=querysets.get_has_site_login_queryset(sites),
    )
    assert result.count() == 1
    assert result.first().has_site_login == expected
