"""Courses views for the dashboard app"""
from __future__ import annotations

from typing import Any

from django.db.models.query import QuerySet
from django.http import JsonResponse
from rest_framework import status as http_status
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from futurex_openedx_extensions.dashboard import serializers
from futurex_openedx_extensions.dashboard.details.courses import (
    get_courses_feedback_queryset,
    get_courses_queryset,
)
from futurex_openedx_extensions.dashboard.docs_utils import docs
from futurex_openedx_extensions.dashboard.statistics.courses import (
    get_courses_count_by_status,
    get_courses_ratings,
)
from futurex_openedx_extensions.helpers.constants import (
    COURSE_STATUS_SELF_PREFIX,
    COURSE_STATUSES,
    FX_VIEW_DEFAULT_AUTH_CLASSES,
)
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.export_mixins import ExportCSVMixin
from futurex_openedx_extensions.helpers.filters import DefaultOrderingFilter
from futurex_openedx_extensions.helpers.library import get_accessible_libraries
from futurex_openedx_extensions.helpers.pagination import DefaultPagination
from futurex_openedx_extensions.helpers.permissions import FXHasTenantCourseAccess
from futurex_openedx_extensions.helpers.roles import FXViewRoleInfoMixin

default_auth_classes = FX_VIEW_DEFAULT_AUTH_CLASSES.copy()


@docs('CoursesView.get')
@docs('CoursesView.post')
class CoursesView(ExportCSVMixin, FXViewRoleInfoMixin, ListAPIView):
    """View to get the list of courses"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    serializer_class = serializers.CourseDetailsSerializer
    pagination_class = DefaultPagination
    filter_backends = [DefaultOrderingFilter]
    ordering_fields = [
        'id', 'self_paced', 'enrolled_count', 'active_count',
        'certificates_count', 'display_name', 'org', 'completion_rate',
    ]
    ordering = ['display_name']
    fx_view_name = 'courses_list'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/courses/v1/courses/: Get the list of courses'

    def get_queryset(self) -> QuerySet:
        """Get the list of learners"""
        search_text = self.request.query_params.get('search_text')
        include_staff = self.request.query_params.get('include_staff')

        return get_courses_queryset(
            fx_permission_info=self.fx_permission_info,
            search_text=search_text,
            visible_filter=None,
            include_staff=include_staff,
        )

    def post(self, request: Any) -> Response | JsonResponse:  # pylint: disable=no-self-use
        """POST /api/fx/courses/v1/courses/"""
        serializer = serializers.CourseCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            created_course = serializer.save()
            return JsonResponse({
                'id': str(created_course.id),
                'url': serializer.get_absolute_url(),
            })

        return Response(
            {'errors': serializer.errors},
            status=http_status.HTTP_400_BAD_REQUEST
        )


@docs('LibraryView.get')
@docs('LibraryView.post')
class LibraryView(ExportCSVMixin, FXViewRoleInfoMixin, APIView):
    """View to get the list of libraries"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    pagination_class = DefaultPagination
    fx_view_name = 'libraries_list'
    fx_default_read_only_roles = ['staff', 'instructor', 'library_user', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/libraries/v1/libraries/: Get the list of libraries'

    def get(self, request: Any) -> Response:
        """
        GET /api/fx/libraries/v1/libraries/?tenant_ids=<tenantIds>

        <tenantIds> (optional): a comma-separated list of the tenant IDs to get the information for. If not provided,
            the API will assume the list of all accessible tenants by the user
        """
        libraries = get_accessible_libraries(self.fx_permission_info, self.request.query_params.get('search_text'))
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(libraries, request)
        serializer = serializers.LibrarySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request: Any) -> Response:  # pylint: disable=no-self-use
        """
        POST /api/fx/libraries/v1/libraries/
        """
        serializer = serializers.LibrarySerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            created_library = serializer.save()
            return JsonResponse(
                {'library': str(created_library.location.library_key)},
                status=http_status.HTTP_201_CREATED,
            )
        return Response(
            {'errors': serializer.errors},
            status=http_status.HTTP_400_BAD_REQUEST
        )


