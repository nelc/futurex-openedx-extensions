"""Serializers for the dashboard details API."""
# pylint: disable=too-many-lines
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Tuple

from common.djangoapps.student.auth import add_users
from common.djangoapps.student.models import CourseEnrollment
from common.djangoapps.student.roles import CourseInstructorRole, CourseStaffRole
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.timezone import now
from eox_nelp.course_experience.models import FeedbackCourse
from eox_tenant.models import TenantConfig
from lms.djangoapps.courseware.courses import get_course_blocks_completion_summary
from lms.djangoapps.grades.api import CourseGradeFactory
from lms.djangoapps.grades.context import grading_context_for_course
from lms.djangoapps.grades.models import PersistentSubsectionGrade
from opaque_keys.edx.locator import CourseLocator
from openedx.core.djangoapps.content.block_structure.api import get_block_structure_manager
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from openedx.core.djangoapps.discussions.models import DiscussionsConfiguration
from openedx.core.djangoapps.django_comment_common.models import assign_default_role
from openedx.core.djangoapps.django_comment_common.utils import seed_permissions_roles
from openedx.core.djangoapps.user_api.accounts.serializers import AccountLegacyProfileSerializer
from openedx.core.lib.courses import get_course_by_id
from organizations.api import add_organization_course, ensure_organization
from rest_framework import serializers
from rest_framework.fields import empty
from social_django.models import UserSocialAuth
from xmodule.course_block import CourseFields
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.django import modulestore
from xmodule.modulestore.exceptions import DuplicateCourseError

from futurex_openedx_extensions.dashboard.custom_serializers import (
    ModelSerializerOptionalFields,
    SerializerOptionalMethodField,
)
from futurex_openedx_extensions.helpers.certificates import get_certificate_url
from futurex_openedx_extensions.helpers.constants import (
    ALLOWED_FILE_EXTENSIONS,
    COURSE_ACCESS_ROLES_GLOBAL,
    COURSE_STATUS_SELF_PREFIX,
    COURSE_STATUSES,
)
from futurex_openedx_extensions.helpers.converters import (
    DEFAULT_DATETIME_FORMAT,
    dt_to_str,
    relative_url_to_absolute_url,
)
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.export_csv import get_exported_file_url
from futurex_openedx_extensions.helpers.extractors import (
    extract_arabic_name_from_user,
    extract_full_name_from_user,
    import_from_path,
)
from futurex_openedx_extensions.helpers.models import DataExportTask, TenantAsset
from futurex_openedx_extensions.helpers.roles import (
    RoleType,
    get_course_access_roles_queryset,
    get_user_course_access_roles,
)
from futurex_openedx_extensions.helpers.tenants import (
    get_all_tenants_info,
    get_org_to_tenant_map,
    get_sso_sites,
    get_tenants_by_org,
)

logger = logging.getLogger(__name__)


class DataExportTaskSerializer(ModelSerializerOptionalFields):
    """Serializer for Data Export Task"""
    download_url = SerializerOptionalMethodField(field_tags=['download_url'])

    class Meta:
        model = DataExportTask
        fields = [
            'id',
            'user_id',
            'tenant_id',
            'status',
            'progress',
            'view_name',
            'related_id',
            'filename',
            'notes',
            'created_at',
            'started_at',
            'completed_at',
            'download_url',
            'error_message',
        ]
        read_only_fields = [
            field.name for field in DataExportTask._meta.fields if field.name not in ['notes']
        ]

    def validate_notes(self: Any, value: str) -> str:  # pylint: disable=no-self-use
        """Sanitize the notes field and escape HTML tags."""
        value = re.sub(r'<', '&lt;', value)
        value = re.sub(r'>', '&gt;', value)
        return value

    def get_download_url(self, obj: DataExportTask) -> Any:  # pylint: disable=no-self-use
        """Return download url."""
        return get_exported_file_url(obj)


