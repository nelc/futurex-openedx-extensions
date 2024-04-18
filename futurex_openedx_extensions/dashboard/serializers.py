"""Serializers for the dashboard details API."""
from django.contrib.auth import get_user_model
from django.utils.timezone import now
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from rest_framework import serializers

from futurex_openedx_extensions.helpers.constants import COURSE_STATUS_SELF_PREFIX, COURSE_STATUSES
from futurex_openedx_extensions.helpers.tenants import get_tenants_by_org


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


class CourseDetailsSerializer(serializers.ModelSerializer):
    """Serializer for course details."""
    status = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    enrolled_count = serializers.IntegerField()
    active_count = serializers.IntegerField()
    certificates_count = serializers.IntegerField()
    start_date = serializers.SerializerMethodField()
    end_date = serializers.SerializerMethodField()
    start_enrollment_date = serializers.SerializerMethodField()
    end_enrollment_date = serializers.SerializerMethodField()
    display_name = serializers.CharField()
    image_url = serializers.SerializerMethodField()
    org = serializers.CharField()
    tenant_ids = serializers.SerializerMethodField()
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = CourseOverview
        fields = [
            'id',
            'status',
            'self_paced',
            'rating',
            'enrolled_count',
            'active_count',
            'certificates_count',
            'start_date',
            'end_date',
            'start_enrollment_date',
            'end_enrollment_date',
            'display_name',
            'image_url',
            'org',
            'tenant_ids',
            'author_name',
        ]

    def get_status(self, obj):
        """Return the course status."""
        now_time = now()
        if obj.end and obj.end < now_time:
            status = COURSE_STATUSES['archived']
        elif obj.start and obj.start > now_time:
            status = COURSE_STATUSES['upcoming']
        else:
            status = COURSE_STATUSES['active']

        return f'{COURSE_STATUS_SELF_PREFIX if obj.self_paced else ""}{status}'

    def get_rating(self, obj):
        """Return the course rating."""
        return round(obj.rating_total / obj.rating_count if obj.rating_count else 0, 1)

    def get_start_enrollment_date(self, obj):
        """Return the start enrollment date."""
        return obj.enrollment_start

    def get_end_enrollment_date(self, obj):
        """Return the end enrollment date."""
        return obj.enrollment_end

    def get_image_url(self, obj):
        """Return the course image URL."""
        return obj.course_image_url

    def get_tenant_ids(self, obj):
        """Return the tenant IDs."""
        return get_tenants_by_org(obj.org)

    def get_start_date(self, obj):
        """Return the start date."""
        return obj.start

    def get_end_date(self, obj):
        """Return the end date."""
        return obj.end

    def get_author_name(self, obj):  # pylint: disable=unused-argument
        """Return the author name."""
        return None