@docs('CourseStatusesView.get')
class CourseStatusesView(FXViewRoleInfoMixin, APIView):
    """View to get the course statuses"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    fx_view_name = 'course_statuses'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/statistics/v1/course_statuses/: Get the course statuses'

    @staticmethod
    def to_json(result: QuerySet) -> dict[str, int]:
        """Convert the result to JSON format"""
        dict_result = {
            f'{COURSE_STATUS_SELF_PREFIX if self_paced else ""}{status}': 0
            for status in COURSE_STATUSES
            for self_paced in [False, True]
        }

        for item in result:
            status = f'{COURSE_STATUS_SELF_PREFIX if item["self_paced"] else ""}{item["status"]}'
            dict_result[status] = item['courses_count']
        return dict_result

    def get(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:
        """
        GET /api/fx/statistics/v1/course_statuses/?tenant_ids=<tenantIds>

        <tenantIds> (optional): a comma-separated list of the tenant IDs to get the information for. If not provided,
            the API will assume the list of all accessible tenants by the user
        """
        result = get_courses_count_by_status(fx_permission_info=self.fx_permission_info)

        return JsonResponse(self.to_json(result))


@docs('CoursesFeedbackView.get')
class CoursesFeedbackView(ExportCSVMixin, FXViewRoleInfoMixin, ListAPIView):
    """View to get the list of courses feedbacks"""
    authentication_classes = default_auth_classes
    serializer_class = serializers.CoursesFeedbackSerializer
    permission_classes = [FXHasTenantCourseAccess]
    pagination_class = DefaultPagination
    fx_view_name = 'courses_feedback'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/courses/v1/feedback: Get the list of feedbacks'

    def validate_rating_list(self, param_key: str) -> list[int] | None:
        """
        Validates that the input string from query parameters is a comma-separated list
        of integers between 1 and 5. Returns the parsed list if valid.

        :param param_key: The key in query params to validate (e.g. 'rating_content')
        :return: List of integers if valid, or None if not provided
        :raises: FXCodedException if validation fails
        """
        value = self.request.query_params.get(param_key)
        if not value:
            return None

        try:
            ratings = [int(r.strip()) for r in value.split(',')]
        except ValueError as exc:
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message=f"'{param_key}' must be a comma-separated list of valid integers."
            ) from exc

        if any(r < 0 or r > 5 for r in ratings):
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message=f"Each value in '{param_key}' must be between 0 and 5 (inclusive)."
            )

        return ratings

    def get_queryset(self, *args: Any, **kwargs: Any) -> QuerySet:
        """Get the list of course feedbacks"""
        course_ids = self.request.query_params.get('course_ids', '')
        course_ids_list = [
            course.strip() for course in course_ids.split(',')
        ] if course_ids else None

        return get_courses_feedback_queryset(
            fx_permission_info=self.request.fx_permission_info,
            course_ids=course_ids_list,
            public_only=self.request.query_params.get('public_only', '0') == '1',
            recommended_only=self.request.query_params.get('recommended_only', '0') == '1',
            feedback_search=self.request.query_params.get('feedback_search'),
            rating_content_filter=self.validate_rating_list('rating_content'),
            rating_instructors_filter=self.validate_rating_list('rating_instructors')
        )


@docs('GlobalRatingView.get')
class GlobalRatingView(FXViewRoleInfoMixin, APIView):
    """View to get the global rating"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    fx_view_name = 'global_rating'
    fx_default_read_only_roles = ['staff', 'instructor', 'data_researcher', 'org_course_creator_group']
    fx_view_description = 'api/fx/statistics/v1/rating/: Get the global rating for courses'

    def get(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:
        """
        GET /api/fx/statistics/v1/rating/?tenant_ids=<tenantIds>

        <tenantIds> (optional): a comma-separated list of the tenant IDs to get the information for. If not provided,
            the API will assume the list of all accessible tenants by the user
        """
        data_result = get_courses_ratings(fx_permission_info=self.fx_permission_info)
        result = {
            'total_rating': data_result['total_rating'],
            'total_count': sum(data_result[f'rating_{index}_count'] for index in range(1, 6)),
            'courses_count': data_result['courses_count'],
            'rating_counts': {
                str(index): data_result[f'rating_{index}_count'] for index in range(1, 6)
            },
        }

        return JsonResponse(result)
