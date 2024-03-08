"""Tests for learner details collectors"""
import pytest
from django.db.models import Sum

from futurex_openedx_extensions.dashboard.details.learners import get_learners_queryset
from tests.base_test_data import expected_statistics


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_ids, search_text, expected_count', [
    ([7, 8], None, 22),
    ([7], None, 17),
    ([7], 'user', 17),
    ([7], 'user4', 10),
    ([7], 'user5', 1),
    ([7], 'user6', 0),
    ([4], None, 0),
])
def test_get_learners_queryset(base_data, tenant_ids, search_text, expected_count):
    """Verify that get_learners_queryset returns the correct QuerySet."""
    assert get_learners_queryset(tenant_ids, search_text).count() == expected_count
