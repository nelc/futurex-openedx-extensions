"""Course-related serializers for the dashboard API."""
from __future__ import annotations

import re
from typing import Any

from common.djangoapps.student.auth import add_users
from common.djangoapps.student.models import CourseEnrollment
from common.djangoapps.student.roles import CourseInstructorRole, CourseStaffRole
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.timezone import now
from eox_nelp.course_experience.models import FeedbackCourse
from lms.djangoapps.courseware.courses import get_course_blocks_completion_summary
from lms.djangoapps.grades.api import CourseGradeFactory
from openedx.core.djangoapps.content.block_structure.api import get_block_structure_manager
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from openedx.core.djangoapps.discussions.models import DiscussionsConfiguration
from openedx.core.djangoapps.django_comment_common.models import assign_default_role
from openedx.core.djangoapps.django_comment_common.utils import seed_permissions_roles
from organizations.api import add_organization_course, ensure_organization
from rest_framework import serializers
from xmodule.course_block import CourseFields
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.django import modulestore
from xmodule.modulestore.exceptions import DuplicateCourseError

from futurex_openedx_extensions.helpers.constants import (
    COURSE_STATUS_SELF_PREFIX,
    COURSE_STATUSES,
)
from futurex_openedx_extensions.helpers.converters import (
    DEFAULT_DATETIME_FORMAT,
    dt_to_str,
    relative_url_to_absolute_url,
)
from futurex_openedx_extensions.helpers.extractors import extract_arabic_name_from_user, extract_full_name_from_user
from futurex_openedx_extensions.helpers.tenants import (
    get_all_tenants_info,
    get_org_to_tenant_map,
    get_tenants_by_org,
    set_request_domain_by_org,
)
from futurex_openedx_extensions.helpers.certificates import get_certificate_url


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
        return dt_to_str(obj.enrollment_start)

    def get_end_enrollment_date(self, obj: CourseOverview) -> Any:  # pylint: disable=no-self-use
        """Return the end enrollment date."""
        return dt_to_str(obj.enrollment_end)

    def get_image_url(self, obj: CourseOverview) -> Any:  # pylint: disable=no-self-use
        """Return the course image URL."""
        return obj.course_image_url

    def get_tenant_ids(self, obj: CourseOverview) -> Any:  # pylint: disable=no-self-use
        """Return the tenant IDs."""
        return get_tenants_by_org(obj.org)

    def get_start_date(self, obj: CourseOverview) -> Any:  # pylint: disable=no-self-use
        """Return the start date."""
        return dt_to_str(obj.start)

    def get_end_date(self, obj: CourseOverview) -> Any:  # pylint: disable=no-self-use
        """Return the end date."""
        return dt_to_str(obj.end)


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


