"""Views for the dashboard app - learner theme (fx-learner) feature"""
from __future__ import annotations

from typing import Any

from opaque_keys.edx.keys import CourseKey
from rest_framework import status as http_status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from futurex_openedx_extensions.dashboard import serializers
from futurex_openedx_extensions.dashboard.docs_utils import docs
from futurex_openedx_extensions.helpers.constants import FX_VIEW_DEFAULT_AUTH_CLASSES
from futurex_openedx_extensions.helpers.converters import error_details_to_dictionary
from futurex_openedx_extensions.helpers.learner_theme import (
    get_catalog,
    get_learner_certificates,
    get_learner_programs,
    get_learner_theme_shell,
    get_request_tenant_id,
)
from futurex_openedx_extensions.helpers.models import CourseLearnerMeta
from futurex_openedx_extensions.helpers.permissions import FXHasTenantAllCoursesAccess
from futurex_openedx_extensions.helpers.querysets import get_course_search_queryset
from futurex_openedx_extensions.helpers.roles import FXViewRoleInfoMixin

default_auth_classes = FX_VIEW_DEFAULT_AUTH_CLASSES.copy()


def tenant_not_found_response() -> Response:
    """Return the 404 answer for a request whose site is not a tenant."""
    return Response(
        error_details_to_dictionary(reason='No tenant is served on this site.'),
        status=http_status.HTTP_404_NOT_FOUND,
    )


@docs('LearnerThemeShellView.get')
class LearnerThemeShellView(APIView):
    """Public header/footer shell of the learner pages of the request's tenant (published values only)"""
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:  # pylint: disable=no-self-use
        """GET /api/fx/theme/v1/shell/"""
        tenant_id = get_request_tenant_id(request)
        shell = get_learner_theme_shell(tenant_id) if tenant_id else {}
        if not shell:
            return tenant_not_found_response()
        return Response(shell)


@docs('LearnerThemeCatalogView.get')
class LearnerThemeCatalogView(APIView):
    """Public catalogue (programs + categories) of the request's tenant"""
    authentication_classes = default_auth_classes
    permission_classes = [AllowAny]

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:  # pylint: disable=no-self-use
        """GET /api/fx/catalog/v1/programs/"""
        if not get_request_tenant_id(request):
            return tenant_not_found_response()
        return Response(get_catalog(request))


@docs('LearnerThemeMyProgramsView.get')
class LearnerThemeMyProgramsView(APIView):
    """The request user's own programs in the request's tenant"""
    authentication_classes = default_auth_classes
    permission_classes = [IsAuthenticated]

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:  # pylint: disable=no-self-use
        """GET /api/fx/learner/v1/programs/"""
        if not get_request_tenant_id(request):
            return tenant_not_found_response()
        return Response(get_learner_programs(request))


@docs('LearnerThemeMyCertificatesView.get')
class LearnerThemeMyCertificatesView(APIView):
    """The request user's own certificates in the request's tenant"""
    authentication_classes = default_auth_classes
    permission_classes = [IsAuthenticated]

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:  # pylint: disable=no-self-use
        """GET /api/fx/learner/v1/certificates/"""
        if not get_request_tenant_id(request):
            return tenant_not_found_response()
        return Response(get_learner_certificates(request))


@docs('CourseLearnerMetaView.get')
@docs('CourseLearnerMetaView.put')
class CourseLearnerMetaView(FXViewRoleInfoMixin, APIView):
    """View to read and set the level and learning mode of a course"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'course_learner_meta'
    fx_default_read_only_roles = ['staff', 'org_course_creator_group']
    fx_default_read_write_roles = ['staff', 'org_course_creator_group']
    fx_allowed_write_methods = ['PUT']
    fx_view_description = 'api/fx/courses/v1/meta/<course_id>/: Level and learning mode of a course'

    def _accessible_course_key(self, course_id: str) -> CourseKey | None:
        """Return the course key when the course exists in the caller's tenants, else None."""
        course = get_course_search_queryset(
            fx_permission_info=self.fx_permission_info,
            course_ids=[course_id],
        ).first()
        return course.id if course else None

    @staticmethod
    def _not_found(course_id: str) -> Response:
        """404 answer for a course outside the caller's tenants"""
        return Response(
            error_details_to_dictionary(reason=f'Course not found or access denied: {course_id}'),
            status=http_status.HTTP_404_NOT_FOUND,
        )

    def get(self, request: Any, course_id: str, *args: Any, **kwargs: Any) -> Response:
        """GET /api/fx/courses/v1/meta/<course_id>/"""
        course_key = self._accessible_course_key(course_id)
        if not course_key:
            return self._not_found(course_id)
        return Response(CourseLearnerMeta.get_meta(course_key))

    def put(self, request: Any, course_id: str, *args: Any, **kwargs: Any) -> Response:
        """PUT /api/fx/courses/v1/meta/<course_id>/"""
        serializer = serializers.CourseLearnerMetaSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=http_status.HTTP_400_BAD_REQUEST)

        course_key = self._accessible_course_key(course_id)
        if not course_key:
            return self._not_found(course_id)

        CourseLearnerMeta.set_meta(
            course_key,
            level=serializer.validated_data['level'],
            learning_mode=serializer.validated_data['learning_mode'],
            user=request.user,
        )
        return Response(CourseLearnerMeta.get_meta(course_key))
