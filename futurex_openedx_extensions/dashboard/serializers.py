"""Serializers for the dashboard details API."""
from django.contrib.auth import get_user_model
from django.utils.timezone import now
from lms.djangoapps.certificates.api import get_certificates_for_user_by_course_keys
from lms.djangoapps.courseware.courses import get_course_blocks_completion_summary
from lms.djangoapps.grades.api import CourseGradeFactory
from opaque_keys.edx.keys import CourseKey
from openedx.core.djangoapps.content.block_structure.api import get_block_structure_manager
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from openedx.core.djangoapps.user_api.accounts.serializers import AccountLegacyProfileSerializer
from rest_framework import serializers

from futurex_openedx_extensions.helpers.constants import COURSE_STATUS_SELF_PREFIX, COURSE_STATUSES
from futurex_openedx_extensions.helpers.converters import relative_url_to_absolute_url
from futurex_openedx_extensions.helpers.tenants import get_tenants_by_org


class LearnerDetailsSerializer(serializers.ModelSerializer):
    """Serializer for learner details."""
    user_id = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    alternative_full_name = serializers.SerializerMethodField()
    username = serializers.CharField()
    email = serializers.EmailField()
    mobile_no = serializers.SerializerMethodField()
    year_of_birth = serializers.SerializerMethodField()
    gender = serializers.SerializerMethodField()
    gender_display = serializers.SerializerMethodField()
    date_joined = serializers.DateTimeField()
    last_login = serializers.DateTimeField()
    enrolled_courses_count = serializers.SerializerMethodField()
    certificates_count = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = [
            "user_id",
            "full_name",
            "alternative_full_name",
            "username",
            "email",
            "mobile_no",
            "year_of_birth",
            "gender",
            "gender_display",
            "date_joined",
            "last_login",
            "enrolled_courses_count",
            "certificates_count",
        ]

    def _get_names(self, obj, alternative=False):
        """
        Calculate the full name and alternative full name. We have two issues in the data:
        1. The first and last names in auth.user contain many records with identical values (redundant data).
        2. The name field in the profile sometimes contains data while the first and last names are empty.
        """
        first_name = obj.first_name.strip()
        last_name = obj.last_name.strip()
        alt_name = (self._get_profile_field(obj, "name") or "").strip()

        if not last_name:
            full_name = first_name
        elif not first_name:
            full_name = last_name
        elif first_name == last_name and " " in first_name:
            full_name = first_name
        else:
            full_name = f"{first_name} {last_name}"

        if alt_name == full_name:
            alt_name = ""

        if not full_name and alt_name:
            full_name = alt_name
            alt_name = ""

        if alt_name and ord(alt_name[0]) > 127 >= ord(full_name[0]):
            names = alt_name, full_name
        else:
            names = full_name, alt_name

        return names[0] if not alternative else names[1]

    @staticmethod
    def _get_profile_field(obj, field_name):
        """Get the profile field value."""
        return getattr(obj.profile, field_name) if hasattr(obj, "profile") and obj.profile else None

    def get_user_id(self, obj):  # pylint: disable=no-self-use
        """Return user ID."""
        return obj.id

    def get_full_name(self, obj):
        """Return full name."""
        return self._get_names(obj)

    def get_alternative_full_name(self, obj):
        """Return alternative full name."""
        return self._get_names(obj, alternative=True)

    def get_mobile_no(self, obj):
        """Return mobile number."""
        return self._get_profile_field(obj, "phone_number")

    def get_gender(self, obj):
        """Return gender."""
        return self._get_profile_field(obj, "gender")

    def get_gender_display(self, obj):
        """Return readable text for gender"""
        return self._get_profile_field(obj, "gender_display")

    def get_certificates_count(self, obj):  # pylint: disable=no-self-use
        """Return certificates count."""
        return obj.certificates_count

    def get_enrolled_courses_count(self, obj):  # pylint: disable=no-self-use
        """Return enrolled courses count."""
        return obj.courses_count

    def get_year_of_birth(self, obj):
        """Return year of birth."""
        return self._get_profile_field(obj, "year_of_birth")


class LearnerDetailsExtendedSerializer(LearnerDetailsSerializer):
    """Serializer for extended learner details."""
    city = serializers.SerializerMethodField()
    bio = serializers.SerializerMethodField()
    level_of_education = serializers.SerializerMethodField()
    social_links = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    profile_link = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = LearnerDetailsSerializer.Meta.fields + [
            "city",
            "bio",
            "level_of_education",
            "social_links",
            "image",
            "profile_link",
        ]

    def get_city(self, obj):
        """Return city."""
        return self._get_profile_field(obj, "city")

    def get_bio(self, obj):
        """Return bio."""
        return self._get_profile_field(obj, "bio")

    def get_level_of_education(self, obj):
        """Return level of education."""
        return self._get_profile_field(obj, "level_of_education_display")

    def get_social_links(self, obj):  # pylint: disable=no-self-use
        """Return social links."""
        result = {}
        profile = obj.profile if hasattr(obj, "profile") else None
        if profile:
            links = profile.social_links.all().order_by('platform')
            for link in links:
                result[link.platform] = link.social_link
        return result

    def get_image(self, obj):
        """Return image."""
        if hasattr(obj, "profile") and obj.profile:
            return AccountLegacyProfileSerializer.get_profile_image(
                obj.profile, obj, self.context.get('request')
            )["image_url_large"]

        return None

    def get_profile_link(self, obj):
        """Return profile link."""
        return relative_url_to_absolute_url(f"/u/{obj.username}/", self.context.get('request'))


