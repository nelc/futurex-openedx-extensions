"""Serializers for the dashboard details API."""
from __future__ import annotations

import re
from typing import Any

from django.contrib.auth import get_user_model
from django.utils.timezone import now
from lms.djangoapps.certificates.api import get_certificates_for_user_by_course_keys
from lms.djangoapps.courseware.courses import get_course_blocks_completion_summary
from lms.djangoapps.grades.api import CourseGradeFactory
from openedx.core.djangoapps.content.block_structure.api import get_block_structure_manager
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from openedx.core.djangoapps.user_api.accounts.serializers import AccountLegacyProfileSerializer
from rest_framework import serializers
from rest_framework.fields import empty

from futurex_openedx_extensions.helpers.constants import (
    COURSE_ACCESS_ROLES_GLOBAL,
    COURSE_STATUS_SELF_PREFIX,
    COURSE_STATUSES,
)
from futurex_openedx_extensions.helpers.converters import relative_url_to_absolute_url
from futurex_openedx_extensions.helpers.models import DataExportTask
from futurex_openedx_extensions.helpers.roles import (
    RoleType,
    get_course_access_roles_queryset,
    get_user_course_access_roles,
)
from futurex_openedx_extensions.helpers.tenants import get_tenants_by_org


class DataExportTaskSerializer(serializers.ModelSerializer):
    """Serializer for Data Export Task"""
    class Meta:
        model = DataExportTask
        fields = '__all__'
        read_only_fields = [
            field.name for field in DataExportTask._meta.fields if field.name not in ['notes']
        ]

    def validate_notes(self: Any, value: str) -> str:   # pylint: disable=no-self-use
        """Sanitize the notes field and remove html tags."""
        value = re.sub(r'<[^>]*>', '', value)
        return value


class LearnerBasicDetailsSerializer(serializers.ModelSerializer):
    """Serializer for learner's basic details."""
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

    class Meta:
        model = get_user_model()
        fields = [
            'user_id',
            'full_name',
            'alternative_full_name',
            'username',
            'email',
            'mobile_no',
            'year_of_birth',
            'gender',
            'gender_display',
            'date_joined',
            'last_login',
        ]

    @staticmethod
    def _is_english(text: str) -> bool:
        """
        Checks if a string consists only of characters in the ASCII range (a-z, A-Z, 0-9, and common symbols).

        This method is very basic and may miss valid English text with non-ASCII characters.
        """
        return all(ord(char) < 128 for char in text)

    def _get_name(self, obj: Any, alternative: bool = False) -> str:
        """
        Calculate the full name and alternative full name. We have two issues in the data:
        1. The first and last names in auth.user contain many records with identical values (redundant data).
        2. The name field in the profile sometimes contains data while the first and last names are empty.

        :param obj: The user object.
        :type obj: Any
        :param alternative: Whether to return the alternative full name.
        :type alternative: bool
        :return: The full name or alternative full name.
        """
        first_name = obj.first_name.strip()
        last_name = obj.last_name.strip()

        full_name = first_name or last_name
        if first_name and last_name and not (first_name == last_name and ' ' in first_name):
            full_name = ' '.join(filter(None, (first_name, last_name)))

        profile_name = self._get_profile_field(obj, 'name')
        alt_name = profile_name.strip() if profile_name else ''

        if not full_name:
            full_name, alt_name = alt_name, ''

        if alt_name and not self._is_english(alt_name):
            full_name, alt_name = alt_name, full_name

        return alt_name if alternative else full_name

    @staticmethod
    def _get_profile_field(obj: get_user_model, field_name: str) -> Any:
        """Get the profile field value."""
        return getattr(obj.profile, field_name) if hasattr(obj, 'profile') and obj.profile else None

    def get_user_id(self, obj: get_user_model) -> Any:  # pylint: disable=no-self-use
        """Return user ID."""
        return obj.id

    def get_full_name(self, obj: get_user_model) -> Any:
        """Return full name."""
        return self._get_name(obj)

    def get_alternative_full_name(self, obj: get_user_model) -> Any:
        """Return alternative full name."""
        return self._get_name(obj, alternative=True)

    def get_mobile_no(self, obj: get_user_model) -> Any:
        """Return mobile number."""
        return self._get_profile_field(obj, 'phone_number')

    def get_gender(self, obj: get_user_model) -> Any:
        """Return gender."""
        return self._get_profile_field(obj, 'gender')

    def get_gender_display(self, obj: get_user_model) -> Any:
        """Return readable text for gender"""
        return self._get_profile_field(obj, 'gender_display')

    def get_year_of_birth(self, obj: get_user_model) -> Any:
        """Return year of birth."""
        return self._get_profile_field(obj, 'year_of_birth')


