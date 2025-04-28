"""Permission classes for FutureX Open edX Extensions."""
from __future__ import annotations

import json
from typing import Any, List

from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.permissions import BasePermission, IsAuthenticated

from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.roles import (
    check_tenant_access,
    get_accessible_tenant_ids,
    get_user_course_access_roles,
)
from futurex_openedx_extensions.helpers.tenants import get_course_org_filter_list, get_org_to_tenant_map
from futurex_openedx_extensions.helpers.users import is_system_staff_user


def get_tenant_limited_fx_permission_info(fx_permission_info: dict, tenant_id: int) -> dict:
    """
    Get a copy of the permission info limited to a single tenant.

    :param fx_permission_info: Permission information
    :type fx_permission_info: dict
    :param tenant_id: Tenant ID
    :type tenant_id: int
    :return: Permission information limited to the tenant
    :rtype: dict
    """
    filtered_orgs = set(get_course_org_filter_list([tenant_id])['course_org_filter_list'])

    view_allowed_full_access_orgs = filtered_orgs & set(fx_permission_info['view_allowed_full_access_orgs'])
    view_allowed_course_access_orgs = filtered_orgs & set(fx_permission_info['view_allowed_course_access_orgs'])

    fx_permission_info_one_tenant = {
        'user': fx_permission_info['user'],
        'user_roles': fx_permission_info['user_roles'],
        'is_system_staff_user': fx_permission_info['is_system_staff_user'],
        'view_allowed_roles': fx_permission_info['view_allowed_roles'],
        'view_allowed_full_access_orgs': list(view_allowed_full_access_orgs),
        'view_allowed_course_access_orgs': list(view_allowed_course_access_orgs),
        'view_allowed_any_access_orgs': list(view_allowed_full_access_orgs | view_allowed_course_access_orgs),
        'view_allowed_tenant_ids_any_access': [tenant_id],
        'view_allowed_tenant_ids_full_access': [tenant_id] if view_allowed_full_access_orgs else [],
        'view_allowed_tenant_ids_partial_access': [] if view_allowed_full_access_orgs else [tenant_id],
    }

    return fx_permission_info_one_tenant