class LearnerBasicDetailsSerializer(ModelSerializerOptionalFields):
    """Serializer for learner's basic details."""
    user_id = serializers.SerializerMethodField(help_text='User ID in edx-platform')
    full_name = serializers.SerializerMethodField(help_text='Full name of the user')
    alternative_full_name = serializers.SerializerMethodField(help_text='Arabic name (if available)')
    username = serializers.SerializerMethodField(help_text='Username of the user in edx-platform')
    national_id = serializers.SerializerMethodField(help_text='National ID of the user (if available)')
    email = serializers.SerializerMethodField(help_text='Email of the user in edx-platform')
    mobile_no = serializers.SerializerMethodField(help_text='Mobile number of the user (if available)')
    year_of_birth = serializers.SerializerMethodField(help_text='Year of birth of the user (if available)')
    gender = serializers.SerializerMethodField(help_text='Gender code of the user (if available)')
    gender_display = serializers.SerializerMethodField(help_text='Gender of the user (if available)')
    date_joined = serializers.SerializerMethodField(
        help_text='Date when the user was registered in the platform regardless of which tenant',
    )
    last_login = serializers.SerializerMethodField(help_text='Date when the user last logged in')

    class Meta:
        model = get_user_model()
        fields = [
            'user_id',
            'full_name',
            'alternative_full_name',
            'username',
            'national_id',
            'email',
            'mobile_no',
            'year_of_birth',
            'gender',
            'gender_display',
            'date_joined',
            'last_login',
        ]

    def _get_user(self, obj: Any = None) -> get_user_model | None:  # pylint: disable=no-self-use
        """
        Retrieve the associated user for the given object.

        This method can be overridden in child classes to provide a different
        implementation for accessing the user, depending on how the user is
        related to the object (e.g., `obj.user`, `obj.profile.user`, etc.).
        """
        return obj

    def _get_profile_field(self: Any, obj: get_user_model, field_name: str) -> Any:
        """Get the profile field value."""
        user = self._get_user(obj)
        return getattr(user.profile, field_name) if hasattr(user, 'profile') and user.profile else None

    def _get_extra_field(self: Any, obj: get_user_model, field_name: str) -> Any:
        """Get the extra field value."""
        user = self._get_user(obj)
        return getattr(user.extrainfo, field_name) if hasattr(user, 'extrainfo') and user.extrainfo else None

    def get_user_id(self, obj: get_user_model) -> int:
        """Return user ID."""
        return self._get_user(obj).id  # type: ignore

    def get_email(self, obj: get_user_model) -> str:
        """Return user ID."""
        return self._get_user(obj).email  # type: ignore

    def get_username(self, obj: get_user_model) -> str:
        """Return user ID."""
        return self._get_user(obj).username  # type: ignore

    def get_date_joined(self, obj: Any) -> str | None:
        date_joined = self._get_user(obj).date_joined  # type: ignore
        return dt_to_str(date_joined)

    def get_last_login(self, obj: Any) -> str | None:
        last_login = self._get_user(obj).last_login  # type: ignore
        return dt_to_str(last_login)

    def get_national_id(self, obj: get_user_model) -> Any:
        """Return national ID."""
        return self._get_extra_field(obj, 'national_id')

    def get_full_name(self, obj: get_user_model) -> Any:
        """Return full name."""
        return extract_full_name_from_user(self._get_user(obj))

    def get_alternative_full_name(self, obj: get_user_model) -> Any:
        """Return alternative full name."""
        return (
            extract_arabic_name_from_user(self._get_user(obj)) or
            extract_full_name_from_user(self._get_user(obj), alternative=True)
        )

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