class LearnerDetailsSerializer(LearnerBasicDetailsSerializer):
    """Serializer for learner details."""
    enrolled_courses_count = serializers.SerializerMethodField()
    certificates_count = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = LearnerBasicDetailsSerializer.Meta.fields + [
            'enrolled_courses_count',
            'certificates_count',
        ]

    def get_certificates_count(self, obj: get_user_model) -> Any:  # pylint: disable=no-self-use
        """Return certificates count."""
        return obj.certificates_count

    def get_enrolled_courses_count(self, obj: get_user_model) -> Any:  # pylint: disable=no-self-use
        """Return enrolled courses count."""
        return obj.courses_count


class LearnerDetailsForCourseSerializer(LearnerBasicDetailsSerializer):
    """Serializer for learner details for a course."""
    certificate_available = serializers.BooleanField()
    course_score = serializers.DecimalField(max_digits=5, decimal_places=2)
    active_in_course = serializers.BooleanField()

    class Meta:
        model = get_user_model()
        fields = LearnerBasicDetailsSerializer.Meta.fields + [
            'certificate_available',
            'course_score',
            'active_in_course',
        ]


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
            'city',
            'bio',
            'level_of_education',
            'social_links',
            'image',
            'profile_link',
        ]

    def get_city(self, obj: get_user_model) -> Any:
        """Return city."""
        return self._get_profile_field(obj, 'city')

    def get_bio(self, obj: get_user_model) -> Any:
        """Return bio."""
        return self._get_profile_field(obj, 'bio')

    def get_level_of_education(self, obj: get_user_model) -> Any:
        """Return level of education."""
        return self._get_profile_field(obj, 'level_of_education_display')

    def get_social_links(self, obj: get_user_model) -> Any:  # pylint: disable=no-self-use
        """Return social links."""
        result = {}
        profile = obj.profile if hasattr(obj, 'profile') else None
        if profile:
            links = profile.social_links.all().order_by('platform')
            for link in links:
                result[link.platform] = link.social_link
        return result

    def get_image(self, obj: get_user_model) -> Any:
        """Return image."""
        if hasattr(obj, 'profile') and obj.profile:
            return AccountLegacyProfileSerializer.get_profile_image(
                obj.profile, obj, self.context.get('request')
            )['image_url_large']

        return None

    def get_profile_link(self, obj: get_user_model) -> Any:
        """Return profile link."""
        return relative_url_to_absolute_url(f'/u/{obj.username}/', self.context.get('request'))


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

    class Meta:
        model = CourseOverview
        fields = [
            'id',
            'status',
            'self_paced',
            'start_date',
            'end_date',
            'start_enrollment_date',
            'end_enrollment_date',
            'display_name',
            'image_url',
            'org',
            'tenant_ids',
        ]

    def get_status(self, obj: CourseOverview) -> Any:  # pylint: disable=no-self-use
        """Return the course status."""
        now_time = now()
        if obj.end and obj.end < now_time:
            status = COURSE_STATUSES['archived']
        elif obj.start and obj.start > now_time:
            status = COURSE_STATUSES['upcoming']
        else:
            status = COURSE_STATUSES['active']

        return f'{COURSE_STATUS_SELF_PREFIX if obj.self_paced else ""}{status}'

    def get_start_enrollment_date(self, obj: CourseOverview) -> Any:  # pylint: disable=no-self-use
        """Return the start enrollment date."""
        return obj.enrollment_start

    def get_end_enrollment_date(self, obj: CourseOverview) -> Any:  # pylint: disable=no-self-use
        """Return the end enrollment date."""
        return obj.enrollment_end

    def get_image_url(self, obj: CourseOverview) -> Any:  # pylint: disable=no-self-use
        """Return the course image URL."""
        return obj.course_image_url

    def get_tenant_ids(self, obj: CourseOverview) -> Any:  # pylint: disable=no-self-use
        """Return the tenant IDs."""
        return get_tenants_by_org(obj.org)

    def get_start_date(self, obj: CourseOverview) -> Any:  # pylint: disable=no-self-use
        """Return the start date."""
        return obj.start

    def get_end_date(self, obj: CourseOverview) -> Any:  # pylint: disable=no-self-use
        """Return the end date."""
        return obj.end