class FXBaseAuthenticatedPermission(IsAuthenticated):
    """Base permission class for FutureX Open edX Extensions."""

    def verify_access_roles(self, request: Any, view: Any) -> bool:
        """Verify access roles."""
        raise NotImplementedError(f'(verify_access_roles) is not implemented ({self.__class__.__name__})')

    @staticmethod
    def _set_view_allowed_info(
        request: Any, tenant_ids: List[int], user_roles: dict, view_allowed_roles: List[str],
    ) -> None:
        """Helper method to set view allowed info."""
        permitted_orgs: set = set(get_course_org_filter_list(tenant_ids)['course_org_filter_list'])
        full_access_orgs: set = set()
        course_access_orgs: set = set()
        for role in view_allowed_roles:
            if role in user_roles:
                full_access_orgs.update(
                    permitted_orgs & set(user_roles[role]['orgs_full_access'])
                )
                course_access_orgs.update(
                    permitted_orgs & set(user_roles[role]['orgs_of_courses'])
                )
        course_access_orgs -= full_access_orgs

        full_access_tenant_ids = set()
        for org in full_access_orgs:
            full_access_tenant_ids.update(get_org_to_tenant_map()[org])

        request.fx_permission_info.update({
            'view_allowed_full_access_orgs': list(full_access_orgs),
            'view_allowed_course_access_orgs': list(course_access_orgs),
            'view_allowed_any_access_orgs': list(full_access_orgs | course_access_orgs),
            'view_allowed_tenant_ids_full_access': list(full_access_tenant_ids),
            'view_allowed_tenant_ids_partial_access': list(set(tenant_ids) - full_access_tenant_ids),
        })

    def has_permission(self, request: Any, view: Any) -> bool:
        """Check if the user is authenticated."""
        if not hasattr(view, 'get_allowed_roles_all_views'):
            raise TypeError(
                f'View ({view.__class__.__name__}) does not have (get_allowed_roles_all_views) method! '
                'Fix this by adding (FXViewRoleInfoMixin) to the view class definition, or avoid using '
                f'permission class ({self.__class__.__name__})'
            )

        if not super().has_permission(request, view) or not request.user.is_active:
            raise NotAuthenticated()

        view_allowed_roles: List[str] = view.get_view_user_roles_mapping(
            view_name=view.fx_view_name, user=request.user,
        )
        tenant_ids_string: str | None = request.GET.get('tenant_ids')

        if tenant_ids_string:
            has_access, details = check_tenant_access(
                user=request.user,
                tenant_ids_string=tenant_ids_string,
                roles_filter=view_allowed_roles,
            )
            if not has_access:
                raise PermissionDenied(detail=json.dumps(details))
            tenant_ids = details['tenant_ids']
        else:
            tenant_ids = get_accessible_tenant_ids(user=request.user, roles_filter=view_allowed_roles)

        if view.fx_tenant_id_url_arg_name:
            if not view.kwargs.get(view.fx_tenant_id_url_arg_name):
                raise FXCodedException(
                    code=FXExceptionCodes.TENANT_ID_REQUIRED_AS_URL_ARG,
                    message=f'Tenant id ({view.fx_tenant_id_url_arg_name}) is required as a URL argument'
                            ', but not found!',
                )

            try:
                _tenant_id = int(view.kwargs[view.fx_tenant_id_url_arg_name])
            except ValueError as exc:
                raise FXCodedException(
                    code=FXExceptionCodes.TENANT_NOT_FOUND,
                    message=f'Invalid tenant ID ({view.kwargs[view.fx_tenant_id_url_arg_name]}), expected int!',
                ) from exc
            else:
                if _tenant_id not in tenant_ids:
                    raise PermissionDenied(detail=json.dumps({
                        'reason': f'User does not have access to the tenant ({_tenant_id})',
                    }))

        system_staff_user_flag = is_system_staff_user(request.user)
        user_roles: dict = get_user_course_access_roles(request.user.id)['roles']

        download_allowed = bool(
            set(user_roles.keys()) & set(view.get_view_user_roles_mapping(
                view_name='exported_files_data', user=request.user
            ))
        )

        request.fx_permission_info = {
            'user': request.user,
            'user_roles': user_roles,
            'is_system_staff_user': system_staff_user_flag,
            'view_allowed_roles': view_allowed_roles,
            'view_allowed_tenant_ids_any_access': tenant_ids,
            'download_allowed': download_allowed,
        }

        if system_staff_user_flag:
            request.fx_permission_info.update({
                'user_roles': {},
                'download_allowed': True,
            })

        if system_staff_user_flag or (
            set(user_roles.keys()) & set(cs.COURSE_ACCESS_ROLES_GLOBAL) & set(view_allowed_roles)
        ):
            request.fx_permission_info.update({
                'view_allowed_full_access_orgs': get_course_org_filter_list(tenant_ids)['course_org_filter_list'],
                'view_allowed_course_access_orgs': [],
                'view_allowed_tenant_ids_full_access': tenant_ids,
                'view_allowed_tenant_ids_partial_access': [],
            })
            request.fx_permission_info['view_allowed_any_access_orgs'] = \
                request.fx_permission_info['view_allowed_full_access_orgs']
            return True

        self._set_view_allowed_info(request, tenant_ids, user_roles, view_allowed_roles)

        return self.verify_access_roles(request, view)


class FXHasTenantAllCoursesAccess(FXBaseAuthenticatedPermission):
    """Permission class to check if the user has access to all courses in the tenants."""
    def verify_access_roles(self, request: Any, view: Any) -> bool:
        """Verify access roles."""
        if not request.fx_permission_info['view_allowed_full_access_orgs']:
            raise PermissionDenied(detail=json.dumps({'reason': 'User does not have full access to any organization'}))

        return True


class FXHasTenantCourseAccess(FXBaseAuthenticatedPermission):
    """Permission class to check if the user has access to one or more courses in the tenants."""
    def verify_access_roles(self, request: Any, view: Any) -> bool:
        """Verify access roles."""
        if not request.fx_permission_info['view_allowed_any_access_orgs']:
            raise PermissionDenied(detail=json.dumps({'reason': 'User does not have course access to the tenant'}))

        return True


class IsSystemStaff(IsAuthenticated):
    """Permission class to check if the user is a staff member."""
    def has_permission(self, request: Any, view: Any) -> bool:
        """Check if the user is a staff member"""
        if not super().has_permission(request, view):
            raise NotAuthenticated()

        if not is_system_staff_user(request.user):
            raise PermissionDenied(detail=json.dumps({'reason': 'User is not a system staff member'}))

        return True


class IsAnonymousOrSystemStaff(BasePermission):
    """Permission class to check if the user is anonymous or system staff."""
    def has_permission(self, request: Any, view: Any) -> bool:
        """Check if the user is anonymous"""
        if not hasattr(request, 'user') or not request.user or not request.user.is_authenticated:
            return True
        return is_system_staff_user(request.user)
