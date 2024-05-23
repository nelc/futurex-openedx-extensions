"""Tests for learner details collectors"""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from futurex_openedx_extensions.dashboard.details.learners import (
    get_certificates_count_for_learner_queryset,
    get_courses_count_for_learner_queryset,
    get_learner_info_queryset,
    get_learners_queryset,
)


@pytest.mark.django_db
@pytest.mark.parametrize("function_to_test, username, expected_count, assert_error_message", [
    ("courses", "user4", 0, "user4 should report zero courses in ORG1 and ORG2 because of being an org admin"),
    ("certificates", "user4", 2, "user4 should report all certificates regardless of being an org admin"),
    ("courses", "user3", 1, "user3 should report courses in ORG2 but not ORG2 because of course access role"),
    ("certificates", "user3", 1, "user3 should report all certificates regardless of course access role"),
    ("courses", "user5", 2, "user5 should report all courses in ORG1 and ORG2"),
    ("certificates", "user5", 1, "user5 should report all certificates regardless of course access role"),
])
def test_count_for_learner_queryset(
    base_data, function_to_test, username, expected_count, assert_error_message
):  # pylint: disable=unused-argument
    """Verify that get_certificates_count_for_learner_queryset returns the correct QuerySet."""
    assert function_to_test in ["courses", "certificates"], f"bad test data (function_to_test = {function_to_test})"

    queryset = get_user_model().objects.filter(username=username)
    assert queryset.count() == 1, f"bad test data (username = {username})"

    course_org_filter_list = ["ORG1", "ORG2"]
    if function_to_test == "courses":
        fnc = get_courses_count_for_learner_queryset
    else:
        fnc = get_certificates_count_for_learner_queryset
    queryset = get_user_model().objects.filter(username=username).annotate(
        result=fnc(course_org_filter_list)
    )

    assert queryset.all()[0].result == expected_count, f"{assert_error_message} +. Check the test data for details."


@pytest.mark.django_db
def test_get_learner_info_queryset(base_data):  # pylint: disable=unused-argument
    """Verify that get_learners_queryset returns the correct QuerySet."""
    queryset = get_learner_info_queryset([1], 3)
    assert queryset.count() == 1, "bad test data, user id (3) should be in the queryset"

    info = queryset.first()
    assert info.username == "user3", "invalid data fetched!"
    assert hasattr(info, "courses_count"), "courses_count should be in the queryset"
    assert hasattr(info, "certificates_count"), "certificates_count should be in the queryset"


@pytest.mark.django_db
def test_get_learner_info_queryset_selecting_profile(base_data):  # pylint: disable=unused-argument
    """Verify that get_learners_queryset returns the correct QuerySet along with the related profile record."""
    with patch('django.db.models.query.QuerySet.select_related') as mocked_select_related:
        get_learner_info_queryset([1], 3)
    mocked_select_related.assert_called_once_with('profile')


@pytest.mark.django_db
@pytest.mark.parametrize("tenant_ids, search_text, expected_count", [
    ([7, 8], None, 22),
    ([7], None, 17),
    ([7], "user", 17),
    ([7], "user4", 10),
    ([7], "user5", 1),
    ([7], "user6", 0),
    ([4], None, 0),
])
def test_get_learners_queryset(base_data, tenant_ids, search_text, expected_count):  # pylint: disable=unused-argument
    """Verify that get_learners_queryset returns the correct QuerySet."""
    assert get_learners_queryset(tenant_ids, search_text).count() == expected_count
