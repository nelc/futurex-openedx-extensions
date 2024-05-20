"""Test serializers for dashboard app"""
import pytest
from common.djangoapps.student.models import UserProfile
from django.contrib.auth import get_user_model
from django.db.models import Count

from futurex_openedx_extensions.dashboard.serializers import LearnerDetailsSerializer


def get_dummy_queryset():
    """Get a dummy queryset for testing."""
    return get_user_model().objects.filter(id__in=[10]).annotate(
        courses_count=Count('id'),
        certificates_count=Count('id'),
    ).select_related('profile')


@pytest.mark.django_db
def test_learner_details_serializer_no_profile():
    """Verify that the LearnerDetailsSerializer is correctly defined."""
    queryset = get_dummy_queryset()
    data = LearnerDetailsSerializer(queryset, many=True).data
    assert len(data) == 1
    assert data[0]['user_id'] == 10
    assert data[0]['full_name'] is None
    assert data[0]['mobile_no'] is None
    assert data[0]['year_of_birth'] is None
    assert data[0]['gender'] is None


@pytest.mark.django_db
def test_learner_details_serializer_with_profile():
    """Verify that the LearnerDetailsSerializer processes the profile fields."""
    UserProfile.objects.create(
        user_id=10,
        name='Test User',
        phone_number='1234567890',
        gender='m',
        year_of_birth=1988,
    )
    queryset = get_dummy_queryset()
    data = LearnerDetailsSerializer(queryset, many=True).data
    assert len(data) == 1
    assert data[0]['user_id'] == 10
    assert data[0]['full_name'] == 'Test User'
    assert data[0]['mobile_no'] == '1234567890'
    assert data[0]['year_of_birth'] == 1988
    assert data[0]['gender'] == 'm'
