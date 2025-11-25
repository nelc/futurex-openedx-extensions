from __future__ import annotations

import logging
from typing import Any

from common.djangoapps.student.auth import add_users
from common.djangoapps.student.models import CourseEnrollment
from common.djangoapps.student.roles import CourseInstructorRole, CourseStaffRole
from eox_nelp.course_experience.models import FeedbackCourse
from eox_tenant.models import TenantConfig
from lms.djangoapps.courseware.courses import get_course_blocks_completion_summary
from lms.djangoapps.grades.api import CourseGradeFactory
from lms.djangoapps.grades.context import grading_context_for_course
from lms.djangoapps.grades.models import PersistentSubsectionGrade
from openedx.core.djangoapps.content.block_structure.api import get_block_structure_manager
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from openedx.core.djangoapps.discussions.models import DiscussionsConfiguration
from openedx.core.djangoapps.django_comment_common.models import assign_default_role
from openedx.core.djangoapps.django_comment_common.utils import seed_permissions_roles
from openedx.core.djangoapps.user_api.accounts.serializers import AccountLegacyProfileSerializer
from openedx.core.lib.courses import get_course_by_id
from rest_framework import serializers
from xmodule.course_block import CourseFields
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.django import modulestore
from xmodule.modulestore.exceptions import DuplicateCourseError

from futurex_openedx_extensions.dashboard.custom_serializers import (
    ListSerializerOptionalFields,
    OptionalFieldsSerializerMixin,
    SerializerOptionalMethodField,
)
from futurex_openedx_extensions.helpers.course_categories import CourseCategories
from futurex_openedx_extensions.helpers.extractors import (
    verify_course_ids,
)

logger = logging.getLogger(__name__)

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

class CategorySerializer(OptionalFieldsSerializerMixin, FxPermissionInfoSerializerMixin, serializers.Serializer):
    """Serializer for course category."""
    id = serializers.CharField(read_only=True)
    label = serializers.DictField(child=serializers.CharField())
    courses = SerializerOptionalMethodField(field_tags=['courses', 'courses_display_names'])
    courses_display_names = SerializerOptionalMethodField(field_tags=['courses', 'courses_display_names'])
    tenant_id = serializers.IntegerField(write_only=True)

    class Meta:
        list_serializer_class = ListSerializerOptionalFields

    def __init__(self, *args: Any, **kwargs: Any):
        """Initialize the serializer and validate context."""
        super().__init__(*args, **kwargs)

        request = self.context.get("request")
        if request and request.method == "GET":
            if 'categories' not in self.context:
                raise serializers.ValidationError('categories dictionary is missing from context')

    def get_courses(self, instance: dict) -> list:
        """Get courses for the category."""
        return self.context['categories'].get(instance['id'], {}).get('courses', [])

    def get_courses_display_names(self, instance: dict) -> dict[str, str]:
        """Get display names of courses for the category."""
        course_ids = self.context['categories'].get(instance['id'], {}).get('courses', [])
        disable_verify = self.context.get('disable_verify_course_ids', False)
        if not disable_verify:
            verify_course_ids(course_ids)

        courses = CourseOverview.objects.filter(id__in=course_ids).values('id', 'display_name')
        id_to_name = {str(course['id']): course['display_name'] for course in courses}
        if not disable_verify:
            non_existent_course_ids = set(course_ids) - set(id_to_name.keys())
            if non_existent_course_ids:
                raise serializers.ValidationError(
                    f'The following course IDs does not exist: {list(non_existent_course_ids)}.'
                )

        return id_to_name

    def to_representation(self, instance: Any) -> Any:
        """Extract the category data from the context and serialize it."""
        category_data = self.context["categories"].get(instance, {})

        data = {"id": instance}
        data.update(category_data)

        return super().to_representation(data)

    def validate_tenant_id(self, value: int) -> int:
        """Validate tenant_id."""
        if value not in self.fx_permission_info['view_allowed_tenant_ids_full_access']:
            raise serializers.ValidationError(f'User does not have required access for tenant ({value}).')
        return value

    def validate_label(self, value: dict) -> dict:
        """Validate label is a non-empty dict."""
        if not value or not isinstance(value, dict):
            raise serializers.ValidationError('Label must be a non-empty dictionary.')
        return value

    def create(self, validated_data: dict) -> dict:
        """Create a new category."""
        tenant_id = validated_data['tenant_id']
        label = validated_data['label']

        category_manager = CourseCategories(tenant_id, open_as_read_only=False)
        category_name = category_manager.add_category(label=label, courses=[])
        category_manager.save()

        return {
            'id': category_name,
            'tenant_id': tenant_id,
            'label': label,
        }

    def update(self, instance: dict, validated_data: dict) -> dict:
        """Update an existing category."""
        raise ValueError('This serializer does not support update. Use partial_update (PATCH) instead.')


class CategoryUpdateSerializer(FxPermissionInfoSerializerMixin, serializers.Serializer):
    """Serializer for updating course category."""
    label = serializers.DictField(child=serializers.CharField(), required=False)
    courses = serializers.ListField(child=serializers.CharField(), required=False)

    def validate_label(self, value: dict) -> dict:
        """Validate label is a non-empty dict."""
        if not value or not isinstance(value, dict):
            raise serializers.ValidationError('Label must be a non-empty dictionary.')
        return value

    def validate_courses(self, value: list) -> list:
        """Validate courses is a list."""
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise serializers.ValidationError('Courses must be a list of existing course IDs.')
        verify_course_ids(value)

        courses_qs = CourseOverview.objects.filter(id__in=value).values_list('id', flat=True)
        courses = [str(course_id) for course_id in courses_qs]
        invalid_courses = []
        for course_id in value:
            if course_id not in courses:
                invalid_courses.append(course_id)
        if invalid_courses:
            raise serializers.ValidationError(f'The following course IDs are invalid: {invalid_courses}.')
        return value


class CategoriesOrderSerializer(FxPermissionInfoSerializerMixin, serializers.Serializer):
    """Serializer for updating categories order."""
    tenant_id = serializers.IntegerField(required=True)
    categories = serializers.ListField(child=serializers.CharField(), required=True)

    def validate_tenant_id(self, value: int) -> int:
        """Validate tenant_id."""
        if value not in self.fx_permission_info['view_allowed_tenant_ids_full_access']:
            raise serializers.ValidationError(f'User does not have required access for tenant ({value}).')
        return value

    def validate_categories(self, value: list) -> list:
        """Validate categories is a non-empty list."""
        if not value or not isinstance(value, list):
            raise serializers.ValidationError('Categories must be a non-empty list.')
        return value


class CourseCategoriesSerializer(serializers.Serializer):
    """Serializer for assigning categories to a course."""
    categories = serializers.ListField(child=serializers.CharField(), required=True)

    def validate_categories(self, value: list) -> list:
        """Validate categories list."""
        if not isinstance(value, list):
            raise serializers.ValidationError('Categories must be a list.')
        return value

