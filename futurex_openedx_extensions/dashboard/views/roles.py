"""Roles views for the dashboard app"""
from __future__ import annotations

from typing import Any, Dict

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models.query import QuerySet
from django.http import JsonResponse
from edx_api_doc_tools import exclude_schema_for
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.exceptions import ParseError
from rest_framework.response import Response
from rest_framework.views import APIView

from futurex_openedx_extensions.dashboard import serializers
from futurex_openedx_extensions.dashboard.docs_utils import docs
from futurex_openedx_extensions.helpers.constants import (
    COURSE_ACCESS_ROLES_SUPPORTED_READ,
    FX_VIEW_DEFAULT_AUTH_CLASSES,
)
from futurex_openedx_extensions.helpers.converters import error_details_to_dictionary
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.pagination import DefaultPagination
from futurex_openedx_extensions.helpers.permissions import (
    FXHasTenantAllCoursesAccess,
    FXHasTenantCourseAccess,
)
from futurex_openedx_extensions.helpers.roles import (
    FXViewRoleInfoMixin,
    add_course_access_roles,
    delete_course_access_roles,
    get_course_access_roles_queryset,
    update_course_access_roles,
)
from futurex_openedx_extensions.helpers.users import get_user_by_key

default_auth_classes = FX_VIEW_DEFAULT_AUTH_CLASSES.copy()


@docs('UserRolesManagementView.create')
@docs('UserRolesManagementView.destroy')
@docs('UserRolesManagementView.list')
@docs('UserRolesManagementView.retrieve')
@docs('UserRolesManagementView.update')
@exclude_schema_for('partial_update')
class UserRolesManagementView(FXViewRoleInfoMixin, viewsets.ModelViewSet):  # pylint: disable=too-many-ancestors
    """View to get the user roles"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantAllCoursesAccess]
    fx_view_name = 'user_roles'
    fx_default_read_only_roles = ['org_course_creator_group']
    fx_default_read_write_roles = ['org_course_creator_group']
    fx_allowed_write_methods = ['POST', 'PUT', 'DELETE']
    fx_view_description = 'api/fx/roles/v1/user_roles/: user roles management APIs'

    lookup_field = 'username'
    lookup_value_regex = '[^/]+'
    serializer_class = serializers.UserRolesSerializer
    pagination_class = DefaultPagination

    @transaction.non_atomic_requests
    def dispatch(self, *args: Any, **kwargs: Any) -> Response:
        return super().dispatch(*args, **kwargs)

    def get_queryset(self) -> QuerySet:
        """Get the list of users"""
        dummy_serializers = serializers.UserRolesSerializer(context={'request': self.request})

        try:
            q_set = get_user_model().objects.filter(
                id__in=get_course_access_roles_queryset(
                    orgs_filter=dummy_serializers.orgs_filter,
                    remove_redundant=True,
                    users=None,
                    search_text=dummy_serializers.query_params['search_text'],
                    roles_filter=dummy_serializers.query_params['roles_filter'],
                    active_filter=dummy_serializers.query_params['active_filter'],
                    course_ids_filter=dummy_serializers.query_params['course_ids_filter'],
                    excluded_role_types=dummy_serializers.query_params['excluded_role_types'],
                    excluded_hidden_roles=not dummy_serializers.query_params['include_hidden_roles'],
                ).values('user_id').distinct().order_by()
            ).select_related('profile').order_by('id')
        except (ValueError, FXCodedException) as exc:
            raise ParseError(f'Invalid parameter: {exc}') from exc

        return q_set

    def create(self, request: Any, *args: Any, **kwargs: Any) -> Response | JsonResponse:
        """Create a new user role"""
        data = request.data
        try:
            if (
                not isinstance(data['tenant_ids'], list) or
                not all(isinstance(t_id, int) for t_id in data['tenant_ids'])
            ):
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT,
                    message='tenant_ids must be a list of integers',
                )

            if not isinstance(data['users'], list):
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT,
                    message='users must be a list',
                )

            if not isinstance(data['role'], str):
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT,
                    message='role must be a string',
                )

            if not isinstance(data['tenant_wide'], int):
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT,
                    message='tenant_wide must be an integer flag',
                )

            if not isinstance(data.get('course_ids', []), list):
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT,
                    message='course_ids must be a list',
                )

            result = add_course_access_roles(
                caller=self.fx_permission_info['user'],
                tenant_ids=data['tenant_ids'],
                user_keys=data['users'],
                role=data['role'],
                tenant_wide=data['tenant_wide'] != 0,
                course_ids=data.get('course_ids', []),
            )
        except KeyError as exc:
            return Response(
                error_details_to_dictionary(reason=f'Missing required parameter: {exc}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )
        except FXCodedException as exc:
            return Response(
                error_details_to_dictionary(reason=f'({exc.code}) {str(exc)}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        return JsonResponse(
            result,
            status=http_status.HTTP_201_CREATED,
        )

    @staticmethod
    def verify_username(username: str) -> Response | Dict[str, Any]:
        """Verify the username"""
        user_info = get_user_by_key(username)
        if not user_info['user']:
            return Response(
                error_details_to_dictionary(reason=f'({user_info["error_code"]}) {user_info["error_message"]}'),
                status=http_status.HTTP_404_NOT_FOUND
            )
        return user_info

    def update(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """Update a user role"""
        user_info = self.verify_username(kwargs['username'])
        if isinstance(user_info, Response):
            return user_info

        result = update_course_access_roles(
            caller=self.fx_permission_info['user'],
            user=user_info['user'],
            new_roles_details=request.data or {},
            dry_run=False,
        )

        if result['error_code']:
            return Response(
                error_details_to_dictionary(reason=f'({result["error_code"]}) {result["error_message"]}'),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        return Response(
            self.serializer_class(user_info['user'], context={'request': request}).data,
            status=http_status.HTTP_200_OK,
        )

    def destroy(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """Delete a user role"""
        if not request.query_params.get('tenant_ids'):
            return Response(
                error_details_to_dictionary(reason="Missing required parameter: 'tenant_ids'"),
                status=http_status.HTTP_400_BAD_REQUEST
            )

        user_info = self.verify_username(kwargs['username'])
        if isinstance(user_info, Response):
            return user_info

        try:
            delete_course_access_roles(
                caller=self.fx_permission_info['user'],
                tenant_ids=self.fx_permission_info['view_allowed_tenant_ids_any_access'],
                user=user_info['user'],
            )
        except FXCodedException as exc:
            return Response(
                error_details_to_dictionary(reason=str(exc)),
                status=http_status.HTTP_404_NOT_FOUND
            )

        return Response(status=http_status.HTTP_204_NO_CONTENT)


@docs('MyRolesView.get')
class MyRolesView(FXViewRoleInfoMixin, APIView):
    """View to get the user roles of the caller"""
    authentication_classes = default_auth_classes
    permission_classes = [FXHasTenantCourseAccess]
    fx_view_name = 'my_roles'
    fx_default_read_only_roles = COURSE_ACCESS_ROLES_SUPPORTED_READ.copy()
    fx_view_description = 'api/fx/roles/v1/my_roles/: user roles management APIs'

    serializer_class = serializers.UserRolesSerializer

    def get(self, request: Any, *args: Any, **kwargs: Any) -> JsonResponse:
        """Get the list of users"""
        data = serializers.UserRolesSerializer(self.fx_permission_info['user'], context={'request': request}).data
        data['is_system_staff'] = self.fx_permission_info['is_system_staff_user']
        return JsonResponse(data)
