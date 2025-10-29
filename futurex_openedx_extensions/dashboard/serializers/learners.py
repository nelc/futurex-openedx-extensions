"""Learner-related serializers for the dashboard API."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from common.djangoapps.student.models import CourseEnrollment
from django.conf import settings
from django.contrib.auth import get_user_model
from lms.djangoapps.courseware.courses import get_course_blocks_completion_summary
from lms.djangoapps.grades.context import grading_context_for_course
from lms.djangoapps.grades.models import PersistentSubsectionGrade
from opaque_keys.edx.locator import CourseLocator
from openedx.core.djangoapps.user_api.accounts.serializers import AccountLegacyProfileSerializer
from openedx.core.lib.courses import get_course_by_id
from rest_framework import serializers
from social_django.models import UserSocialAuth

from futurex_openedx_extensions.dashboard.custom_serializers import (
    ModelSerializerOptionalFields,
    SerializerOptionalMethodField,
)
from futurex_openedx_extensions.helpers.certificates import get_certificate_date, get_certificate_url
from futurex_openedx_extensions.helpers.converters import dt_to_str, relative_url_to_absolute_url
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.extractors import (
    extract_arabic_name_from_user,
    extract_full_name_from_user,
    import_from_path,
)
from futurex_openedx_extensions.helpers.tenants import (
    get_all_tenants_info,
    get_org_to_tenant_map,
    get_sso_sites,
)

logger = logging.getLogger(__name__)


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
    certificate_date = SerializerOptionalMethodField(field_tags=['certificate_date', 'csv_export'])

    class Meta:
        fields = [
            'certificate_available',
            'course_score',
            'active_in_course',
            'progress',
            'certificate_url',
            'certificate_date',
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

    def get_certificate_date(self, obj: Any) -> Any:
        """Return the certificate Date."""
        return dt_to_str(get_certificate_date(
            self._get_user(obj), self._get_course_id(obj)
        ))

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
