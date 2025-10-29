"""Learners views for the dashboard app"""
from __future__ import annotations

from typing import Any

from django.db.models.query import QuerySet
from django.http import JsonResponse
from rest_framework import status as http_status
from rest_framework.response import Response
from rest_framework.views import APIView

from futurex_openedx_extensions.dashboard import serializers
from futurex_openedx_extensions.dashboard.details.courses import get_learner_courses_info_queryset
from futurex_openedx_extensions.dashboard.details.learners import (
    get_learner_info_queryset,
    get_learners_by_course_queryset,
    get_learners_enrollments_queryset,
    get_learners_queryset,
)
from futurex_openedx_extensions.dashboard.docs_utils import docs
from futurex_openedx_extensions.helpers.constants import FX_VIEW_DEFAULT_AUTH_CLASSES
from futurex_openedx_extensions.helpers.converters import error_details_to_dictionary
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.export_mixins import ExportCSVMixin
from futurex_openedx_extensions.helpers.pagination import DefaultPagination
from futurex_openedx_extensions.helpers.permissions import FXHasTenantCourseAccess
from futurex_openedx_extensions.helpers.roles import FXViewRoleInfoMixin
from rest_framework.generics import ListAPIView

default_auth_classes = FX_VIEW_DEFAULT_AUTH_CLASSES.copy()


@docs('LearnersView.get')
class LearnersView(ExportCSVMixin, FXViewRoleInfoMixin, ListAPIView):
    """View to get the list of learners"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    serializer_class = serializers.LearnerDetailsSerializer
    pagination_class = DefaultPagination
    fx_view_name = 'learners_list'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/learners/v1/learners/: Get the list of learners'

    def get_queryset(self) -> QuerySet:
        """Get the list of learners"""
        search_text = self.request.query_params.get('search_text')
        include_staff = self.request.query_params.get('include_staff', '0') == '1'
        min_enrollments_count = self.request.query_params.get('min_enrollments_count', -1)
        max_enrollments_count = self.request.query_params.get('max_enrollments_count', -1)

        try:
            min_enrollments_count = int(min_enrollments_count)
            max_enrollments_count = int(max_enrollments_count)
        except ValueError:
            pass  # let get_learners_queryset handle the invalid values

        return get_learners_queryset(
            fx_permission_info=self.fx_permission_info,
            search_text=search_text,
            include_staff=include_staff,
            enrollments_filter=(min_enrollments_count, max_enrollments_count),
        )


@docs('LearnerInfoView.get')
class LearnerInfoView(FXViewRoleInfoMixin, APIView):
    """View to get the information of a learner"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    fx_view_name = 'learner_detailed_info'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/learners/v1/learner/: Get the information of a learner'

    def get(self, request: Any, username: str, *args: Any, **kwargs: Any) -> JsonResponse | Response:
        """
        GET /api/fx/learners/v1/learner/<username>/
        """
        include_staff = request.query_params.get('include_staff', '0') == '1'

        try:
            user = get_learner_info_queryset(
                fx_permission_info=self.fx_permission_info,
                user_key=username,
                include_staff=include_staff,
            ).first()
        except FXCodedException as exc:
            return_status = http_status.HTTP_404_NOT_FOUND if exc.code in (
                FXExceptionCodes.USER_QUERY_NOT_PERMITTED.value, FXExceptionCodes.USER_NOT_FOUND.value,
            ) else http_status.HTTP_400_BAD_REQUEST

            return Response(
                error_details_to_dictionary(reason=str(exc)),
                status=return_status,
            )

        return JsonResponse(
            serializers.LearnerDetailsExtendedSerializer(user, context={'request': request}).data
        )