class CourseDetailsSerializer(CourseDetailsBaseSerializer):
    """Serializer for course details."""
    rating = serializers.SerializerMethodField()
    enrolled_count = serializers.IntegerField()
    active_count = serializers.IntegerField()
    certificates_count = serializers.IntegerField()
    completion_rate = serializers.FloatField()

    class Meta:
        model = CourseOverview
        fields = CourseDetailsBaseSerializer.Meta.fields + [
            'rating',
            'enrolled_count',
            'active_count',
            'certificates_count',
            'completion_rate',
        ]

    def get_rating(self, obj: CourseOverview) -> Any:  # pylint: disable=no-self-use
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
            'enrollment_date',
            'last_activity',
            'certificate_url',
            'progress_url',
            'grades_url',
            'progress',
            'grade',
        ]

    def get_certificate_url(self, obj: CourseOverview) -> Any:  # pylint: disable=no-self-use
        """Return the certificate URL."""
        user = get_user_model().objects.get(id=obj.related_user_id)
        certificate = get_certificates_for_user_by_course_keys(user, [obj.id])
        if certificate and str(obj.id) in certificate:
            return certificate[str(obj.id)].get('download_url')

        return None

    def get_progress_url(self, obj: CourseOverview) -> Any:
        """Return the certificate URL."""
        return relative_url_to_absolute_url(
            f'/learning/course/{obj.id}/progress/{obj.related_user_id}/',
            self.context.get('request')
        )

    def get_grades_url(self, obj: CourseOverview) -> Any:
        """Return the certificate URL."""
        return relative_url_to_absolute_url(
            f'/gradebook/{obj.id}/',
            self.context.get('request')
        )

    def get_progress(self, obj: CourseOverview) -> Any:  # pylint: disable=no-self-use
        """Return the certificate URL."""
        user = get_user_model().objects.get(id=obj.related_user_id)
        return get_course_blocks_completion_summary(obj.id, user)

    def get_grade(self, obj: CourseOverview) -> Any:  # pylint: disable=no-self-use
        """Return the grade summary."""
        collected_block_structure = get_block_structure_manager(obj.id).get_collected()
        course_grade = CourseGradeFactory().read(
            get_user_model().objects.get(id=obj.related_user_id),
            collected_block_structure=collected_block_structure
        )

        return {
            'percent': course_grade.percent,
            'letter_grade': course_grade.letter_grade,
            'is_passing': course_grade.passed,
        }