class CourseScoreAndCertificateSerializer(ModelSerializerOptionalFields):
    """
    Course Score and Certificate Details Serializer

    Handles data for multiple courses, but exam_scores is included only for a single course when course_id is
    provided in the context. Otherwise, exam_scores is excluded, even if requested in requested_optional_field_tags.
    """
    exam_scores = SerializerOptionalMethodField(field_tags=['exam_scores', 'csv_export'])
    certificate_available = serializers.BooleanField()
    course_score = serializers.FloatField()
    active_in_course = serializers.BooleanField()
    progress = SerializerOptionalMethodField(field_tags=['progress', 'csv_export'])
    certificate_url = SerializerOptionalMethodField(field_tags=['certificate_url', 'csv_export'])

    class Meta:
        fields = [
            'certificate_available',
            'course_score',
            'active_in_course',
            'progress',
            'certificate_url',
            'exam_scores',
        ]

    def __init__(self, *args: Any, **kwargs: Any):
        """Initialize the serializer."""
        super().__init__(*args, **kwargs)
        self._is_exam_name_in_header = self.context.get('omit_subsection_name', '0') != '1'
        self._grading_info: Dict[str, Any] = {}
        self._subsection_locations: Dict[str, Any] = {}

        if self.context.get('course_id'):
            self.collect_grading_info()

    def collect_grading_info(self) -> None:
        """
        Collect the grading info.
        """
        course_id = CourseLocator.from_string(self.context.get('course_id'))
        self._grading_info = {}
        self._subsection_locations = {}
        if not self.is_optional_field_requested('exam_scores'):
            return

        grading_context = grading_context_for_course(get_course_by_id(course_id))
        index = 0
        for assignment_type_name, subsection_infos in grading_context['all_graded_subsections_by_type'].items():
            for subsection_index, subsection_info in enumerate(subsection_infos, start=1):
                header_enum = f' {subsection_index}' if len(subsection_infos) > 1 else ''
                header_name = f'{assignment_type_name}{header_enum}'
                if self.is_exam_name_in_header:
                    header_name += f': {subsection_info["subsection_block"].display_name}'

                self._grading_info[str(index)] = {
                    'header_name': header_name,
                    'location': str(subsection_info['subsection_block'].location),
                }
                self._subsection_locations[str(subsection_info['subsection_block'].location)] = str(index)
                index += 1

    @property
    def is_exam_name_in_header(self) -> bool:
        """Check if the exam name is needed in the header."""
        return self._is_exam_name_in_header

    @property
    def grading_info(self) -> Dict[str, Any]:
        """Get the grading info."""
        return self._grading_info

    @property
    def subsection_locations(self) -> Dict[str, Any]:
        """Get the subsection locations."""
        return self._subsection_locations

    def _get_course_id(self, obj: Any = None) -> Any:
        """Get the course ID. Its helper method required for CourseScoreAndCertificateSerializer"""
        raise NotImplementedError('Child class must implement _get_user method.')

    def _get_user(self, obj: Any = None) -> Any:
        """Get the User. Its helper method required for CourseScoreAndCertificateSerializer"""
        raise NotImplementedError('Child class must implement _get_course_id method.')

    def get_certificate_url(self, obj: Any) -> Any:
        """Return the certificate URL."""
        return get_certificate_url(
            self.context.get('request'), self._get_user(obj), self._get_course_id(obj)
        )

    def get_progress(self, obj: Any) -> Any:
        """Return the certificate URL."""
        progress_info = get_course_blocks_completion_summary(
            self._get_course_id(obj), self._get_user(obj)
        )
        total = progress_info['complete_count'] + progress_info['incomplete_count'] + progress_info['locked_count']
        return round(progress_info['complete_count'] / total, 4) if total else 0.0

    def get_exam_scores(self, obj: Any) -> Dict[str, Tuple[float, float] | None]:
        """Return exam scores."""
        result: Dict[str, Tuple[float, float] | None] = {__index: None for __index in self.grading_info}
        grades = PersistentSubsectionGrade.objects.filter(
            user_id=self._get_user(obj).id,
            course_id=self._get_course_id(obj),
            usage_key__in=self.subsection_locations.keys(),
            first_attempted__isnull=False,
        ).values('usage_key', 'earned_all', 'possible_all')

        for grade in grades:
            result[self.subsection_locations[str(grade['usage_key'])]] = (grade['earned_all'], grade['possible_all'])

        return result

    def to_representation(self, instance: Any) -> Any:
        """Return the representation of the instance."""
        def _extract_exam_scores(representation_item: dict[str, Any]) -> None:
            exam_scores = representation_item.pop('exam_scores', {})
            for index, score in exam_scores.items():
                earned_key = f'earned - {self.grading_info[index]["header_name"]}'
                possible_key = f'possible - {self.grading_info[index]["header_name"]}'
                representation_item[earned_key] = score[0] if score else 'no attempt'
                representation_item[possible_key] = score[1] if score else 'no attempt'

        representation = super().to_representation(instance)

        _extract_exam_scores(representation)

        return representation


class LearnerDetailsSerializer(LearnerBasicDetailsSerializer):
    """Serializer for learner details."""
    enrolled_courses_count = serializers.SerializerMethodField(help_text='Number of courses the user is enrolled in')
    certificates_count = serializers.SerializerMethodField(help_text='Number of certificates the user has earned')

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


