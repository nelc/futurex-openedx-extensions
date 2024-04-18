"""Serializers for the dashboard details API."""

from django.contrib.auth import get_user_model
from rest_framework import serializers


class LearnerDetailsSerializer(serializers.ModelSerializer):
    """Serializer for learner details."""
    user_id = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    username = serializers.CharField()
    email = serializers.EmailField()
    mobile_no = serializers.SerializerMethodField()
    date_of_birth = serializers.SerializerMethodField()
    gender = serializers.SerializerMethodField()
    date_joined = serializers.DateTimeField()
    last_login = serializers.DateTimeField()
    enrolled_courses_count = serializers.SerializerMethodField()
    certificates_count = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = [
            'user_id',
            'full_name',
            'username',
            'email',
            'mobile_no',
            'date_of_birth',
            'gender',
            'date_joined',
            'last_login',
            'enrolled_courses_count',
            'certificates_count',
        ]

    @staticmethod
    def _get_profile_field(obj, field_name):
        """Get the profile field value."""
        return getattr(obj.profile, field_name) if hasattr(obj, 'profile') and obj.profile else None

    def get_user_id(self, obj):
        """Return user ID."""
        return obj.id

    def get_full_name(self, obj):
        """Return full name."""
        return self._get_profile_field(obj, 'name')

    def get_mobile_no(self, obj):
        """Return mobile number."""
        return self._get_profile_field(obj, 'phone_number')

    def get_date_of_birth(self, obj):  # pylint: disable=unused-argument
        """Return date of birth."""
        return None

    def get_gender(self, obj):
        """Return gender."""
        return self._get_profile_field(obj, 'gender')

    def get_certificates_count(self, obj):
        """Return certificates count."""
        return obj.certificates_count

    def get_enrolled_courses_count(self, obj):
        """Return enrolled courses count."""
        return obj.courses_count