class UserRolesSerializer(LearnerBasicDetailsSerializer):
    """Serializer for user roles."""
    tenants = serializers.SerializerMethodField()
    global_roles = serializers.SerializerMethodField()

    def __init__(self, instance: Any | None = None, data: Any = empty, **kwargs: Any):
        """Initialize the serializer."""
        self._org_tenant: dict[str, list[int]] = {}
        self._roles_data: dict[Any, Any] = {}

        permission_info = kwargs['context']['request'].fx_permission_info
        self.orgs_filter = permission_info['view_allowed_any_access_orgs']
        self.permitted_tenant_ids = permission_info['view_allowed_tenant_ids_any_access']
        self.query_params = self.parse_query_params(kwargs['context']['request'].query_params)

        if instance:
            self.construct_roles_data(instance if isinstance(instance, list) else [instance])

        super().__init__(instance, data, **kwargs)

    @staticmethod
    def parse_query_params(query_params: dict[str, Any]) -> dict[str, Any]:
        """
        Parse the query parameters.

        :param query_params: The query parameters.
        :type query_params: dict[str, Any]
        """
        result = {
            'search_text': query_params.get('search_text', ''),
            'course_ids_filter': query_params[
                'only_course_ids'
            ].split(',') if query_params.get('only_course_ids') else [],
            'roles_filter': query_params.get('only_roles', '').split(',') if query_params.get('only_roles') else [],
        }

        if query_params.get('active_users_filter') is not None:
            result['active_filter'] = query_params['active_users_filter'] == '1'
        else:
            result['active_filter'] = None

        exclude_tenant_roles = False
        exclude_course_roles = False
        if query_params.get('exclude_tenant_roles') is not None:
            exclude_tenant_roles = query_params['exclude_tenant_roles'] == '1'

        if not exclude_tenant_roles and query_params.get('exclude_course_roles') is not None:
            exclude_course_roles = query_params['exclude_course_roles'] == '1'

        if exclude_tenant_roles:
            result['exclude_role_type'] = RoleType.ORG_WIDE
        elif exclude_course_roles:
            result['exclude_role_type'] = RoleType.COURSE_SPECIFIC
        else:
            result['exclude_role_type'] = None

        return result

    def get_org_tenants(self, org: str) -> list[int]:
        """
        Get the tenants for an organization.

        :param org: The organization to get the tenants for.
        :type org: str
        :return: The tenants.
        :rtype: list[int]
        """
        result = self._org_tenant.get(org)
        if not result:
            result = get_tenants_by_org(org)
            self._org_tenant[org] = result

        return result or []

    def construct_roles_data(self, users: list[get_user_model]) -> None:
        """
        Construct the roles data.

        {
            "<userID>": {
                "<tenantID>": {
                    "tenant_roles": ["<roleName>", "<roleName>"],
                    "course_roles": {
                        "<courseID>": ["<roleName>", "<roleName>"],
                        "<courseID>": ["<roleName>", "<roleName>"],
                    },
                },
                ....
            },
            ....
        }

        :param users: The user instances.
        :type users: list[get_user_model]
        """
        self._roles_data = {}
        for user in users:
            self._roles_data[user.id] = {}

        records = get_course_access_roles_queryset(
            self.orgs_filter,
            remove_redundant=True,
            users=users,
            search_text=self.query_params['search_text'],
            roles_filter=self.query_params['roles_filter'],
            active_filter=self.query_params['active_filter'],
            course_ids_filter=self.query_params['course_ids_filter'],
            exclude_role_type=self.query_params['exclude_role_type'],
        )

        for record in records or []:
            usr_data = self._roles_data[record.user_id]
            for tenant_id in self.get_org_tenants(record.org):
                if tenant_id not in self.permitted_tenant_ids:
                    continue

                if tenant_id not in usr_data:
                    usr_data[tenant_id] = {
                        'tenant_roles': [],
                        'course_roles': {},
                    }

                course_id = str(record.course_id) if record.course_id else None
                if course_id and course_id not in usr_data[tenant_id]['course_roles']:
                    usr_data[tenant_id]['course_roles'][course_id] = []

                if course_id:
                    usr_data[tenant_id]['course_roles'][course_id].append(record.role)
                elif record.role not in usr_data[tenant_id]['tenant_roles']:
                    usr_data[tenant_id]['tenant_roles'].append(record.role)

    @property
    def roles_data(self) -> dict[Any, Any] | None:
        """Get the roles data."""
        return self._roles_data

    def get_tenants(self, obj: get_user_model) -> Any:
        """Return the tenants."""
        return self.roles_data.get(obj.id, {}) if self.roles_data else {}

    def get_global_roles(self, obj: get_user_model) -> Any:  # pylint:disable=no-self-use
        """Return the global roles."""
        roles_dict = get_user_course_access_roles(obj)['roles']
        return [role for role in roles_dict if role in COURSE_ACCESS_ROLES_GLOBAL]

    class Meta:
        model = get_user_model()
        fields = [
            'user_id',
            'email',
            'username',
            'full_name',
            'alternative_full_name',
            'global_roles',
            'tenants',
        ]