class LearnerDetailsForCourseSerializer(
    LearnerBasicDetailsSerializer, CourseScoreAndCertificateSerializer
):  # pylint: disable=too-many-ancestors
    """Serializer for learner details for a course."""

    class Meta:
        model = get_user_model()
        fields = LearnerBasicDetailsSerializer.Meta.fields + CourseScoreAndCertificateSerializer.Meta.fields

    def _get_course_id(self, obj: Any = None) -> CourseLocator:
        """Get the course ID. Its helper method required for CourseScoreAndCertificateSerializer"""
        return CourseLocator.from_string(self.context.get('course_id'))

    def _get_user(self, obj: Any = None) -> get_user_model:
        """Get the User. Its helper method required for CourseScoreAndCertificateSerializer"""
        return obj


class LearnerEnrollmentSerializer(
    LearnerBasicDetailsSerializer, CourseScoreAndCertificateSerializer
):  # pylint: disable=too-many-ancestors
    """Serializer for learner enrollments"""
    course_id = serializers.SerializerMethodField()
    sso_external_id = SerializerOptionalMethodField(field_tags=['sso_external_id', 'csv_export'])

    class Meta:
        model = CourseEnrollment
        fields = (
            LearnerBasicDetailsSerializer.Meta.fields +
            CourseScoreAndCertificateSerializer.Meta.fields +
            ['course_id', 'sso_external_id']
        )

    def _get_course_id(self, obj: Any = None) -> CourseLocator | None:
        """Get the course ID. Its helper method required for CourseScoreAndCertificateSerializer"""
        return obj.course_id if obj else None

    def _get_user(self, obj: Any = None) -> get_user_model | None:
        """
        Get the User. Its helper method required for CourseScoreAndCertificateSerializer. It also
        plays important role for LearnerBasicDetailsSerializer
        """
        return obj.user if obj else None

    def get_course_id(self, obj: Any) -> str:
        """Get course id"""
        return str(self._get_course_id(obj))

    @staticmethod
    def get_sso_site_info(obj: Any) -> List[Dict[str, Any]]:
        """Get SSO information of the tenant's site related to the course"""
        course_tenants = get_org_to_tenant_map().get(obj.course_id.org.lower(), [])
        for tenant_id in course_tenants:
            sso_site_info = get_sso_sites().get(get_all_tenants_info()['sites'][tenant_id])
            if sso_site_info:
                return sso_site_info

        return []

    def get_sso_external_id(self, obj: Any) -> str:
        """Get the SSO external ID from social auth extra_data."""
        result = ''

        sso_site_info = self.get_sso_site_info(obj)
        if not sso_site_info:
            return result

        social_auth_records = UserSocialAuth.objects.filter(user=obj.user, provider='tpa-saml')
        user_auth_by_slug = {}
        for record in social_auth_records:
            if record.uid.count(':') == 1:
                sso_slug, _ = record.uid.split(':')
                user_auth_by_slug[sso_slug] = record

        if not user_auth_by_slug:
            return result

        for entity_id, sso_info in settings.FX_SSO_INFO.items():
            if not sso_info.get('external_id_field') or not sso_info.get('external_id_extractor'):
                logger.warning(
                    'Bad (external_id_field) or (external_id_extractor) settings for Entity ID (%s)', entity_id,
                )
                continue

            for sso_links in sso_site_info:
                if entity_id == sso_links['entity_id']:
                    user_auth_record = user_auth_by_slug.get(sso_links['slug'])
                    if not user_auth_record:
                        continue

                    external_id_value = user_auth_record.extra_data.get(sso_info['external_id_field'])
                    if external_id_value:
                        try:
                            external_id_extractor = import_from_path(sso_info['external_id_extractor'])
                        except Exception as exc:
                            raise FXCodedException(
                                code=FXExceptionCodes.BAD_CONFIGURATION_EXTERNAL_ID_EXTRACTOR,
                                message=f'Bad configuration: FX_SSO_INFO.{entity_id}.external_id_extractor. {str(exc)}'
                            ) from exc

                        try:
                            result = str(external_id_extractor(external_id_value) or '')
                        except Exception as exc:
                            logger.warning(
                                'SSO External ID extraction raised and error for user %s: %s', obj.user.username, exc,
                            )
                    break

        return result