class CourseDetailsBaseSerializer(serializers.ModelSerializer):
    """Serializer for course details."""
    status = serializers.SerializerMethodField()
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
            "id",
            "status",
            "self_paced",
            "start_date",
            "end_date",
            "start_enrollment_date",
            "end_enrollment_date",
            "display_name",
            "image_url",
            "org",
            "tenant_ids",
            "author_name",
        ]

    def get_status(self, obj):  # pylint: disable=no-self-use
        """Return the course status."""
        now_time = now()
        if obj.end and obj.end < now_time:
            status = COURSE_STATUSES["archived"]
        elif obj.start and obj.start > now_time:
            status = COURSE_STATUSES["upcoming"]
        else:
            status = COURSE_STATUSES["active"]

        return f'{COURSE_STATUS_SELF_PREFIX if obj.self_paced else ""}{status}'

    def get_start_enrollment_date(self, obj):  # pylint: disable=no-self-use
        """Return the start enrollment date."""
        return obj.enrollment_start

    def get_end_enrollment_date(self, obj):  # pylint: disable=no-self-use
        """Return the end enrollment date."""
        return obj.enrollment_end

    def get_image_url(self, obj):  # pylint: disable=no-self-use
        """Return the course image URL."""
        return obj.course_image_url

    def get_tenant_ids(self, obj):  # pylint: disable=no-self-use
        """Return the tenant IDs."""
        return get_tenants_by_org(obj.org)

    def get_start_date(self, obj):  # pylint: disable=no-self-use
        """Return the start date."""
        return obj.start

    def get_end_date(self, obj):  # pylint: disable=no-self-use
        """Return the end date."""
        return obj.end

    def get_author_name(self, obj):  # pylint: disable=unused-argument,no-self-use
        """Return the author name."""
        return None


class CourseDetailsSerializer(CourseDetailsBaseSerializer):
    """Serializer for course details."""
    rating = serializers.SerializerMethodField()
    enrolled_count = serializers.IntegerField()
    active_count = serializers.IntegerField()
    certificates_count = serializers.IntegerField()

    class Meta:
        model = CourseOverview
        fields = CourseDetailsBaseSerializer.Meta.fields + [
            "rating",
            "enrolled_count",
            "active_count",
            "certificates_count",
        ]

    def get_rating(self, obj):  # pylint: disable=no-self-use
        """Return the course rating."""
        return round(obj.rating_total / obj.rating_count if obj.rating_count else 0, 1)


class LearnerCoursesDetailsSerializer(CourseDetailsBaseSerializer):
    """Serializer for learner's courses details."""
    enrollment_date = serializers.DateTimeField()
    last_activity = serializers.DateTimeField()
    certificate_url = serializers.SerializerMethodField()
    progress_url = serializers.SerializerMethodField()
    grades_url = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    grade = serializers.SerializerMethodField()

    class Meta:
        model = CourseOverview
        fields = CourseDetailsBaseSerializer.Meta.fields + [
            "enrollment_date",
            "last_activity",
            "certificate_url",
            "progress_url",
            "grades_url",
            "progress",
            "grade",
        ]

    def get_certificate_url(self, obj):  # pylint: disable=no-self-use
        """Return the certificate URL."""
        user = get_user_model().objects.get(id=obj.related_user_id)
        certificate = get_certificates_for_user_by_course_keys(user, [obj.id])
        if certificate and obj.id in certificate:
            return certificate[obj.id].get("download_url")

        return None

    def get_progress_url(self, obj):
        """Return the certificate URL."""
        return relative_url_to_absolute_url(
            f"/learning/course/{obj.id}/progress/{obj.related_user_id}/",
            self.context.get('request')
        )

    def get_grades_url(self, obj):
        """Return the certificate URL."""
        return relative_url_to_absolute_url(
            f"/gradebook/{obj.id}/",
            self.context.get('request')
        )

    def get_progress(self, obj):  # pylint: disable=no-self-use
        """Return the certificate URL."""
        user = get_user_model().objects.get(id=obj.related_user_id)
        return get_course_blocks_completion_summary(obj.id, user)

    def get_grade(self, obj):  # pylint: disable=no-self-use
        """Return the certificate URL."""
        collected_block_structure = get_block_structure_manager(obj.id).get_collected()
        course_grade = CourseGradeFactory().read(
            get_user_model().objects.get(id=obj.related_user_id),
            collected_block_structure=collected_block_structure
        )
        course_grade.update(visible_grades_only=True, has_staff_access=False)

        return course_grade
