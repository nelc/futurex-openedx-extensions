from __future__ import annotations

from typing import Any

from common.djangoapps.student.models import get_user_by_username_or_email
from rest_framework import status as http_status
from rest_framework.response import Response
from rest_framework.views import APIView

from futurex_openedx_extensions.dashboard import s2025 as serializers
from futurex_openedx_extensions.dashboard.docs_utils import docs
from futurex_openedx_extensions.helpers.constants import (
    FX_VIEW_DEFAULT_AUTH_CLASSES,
)
from futurex_openedx_extensions.helpers.converters import error_details_to_dictionary
from futurex_openedx_extensions.helpers.course_categories import CourseCategories
from futurex_openedx_extensions.helpers.exceptions import FXCodedException
from futurex_openedx_extensions.helpers.permissions import (
    FXHasTenantAllCoursesAccess,
)
from futurex_openedx_extensions.helpers.querysets import get_course_search_queryset
from futurex_openedx_extensions.helpers.roles import (
    FXViewRoleInfoMixin,
)
from futurex_openedx_extensions.helpers.tenants import (
    get_tenants_by_org,
)

default_auth_classes = FX_VIEW_DEFAULT_AUTH_CLASSES.copy()


@docs('CategoriesView.get')
@docs('CategoriesView.post')
class CategoriesView(FXViewRoleInfoMixin, APIView):
    """View to manage course categories"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'categories_management'
    fx_default_read_only_roles = ['staff', 'org_course_creator_group']
    fx_default_read_write_roles = ['staff', 'org_course_creator_group']
    fx_allowed_write_methods = ['POST']
    fx_view_description = 'api/fx/courses/v1/categories/: Manage course categories'

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """GET /api/fx/courses/v1/categories/"""
        tenant_id = self.verify_one_tenant_id_provided(request)

        category_manager = CourseCategories(tenant_id)

        serialized = serializers.CategorySerializer(
            instance=category_manager.sorting,
            many=True,
            context={
                'request': request, 'categories': category_manager.categories,
            }
        )
        return Response(serialized.data)

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """POST /api/fx/courses/v1/categories/"""
        serializer = serializers.CategorySerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=http_status.HTTP_400_BAD_REQUEST)

        try:
            category = serializer.save()
            return Response(category, status=http_status.HTTP_201_CREATED)
        except FXCodedException as exc:
            return Response(
                error_details_to_dictionary(reason=f'({exc.code}) {str(exc)}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )


@docs('CategoryDetailView.get')
@docs('CategoryDetailView.patch')
@docs('CategoryDetailView.delete')
class CategoryDetailView(FXViewRoleInfoMixin, APIView):
    """View to manage individual category"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'category_detail'
    fx_default_read_write_roles = ['staff', 'org_course_creator_group']
    fx_allowed_write_methods = ['PATCH', 'DELETE']
    fx_view_description = 'api/fx/courses/v1/categories/<category_id>/: Manage individual category'

    def get(self, request: Any, category_id: str, *args: Any, **kwargs: Any) -> Response:
        """GET /api/fx/courses/v1/categories/<category_id>/"""
        tenant_id = self.verify_one_tenant_id_provided(request)

        try:
            category_manager = CourseCategories(tenant_id)
            category_manager.verify_category_name_exists(category_id)

            serialized = serializers.CategorySerializer(
                instance=category_id,
                context={
                    'request': request,
                    'categories': category_manager.categories,
                },
            )
            return Response(serialized.data)

        except FXCodedException as exc:
            return Response(
                error_details_to_dictionary(reason=f'({exc.code}) {str(exc)}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )

    def patch(self, request: Any, category_id: str, *args: Any, **kwargs: Any) -> Response:
        """PATCH /api/fx/courses/v1/categories/<category_id>/"""
        tenant_id = self.verify_one_tenant_id_provided(request)

        serializer = serializers.CategoryUpdateSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=http_status.HTTP_400_BAD_REQUEST)

        try:
            category_manager = CourseCategories(tenant_id, open_as_read_only=False)
            category_manager.verify_category_name_exists(category_id)

            if 'label' in serializer.validated_data:
                category_manager.categories[category_id]['label'] = serializer.validated_data['label']

            if 'courses' in serializer.validated_data:
                category_manager.set_courses_for_category(
                    category_name=category_id, courses=serializer.validated_data['courses'],
                )

            category_manager.save()
            return Response(status=http_status.HTTP_204_NO_CONTENT)

        except FXCodedException as exc:
            return Response(
                error_details_to_dictionary(reason=f'({exc.code}) {str(exc)}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )

    def delete(self, request: Any, category_id: str, *args: Any, **kwargs: Any) -> Response:
        """DELETE /api/fx/courses/v1/categories/<category_id>/"""
        tenant_id = self.verify_one_tenant_id_provided(request)

        try:
            category_manager = CourseCategories(tenant_id, open_as_read_only=False)
            category_manager.remove_category(category_id)
            category_manager.save()
            return Response(status=http_status.HTTP_204_NO_CONTENT)

        except FXCodedException as exc:
            return Response(
                error_details_to_dictionary(reason=f'({exc.code}) {str(exc)}'),
                status=http_status.HTTP_400_BAD_REQUEST,
            )


@docs('CategoriesOrderView.post')
class CategoriesOrderView(FXViewRoleInfoMixin, APIView):
    """View to update categories order"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'categories_order'
    fx_default_read_write_roles = ['staff', 'org_course_creator_group']
    fx_allowed_write_methods = ['POST']
    fx_view_description = 'api/fx/courses/v1/categories_order/: Update categories order'

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """POST /api/fx/courses/v1/categories_order/"""
        serializer = serializers.CategoriesOrderSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=http_status.HTTP_400_BAD_REQUEST)

        try:
            tenant_id = serializer.validated_data['tenant_id']
            categories = serializer.validated_data['categories']

            category_manager = CourseCategories(tenant_id, open_as_read_only=False)
            category_manager.set_categories_sorting(categories)
            category_manager.save()

            return Response(status=http_status.HTTP_204_NO_CONTENT)

        except FXCodedException as exc:
            return Response(
                error_details_to_dictionary(reason=f'({exc.code}) {str(exc)}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )


@docs('CourseCategoriesView.put')
class CourseCategoriesView(FXViewRoleInfoMixin, APIView):
    """View to assign categories to a course"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'course_categories'
    fx_default_read_write_roles = ['staff', 'org_course_creator_group']
    fx_allowed_write_methods = ['PUT']
    fx_view_description = 'api/fx/courses/v1/course_categories/<course_id>/: Assign categories to a course'

    def put(self, request: Any, course_id: str, *args: Any, **kwargs: Any) -> Response:
        """PUT /api/fx/courses/v1/course_categories/<course_id>/"""
        serializer = serializers.CourseCategoriesSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=http_status.HTTP_400_BAD_REQUEST)

        accessible_course = get_course_search_queryset(
            fx_permission_info=self.fx_permission_info,
            course_ids=[course_id],
        ).first()

        if not accessible_course:
            return Response(
                error_details_to_dictionary(reason=f'Course not found or access denied: {course_id}'),
                status=http_status.HTTP_404_NOT_FOUND
            )

        tenant_ids = get_tenants_by_org(accessible_course.org)
        if len(tenant_ids) > 1:
            return Response(
                error_details_to_dictionary(
                    reason=f'Multiple tenants found for course: {course_id}, unable to proceed.'
                ),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        try:
            category_manager = CourseCategories(tenant_ids[0], open_as_read_only=False)
            category_manager.set_categories_for_course(course_id, serializer.validated_data['categories'])
            category_manager.save()

        except FXCodedException as exc:
            return Response(
                error_details_to_dictionary(reason=f'({exc.code}) {str(exc)}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        return Response(status=http_status.HTTP_204_NO_CONTENT)