class LearnerDetailsExtendedSerializer(LearnerDetailsSerializer):  # pylint: disable=too-many-ancestors
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
        if not self._default_org:
            raise serializers.ValidationError('Default organization is not set. Call validate_tenant_id first.')

        course_id = f'course-v1:{self.default_org}+{self.validated_data["number"]}+{self.validated_data["run"]}'
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
            'include_hidden_roles': query_params.get('include_hidden_roles', '0') == '1',
        }

        if query_params.get('active_users_filter') is not None:
            result['active_filter'] = query_params['active_users_filter'] == '1'
        else:
            result['active_filter'] = None

        excluded_role_types = query_params.get('excluded_role_types', '').split(',') \
            if query_params.get('excluded_role_types') else []

        result['excluded_role_types'] = []
        if 'global' in excluded_role_types:
            result['excluded_role_types'].append(RoleType.GLOBAL)

        if 'tenant' in excluded_role_types:
            result['excluded_role_types'].append(RoleType.ORG_WIDE)

        if 'course' in excluded_role_types:
            result['excluded_role_types'].append(RoleType.COURSE_SPECIFIC)

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
            excluded_role_types=self.query_params['excluded_role_types'],
            excluded_hidden_roles=not self.query_params['include_hidden_roles'],
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
            'national_id',
            'full_name',
            'alternative_full_name',
            'global_roles',
            'tenants',
        ]


class ReadOnlySerializer(serializers.Serializer):
    """A serializer that is only used for read operations and does not require create/update methods."""

    def create(self, validated_data: Any) -> Any:
        """Not implemented: Create a new object."""
        raise ValueError('This serializer is read-only and does not support object creation.')

    def update(self, instance: Any, validated_data: Any) -> Any:
        """Not implemented: Update an existing object."""
        raise ValueError('This serializer is read-only and does not support object updates.')


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


class AggregatedCountsQuerySettingsSerializer(ReadOnlySerializer):
    """Serializer for aggregated counts settings."""
    aggregate_period = serializers.CharField()
    date_from = serializers.DateTimeField(format=DEFAULT_DATETIME_FORMAT)
    date_to = serializers.DateTimeField(format=DEFAULT_DATETIME_FORMAT)


class AggregatedCountsTotalsSerializer(ReadOnlySerializer):
    enrollments_count = serializers.IntegerField(required=False, allow_null=True)


class AggregatedCountsValuesSerializer(ReadOnlySerializer):
    label = serializers.CharField()
    value = serializers.IntegerField()


class AggregatedCountsAllTenantsSerializer(ReadOnlySerializer):
    enrollments_count = AggregatedCountsValuesSerializer(required=False, allow_null=True, many=True)
    totals = AggregatedCountsTotalsSerializer()


class AggregatedCountsOneTenantSerializer(AggregatedCountsAllTenantsSerializer):
    tenant_id = serializers.IntegerField()


class AggregatedCountsSerializer(ReadOnlySerializer):
    query_settings = AggregatedCountsQuerySettingsSerializer()
    all_tenants = AggregatedCountsAllTenantsSerializer()
    by_tenant = AggregatedCountsOneTenantSerializer(many=True)
    limited_access = serializers.BooleanField()


class FxPermissionInfoSerializerMixin:  # pylint: disable=too-few-public-methods
    """Mixin to add a property fx_permission_info that loads the fx_permission_info from the request context."""

    @property
    def fx_permission_info(self) -> dict[str, Any]:
        """
        Get the fx_permission_info from the request context.

        :return: The fx_permission_info dictionary.
        :rtype: dict[str, Any]
        """
        request = self.context.get('request')  # type: ignore[attr-defined]
        if not request:
            raise serializers.ValidationError('Unable to load fx_permission_info as request object is missing.')
        if not hasattr(request, 'fx_permission_info'):
            raise serializers.ValidationError('fx_permission_info is missing in the request context of the serializer!')

        return request.fx_permission_info