class CourseCreateSerializer(serializers.Serializer):
    """Serializer for course create."""
    COURSE_NUMBER_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
    MAX_COURSE_ID_LENGTH = 250

    tenant_id = serializers.IntegerField(
        help_text='Tenant ID for the course. Must be a valid tenant ID.',
    )
    number = serializers.CharField(help_text='Course code number, like "CS101"')
    run = serializers.CharField(help_text='Course run, like "2023_Fall"')
    display_name = serializers.CharField(
        help_text='Display name of the course.',
    )
    start = serializers.DateTimeField(
        required=False,
        help_text='Start date of the course.',
    )
    end = serializers.DateTimeField(
        required=False,
        help_text='End date of the course.',
    )
    enrollment_start = serializers.DateTimeField(
        required=False,
        help_text='Start date of the course enrollment.',
    )
    enrollment_end = serializers.DateTimeField(
        required=False,
        help_text='End date of the course enrollment.',
    )
    self_paced = serializers.BooleanField(
        default=False,
        help_text='If true, the course is self-paced. If false, the course is instructor-paced.',
    )
    invitation_only = serializers.BooleanField(
        default=False,
        help_text='If true, the course enrollment is invitation-only.',
    )
    language = serializers.ChoiceField(
        choices=[],
        required=False,
        help_text='Language code for the course, like "en" for English.',
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the serializer."""
        super().__init__(*args, **kwargs)
        self._default_org = ''
        self.fields['language'].choices = getattr(settings, 'FX_ALLOWED_COURSE_LANGUAGE_CODES', [])

    @property
    def default_org(self) -> str:
        """Get the default organization for the tenant."""
        return self._default_org

    def get_absolute_url(self) -> str | None:
        """Get the absolute URL for the course."""
        if not self.default_org:
            raise serializers.ValidationError('Default organization is not set. Call validate_tenant_id first.')

        course_id = f'course-v1:{self.default_org}+{self.validated_data["number"]}+{self.validated_data["run"]}'
        set_request_domain_by_org(self.context.get('request'), self.default_org)
        return relative_url_to_absolute_url(f'/courses/{course_id}/', self.context.get('request'))

    def validate_tenant_id(self, tenant_id: Any) -> Any:
        """Validate the tenant ID."""
        default_orgs = get_all_tenants_info().get('default_org_per_tenant', {})
        if tenant_id not in default_orgs:
            raise serializers.ValidationError(
                f'Invalid tenant_id: {tenant_id}. This tenant does not exist or is not configured properly.'
            )

        if not default_orgs[tenant_id]:
            raise serializers.ValidationError(
                f'No default organization configured for tenant_id: {tenant_id}.'
            )
        if tenant_id not in get_org_to_tenant_map().get(default_orgs[tenant_id], []):
            raise serializers.ValidationError(
                f'Invalid default organization ({default_orgs[tenant_id]}) configured for tenant ID {tenant_id}.'
            )
        self._default_org = default_orgs[tenant_id]
        return tenant_id

    def validate_number(self, value: str) -> str:
        """Validate that number matches COURSE_NUMBER_PATTERN."""
        if not self.COURSE_NUMBER_PATTERN.match(value):
            raise serializers.ValidationError(
                f'Invalid number ({value}). Only alphanumeric characters, underscores, and hyphens are allowed.'
            )
        return value

    def validate_run(self, value: str) -> str:
        """Validate that run matches COURSE_NUMBER_PATTERN."""
        if not self.COURSE_NUMBER_PATTERN.match(value):
            raise serializers.ValidationError(
                f'Invalid run ({value}). Only alphanumeric characters, underscores, and hyphens are allowed.'
            )
        return value

    def validate(self, attrs: dict) -> dict:
        """Validate the course creation data."""
        number = attrs.get('number', '')
        run = attrs.get('run', '')
        if len(f'course-v1:{self.default_org}+{number}+{run}') > self.MAX_COURSE_ID_LENGTH:
            raise serializers.ValidationError(
                f'Course ID is too long. The maximum length is {self.MAX_COURSE_ID_LENGTH} characters.'
            )

        dates = {
            'start': attrs.get('start', CourseFields.start.default),
            'end': attrs.get('end'),
            'enrollment_start': attrs.get('enrollment_start', CourseFields.enrollment_start.default),
            'enrollment_end': attrs.get('enrollment_end'),
        }
        greater_or_equal_rules = [
            ('end', 'start'),
            ('enrollment_end', 'enrollment_start'),
            ('start', 'enrollment_start'),
            ('end', 'enrollment_end'),
        ]
        for rule in greater_or_equal_rules:
            lvalue, rvalue = rule
            if dates[lvalue] and dates[rvalue] and dates[lvalue] < dates[rvalue]:
                raise serializers.ValidationError(
                    f'{lvalue} cannot be before {rvalue}. {lvalue}[{dates[lvalue]}], {rvalue}[{dates[rvalue]}]'
                )

        return attrs

    @staticmethod
    def update_course_discussions_settings(course: Any) -> None:
        """
        Add course discussion settings to the course.
        CMS References: cms.djangoapps.contentstore.utils.update_course_discussions_settings
        """
        provider = DiscussionsConfiguration.get(context_key=course.id).provider_type
        course.discussions_settings['provider_type'] = provider
        modulestore().update_item(course, course.published_by)

    @staticmethod
    def initialize_permissions(course: Any, user: get_user_model) -> None:
        """
        seeds permissions, enrolls the user, and assigns the default role for the course.

        CMS Reference: cms.djangoapps.contentstore.utils.initialize_permissions
        """
        seed_permissions_roles(course.id)
        CourseEnrollment.enroll(user, course.id)
        assign_default_role(course.id, user)

    @staticmethod
    def add_roles_and_permissions(course: Any, user: get_user_model) -> None:
        """
        Assigns instructor and staff roles and required permissions
        """
        CourseInstructorRole(course.id).add_users(user)
        add_users(user, CourseStaffRole(course.id), user)
        CourseCreateSerializer.initialize_permissions(course, user)

    def create(self, validated_data: dict) -> Any:
        """
        Create new course.

        TODO: Update code to create rerun.
        """
        user = self.context['request'].user
        tenant_id = validated_data['tenant_id']
        org = get_all_tenants_info()['default_org_per_tenant'][tenant_id]
        number = validated_data.get('number')
        run = validated_data['run']

        field_names = [
            'start',
            'end',
            'enrollment_start',
            'enrollment_end',
            'language',
            'self_paced',
            'invitation_only',
            'display_name',
        ]
        fields = {
            field_name: validated_data.get(field_name) for field_name in field_names if field_name in validated_data
        }

        try:
            org_data = ensure_organization(org)
        except Exception as exc:
            raise serializers.ValidationError(
                'Organization does not exist. Please add the organization before proceeding.'
            ) from exc

        try:
            store = modulestore().default_modulestore.get_modulestore_type()
            with modulestore().default_store(store):
                new_course = modulestore().create_course(
                    org,
                    number,
                    run,
                    user.id,
                    fields=fields,
                )
                self.add_roles_and_permissions(new_course, user)
            add_organization_course(org_data, new_course.id)
            self.update_course_discussions_settings(new_course)
        except DuplicateCourseError as exc:
            raise serializers.ValidationError(
                f'Course with org: {org}, number: {number}, run: {run} already exists.'
            ) from exc

        return new_course

    def update(self, instance: Any, validated_data: Any) -> Any:
        """Not implemented: Update an existing object."""
        raise ValueError('This serializer does not support update.')


class LearnerCoursesDetailsSerializer(CourseDetailsBaseSerializer):
    """Serializer for learner's courses details."""
    enrollment_date = serializers.DateTimeField(format=DEFAULT_DATETIME_FORMAT)
    last_activity = serializers.DateTimeField(format=DEFAULT_DATETIME_FORMAT)
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

    def get_certificate_url(self, obj: CourseOverview) -> Any:
        """Return the certificate URL."""
        user = get_user_model().objects.get(id=obj.related_user_id)
        return get_certificate_url(self.context.get('request'), user, obj.id)

    def get_progress_url(self, obj: CourseOverview) -> Any:
        """Return the certificate URL."""
        set_request_domain_by_org(self.context.get('request'), obj.org)
        return relative_url_to_absolute_url(
            f'/learning/course/{obj.id}/progress/{obj.related_user_id}/',
            self.context.get('request')
        )

    def get_grades_url(self, obj: CourseOverview) -> Any:
        """Return the certificate URL."""
        set_request_domain_by_org(self.context.get('request'), obj.org)
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


class LibrarySerializer(serializers.Serializer):
    """Serializer for library."""
    library_key = serializers.CharField(source='location.library_key', read_only=True)
    edited_by = serializers.IntegerField(source='_edited_by', read_only=True)
    edited_on = serializers.DateTimeField(source='_edited_on', read_only=True)
    tenant_ids = serializers.SerializerMethodField(read_only=True)
    display_name = serializers.CharField()
    tenant_id = serializers.IntegerField(write_only=True)
    number = serializers.CharField(write_only=True)

    def get_tenant_ids(self, obj: Any) -> Any:  # pylint: disable=no-self-use
        """Return the tenant IDs."""
        return get_tenants_by_org(obj.location.library_key.org)

    def validate_tenant_id(self, tenant_id: Any) -> Any:  # pylint: disable=no-self-use
        """Validate the tenant ID."""
        default_orgs = get_all_tenants_info().get('default_org_per_tenant', {})
        if tenant_id not in default_orgs:
            raise serializers.ValidationError(
                f'Invalid tenant_id: "{tenant_id}". This tenant does not exist or is not configured properly.'
            )
        if not default_orgs[tenant_id]:
            raise serializers.ValidationError(
                f'No default organization configured for tenant_id: "{tenant_id}".'
            )
        if tenant_id not in get_org_to_tenant_map().get(default_orgs[tenant_id], []):
            raise serializers.ValidationError(
                f'Invalid default organization "{default_orgs[tenant_id]}" configured for tenant ID "{tenant_id}". '
                'This organization is not associated with the tenant.'
            )
        return tenant_id

    def create(self, validated_data: Any) -> Any:
        """Create new library object."""
        user = self.context['request'].user
        tenant_id = validated_data['tenant_id']
        org = get_all_tenants_info()['default_org_per_tenant'][tenant_id]
        try:
            store = modulestore()
            with store.default_store(ModuleStoreEnum.Type.split):
                library = store.create_library(
                    org=org,
                    library=validated_data['number'],
                    user_id=user.id,
                    fields={
                        'display_name': validated_data['display_name']
                    },
                )
            # can't use auth.add_users here b/c it requires user to already have Instructor perms in this course
            CourseInstructorRole(library.location.library_key).add_users(user)
            add_users(user, CourseStaffRole(library.location.library_key), user)
            return library
        except DuplicateCourseError as exc:
            raise serializers.ValidationError(
                f'Library with org: {org} and number: {validated_data["number"]} already exists.'
            ) from exc

    def update(self, instance: Any, validated_data: Any) -> Any:
        """Not implemented: Update an existing object."""
        raise ValueError('This serializer does not support update.')

    def to_representation(self, instance: Any) -> dict:
        """Return representation."""
        instance.org = instance.location.library_key.org
        rep = super().to_representation(instance)
        return rep


class CoursesFeedbackSerializer(serializers.ModelSerializer):
    """Serializer for courses feedback."""
    course_id = serializers.SerializerMethodField()
    course_name = serializers.SerializerMethodField()
    author_username = serializers.SerializerMethodField()
    author_full_name = serializers.SerializerMethodField()
    author_altternative_full_name = serializers.SerializerMethodField()
    author_email = serializers.SerializerMethodField()

    class Meta:
        model = FeedbackCourse
        fields = (
            'id', 'course_id', 'course_name', 'author_username', 'author_full_name', 'author_altternative_full_name',
            'author_email', 'rating_content', 'feedback', 'public', 'rating_instructors', 'recommended'
        )

    def get_course_id(self, obj: FeedbackCourse) -> str:  # pylint: disable=no-self-use
        """Get course id"""
        return str(obj.course_id.id)

    def get_course_name(self, obj: FeedbackCourse) -> str:  # pylint: disable=no-self-use
        """Get course id"""
        return obj.course_id.display_name

    def get_author_username(self, obj: FeedbackCourse) -> str:  # pylint: disable=no-self-use
        """Get course id"""
        return str(obj.author.username)

    def get_author_email(self, obj: FeedbackCourse) -> str:  # pylint: disable=no-self-use
        """Get course id"""
        return str(obj.author.email)

    def get_author_full_name(self, obj: FeedbackCourse) -> str:  # pylint: disable=no-self-use
        """Return full name."""
        return extract_full_name_from_user(obj.author)

    def get_author_altternative_full_name(self, obj: FeedbackCourse) -> str:  # pylint: disable=no-self-use
        """Return alternative full name."""
        return (
            extract_arabic_name_from_user(obj.author) or
            extract_full_name_from_user(obj.author, alternative=True)
        )
