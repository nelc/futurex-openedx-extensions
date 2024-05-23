"""Test serializers for dashboard app"""
from unittest.mock import Mock

import pytest
from common.djangoapps.student.models import SocialLink, UserProfile
from django.contrib.auth import get_user_model
from django.db.models import Count
from openedx.core.djangoapps.user_api.accounts.serializers import AccountLegacyProfileSerializer

from futurex_openedx_extensions.dashboard.serializers import LearnerDetailsExtendedSerializer, LearnerDetailsSerializer


def get_dummy_queryset(users_list=None):
    """Get a dummy queryset for testing."""
    if users_list is None:
        users_list = [10]
    return get_user_model().objects.filter(id__in=users_list).annotate(
        courses_count=Count('id'),
        certificates_count=Count('id'),
    ).select_related('profile')


@pytest.mark.django_db
def test_learner_details_serializer_no_profile(base_data):  # pylint: disable=unused-argument
    """Verify that the LearnerDetailsSerializer is correctly defined."""
    queryset = get_dummy_queryset()
    data = LearnerDetailsSerializer(queryset, many=True).data
    assert len(data) == 1
    assert data[0]['user_id'] == 10
    assert data[0]['full_name'] == ""
    assert data[0]['mobile_no'] is None
    assert data[0]['year_of_birth'] is None
    assert data[0]['gender'] is None


@pytest.mark.django_db
def test_learner_details_serializer_with_profile(base_data):  # pylint: disable=unused-argument
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


@pytest.mark.django_db
@pytest.mark.parametrize("first_name, last_name, profile_name, expected_full_name, expected_alt_name, use_case", [
    ("", "", "", "", "", "all are empty"),
    ("", "Doe", "Alt John", "Doe", "Alt John", "first name empty"),
    ("John", "", "Alt John", "John", "Alt John", "last name empty"),
    ("John", "Doe", "", "John Doe", "", "profile name empty"),
    ("", "", "Alt John", "Alt John", "", "first and last names empty"),
    ("John", "John", "Alt John", "John John", "Alt John", "first and last names identical with no spaces"),
    ("John Doe", "John Doe", "Alt John", "John Doe", "Alt John", "first and last names identical with spaces"),
    ("عربي", "Doe", "Alt John", "عربي Doe", "Alt John", "Arabic name"),
    ("John", "Doe", "عربي", "عربي", "John Doe", "Arabic alternative name"),
])
def test_learner_details_serializer_full_name_alt_name(
    base_data, first_name, last_name, profile_name, expected_full_name, expected_alt_name, use_case
):  # pylint: disable=unused-argument, too-many-arguments
    """Verify that the LearnerDetailsSerializer processes names as expected."""
    queryset = get_dummy_queryset()
    UserProfile.objects.create(
        user_id=10,
        name=profile_name,
    )
    user = queryset.first()
    user.first_name = first_name
    user.last_name = last_name
    user.save()

    serializer = LearnerDetailsSerializer(queryset, many=True)
    data = serializer.data
    assert len(data) == 1
    assert data[0]['user_id'] == 10
    assert data[0]['full_name'] == expected_full_name, f"checking ({use_case}) failed"
    assert data[0]['alternative_full_name'] == expected_alt_name, f"checking ({use_case}) failed"


@pytest.mark.django_db
def test_learner_details_extended_serializer(base_data):  # pylint: disable=unused-argument
    """Verify that the LearnerDetailsExtendedSerializer returns the correct data."""
    queryset = get_dummy_queryset()
    profile = UserProfile.objects.create(
        user_id=10,
        city='Test City',
        bio='Test Bio',
        level_of_education='Test Level',
    )
    data = LearnerDetailsExtendedSerializer(queryset, many=True).data
    image_serialized = AccountLegacyProfileSerializer.get_profile_image(profile, queryset.first(), None)
    assert len(data) == 1
    assert data[0]['user_id'] == 10
    assert data[0]['city'] == 'Test City'
    assert data[0]['bio'] == 'Test Bio'
    assert data[0]['level_of_education'] == 'Test Level'
    assert data[0]['social_links'] == {}
    assert data[0]['image'] == image_serialized['image_url_large']
    assert data[0]['profile_link'] is None
    assert image_serialized['has_image'] is False


@pytest.mark.django_db
def test_learner_details_extended_serializer_no_profile(base_data):  # pylint: disable=unused-argument
    """Verify that the LearnerDetailsExtendedSerializer returns the correct data when there is no profile."""
    queryset = get_dummy_queryset()
    data = LearnerDetailsExtendedSerializer(queryset, many=True).data
    assert len(data) == 1
    assert data[0]['user_id'] == 10
    assert data[0]['city'] is None
    assert data[0]['bio'] is None
    assert data[0]['level_of_education'] is None
    assert data[0]['social_links'] == {}
    assert data[0]['image'] is None
    assert data[0]['profile_link'] is None


@pytest.mark.django_db
@pytest.mark.parametrize("site, expected_value", [
    (None, None),
    (Mock(domain='https://profile.example.com'), 'https://profile.example.com/u/user10'),
])
def test_learner_details_extended_serializer_profile_link(
    base_data, site, expected_value
):  # pylint: disable=unused-argument
    """Verify that the LearnerDetailsExtendedSerializer returns the profile link."""
    queryset = get_dummy_queryset()
    UserProfile.objects.create(user_id=10)
    data = LearnerDetailsExtendedSerializer(
        queryset, many=True, context={'request': Mock(site=site)}
    ).data
    assert len(data) == 1
    assert data[0]['user_id'] == 10
    assert data[0]['profile_link'] == expected_value


@pytest.mark.django_db
def test_learner_details_extended_serializer_social_links(base_data):  # pylint: disable=unused-argument
    """Verify that the LearnerDetailsExtendedSerializer returns the social links."""
    queryset = get_dummy_queryset()
    profile = UserProfile.objects.create(user_id=10)
    SocialLink.objects.create(
        user_profile_id=profile.id,
        platform='facebook',
        social_link='https://facebook.com/test',
    )
    data = LearnerDetailsExtendedSerializer(queryset, many=True).data
    assert len(data) == 1
    assert data[0]['user_id'] == 10
    assert data[0]['social_links'] == {'facebook': 'https://facebook.com/test'}


@pytest.mark.django_db
def test_learner_details_extended_serializer_image(base_data):  # pylint: disable=unused-argument
    """Verify that the LearnerDetailsExtendedSerializer returns the profile image."""
    queryset = get_dummy_queryset([1])
    profile = UserProfile.objects.create(user_id=1)
    data = LearnerDetailsExtendedSerializer(queryset, many=True).data
    image_serialized = AccountLegacyProfileSerializer.get_profile_image(profile, queryset.first(), None)
    assert len(data) == 1
    assert data[0]['user_id'] == 1
    assert data[0]['image'] == image_serialized['image_url_large']
    assert image_serialized['has_image'] is True