class FileUploadSerializer(FxPermissionInfoSerializerMixin, ReadOnlySerializer):
    """
    Serializer for handling the file upload request. It validates and serializes the input data.
    """
    file = serializers.FileField(help_text='File to be uploaded')
    slug = serializers.SlugField(help_text='File slug. Only alphanumeric characters, and underscores are allowed.')
    tenant_id = serializers.IntegerField(help_text='Tenant ID')

    def validate_tenant_id(self, value: int) -> int:
        """
        Custom validation for tenant_id to ensure that the tenant exists.
        """
        try:
            TenantConfig.objects.get(id=value)
        except TenantConfig.DoesNotExist as exc:
            raise serializers.ValidationError(f'Tenant with ID {value} does not exist.') from exc

        if value not in self.fx_permission_info['view_allowed_tenant_ids_full_access']:
            raise serializers.ValidationError(f'User does not have have required access for tenant ({value}).')

        return value


class TenantAssetSerializer(FxPermissionInfoSerializerMixin, serializers.ModelSerializer):
    """Serializer for Data Export Task"""
    file_url = serializers.SerializerMethodField()
    file = serializers.FileField(write_only=True)
    tenant_id = serializers.PrimaryKeyRelatedField(queryset=TenantConfig.objects.all(), source='tenant')

    class Meta:
        model = TenantAsset
        fields = ['id', 'tenant_id', 'slug', 'file', 'file_url', 'updated_by', 'updated_at']
        read_only_fields = ['id', 'updated_at', 'file_url', 'updated_by']

    def __init__(self, *args: Any, **kwargs: Any):
        """Override init to dynamically change fields. This change is only for swagger docs"""
        include_write_only = kwargs.pop('include_write_only', True)
        super().__init__(*args, **kwargs)
        if include_write_only is False:
            self.fields.pop('file')

    def get_unique_together_validators(self) -> list:
        """
        Overriding this method to bypass the unique_together constraint on 'tenant' and 'slug'.
        This prevents an error from being raised before reaching the create or update logic.
        """
        return []

    def validate_file(self, file: Any) -> Any:  # pylint: disable=no-self-use
        """
        Custom validation for file to ensure file extension.
        """
        file_extension = os.path.splitext(file.name)[1]
        if file_extension.lower() not in ALLOWED_FILE_EXTENSIONS:
            raise serializers.ValidationError(f'Invalid file type. Allowed types are {ALLOWED_FILE_EXTENSIONS}.')
        return file

    def validate_tenant_id(self, tenant: TenantConfig) -> int:
        """
        Custom validation for tenant to ensure that the tenant permissions.
        """
        if tenant.id not in self.fx_permission_info['view_allowed_tenant_ids_full_access']:
            template_tenant_id = get_all_tenants_info()['template_tenant']['tenant_id']
            if self.fx_permission_info['is_system_staff_user'] and template_tenant_id == tenant.id:
                return tenant
            raise serializers.ValidationError(
                f'User does not have have required access for tenant ({tenant.id}).'
            )

        return tenant

    def validate_slug(self, slug: str) -> str:
        """
        Custom validation for the slug to ensure it doesn't start with an underscore unless the user is a system staff.
        """
        if slug.startswith('_') and not self.fx_permission_info['is_system_staff_user']:
            raise serializers.ValidationError(
                'Slug cannot start with an underscore unless the user is a system staff.'
            )
        return slug

    def get_file_url(self, obj: TenantAsset) -> Any:  # pylint: disable=no-self-use
        """Return file url."""
        return obj.file.url

    def create(self, validated_data: dict) -> TenantAsset:
        """
        Override the create method to handle scenarios where a user tries to upload a new asset with the same slug
        for the same tenant. Instead of creating a new asset, the existing asset will be updated with the new file.
        """
        request = self.context.get('request')
        asset, _ = TenantAsset.objects.update_or_create(
            tenant=validated_data['tenant'], slug=validated_data['slug'],
            defaults={
                'file': validated_data['file'],
                'updated_by': request.user,
                'updated_at': now()
            }
        )
        return asset


class TenantConfigSerializer(ReadOnlySerializer):
    """Serializer for Tenant Configurations."""
    values = serializers.DictField(default=dict)
    not_permitted = serializers.ListField(child=serializers.CharField(), default=list)
    bad_keys = serializers.ListField(child=serializers.CharField(), default=list)
    revision_ids = serializers.SerializerMethodField()

    def get_revision_ids(self, obj: Any) -> Dict[str, str]:  # pylint: disable=no-self-use
        """Return the revision IDs as strings."""
        revision_ids = obj.get('revision_ids', {})
        return {key: str(value) for key, value in revision_ids.items()}