@docs('LearnerCoursesView.get')
class LearnerCoursesView(FXViewRoleInfoMixin, APIView):
    """View to get the list of courses for a learner"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    pagination_class = DefaultPagination
    fx_view_name = 'learner_courses'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/learners/v1/learner_courses/: Get the list of courses for a learner'

    def get(self, request: Any, username: str, *args: Any, **kwargs: Any) -> JsonResponse | Response:
        """
        GET /api/fx/learners/v1/learner_courses/<username>/
        """
        include_staff = request.query_params.get('include_staff', '0') == '1'

        try:
            courses = get_learner_courses_info_queryset(
                fx_permission_info=self.fx_permission_info,
                user_key=username,
                visible_filter=None,
                include_staff=include_staff,
            )
        except FXCodedException as exc:
            return_status = http_status.HTTP_404_NOT_FOUND if exc.code in (
                FXExceptionCodes.USER_QUERY_NOT_PERMITTED.value, FXExceptionCodes.USER_NOT_FOUND.value,
            ) else http_status.HTTP_400_BAD_REQUEST

            return Response(
                error_details_to_dictionary(reason=str(exc)),
                status=return_status,
            )

        return Response(serializers.LearnerCoursesDetailsSerializer(
            courses, context={'request': request}, many=True
        ).data)


@docs('LearnersDetailsForCourseView.get')
class LearnersDetailsForCourseView(ExportCSVMixin, FXViewRoleInfoMixin, ListAPIView):
    """View to get the list of learners for a course"""
    authentication_classes = default_auth_classes
    serializer_class = serializers.LearnerDetailsForCourseSerializer
    permission_classes = [FXHasTenantCourseAccess]
    pagination_class = DefaultPagination
    fx_view_name = 'learners_with_details_for_course'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/learners/v1/learners/<course-id>: Get the list of learners for a course'

    def get_related_id(self) -> None:
        """
        Related ID is course_id for this view.
        """
        return self.kwargs.get('course_id')

    def get_queryset(self, *args: Any, **kwargs: Any) -> QuerySet:
        """Get the list of learners for a course"""
        search_text = self.request.query_params.get('search_text')
        course_id = self.kwargs.get('course_id')
        include_staff = self.request.query_params.get('include_staff', '0') == '1'

        return get_learners_by_course_queryset(
            course_id=course_id,
            search_text=search_text,
            include_staff=include_staff,
        )

    def get_serializer_context(self) -> dict[str, Any]:
        """Get the serializer context"""
        context = super().get_serializer_context()
        context['course_id'] = self.kwargs.get('course_id')
        context['omit_subsection_name'] = self.request.query_params.get('omit_subsection_name', '0')
        return context


@docs('LearnersEnrollmentView.get')
class LearnersEnrollmentView(ExportCSVMixin, FXViewRoleInfoMixin, ListAPIView):
    """View to get the list of learners for a course"""
    authentication_classes = default_auth_classes
    serializer_class = serializers.LearnerEnrollmentSerializer
    permission_classes = [FXHasTenantCourseAccess]
    pagination_class = DefaultPagination
    fx_view_name = 'learners_enrollment_details'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/learners/v1/enrollments: Get the list of enrollments'
    is_single_course_requested = False

    def get_queryset(self, *args: Any, **kwargs: Any) -> QuerySet:
        """Get the list of learners for a course"""
        course_ids = self.request.query_params.get('course_ids', '')
        user_ids = self.request.query_params.get('user_ids', '')
        usernames = self.request.query_params.get('usernames', '')
        course_ids_list = [
            course.strip() for course in course_ids.split(',')
        ] if course_ids else None
        user_ids_list = [
            int(user.strip()) for user in user_ids.split(',') if user.strip().isdigit()
        ] if user_ids else None
        usernames_list = [
            username.strip() for username in usernames.split(',')
        ] if usernames else None

        if course_ids_list and len(course_ids_list) == 1:
            self.is_single_course_requested = True

        return get_learners_enrollments_queryset(
            fx_permission_info=self.request.fx_permission_info,
            user_ids=user_ids_list,
            course_ids=course_ids_list,
            usernames=usernames_list,
            learner_search=self.request.query_params.get('learner_search'),
            course_search=self.request.query_params.get('course_search'),
            include_staff=self.request.query_params.get('include_staff', '0') == '1',
        )

    def get_serializer_context(self) -> dict[str, Any]:
        """Get the serializer context"""
        context = super().get_serializer_context()
        if self.is_single_course_requested and self.get_queryset().exists():
            context['course_id'] = str(self.get_queryset().first().course_id)
            context['omit_subsection_name'] = self.request.query_params.get('omit_subsection_name', '0')
        return context
