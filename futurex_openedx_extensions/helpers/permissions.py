"""Permission classes for FutureX Open edX Extensions."""
from __future__ import annotations

import json
from typing import Any, List

from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.permissions import BasePermission, IsAuthenticated

from futurex_openedx_extensions.helpers.roles import check_tenant_access, get_user_course_access_roles
from futurex_openedx_extensions.helpers.tenants import get_accessible_tenant_ids, get_course_org_filter_list


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

    fx_permission_info_one_tenant = {
        'user': fx_permission_info['user'],
        'user_roles': fx_permission_info['user_roles'],
        'is_system_staff_user': fx_permission_info['is_system_staff_user'],
        'permitted_tenant_ids': [tenant_id],
        'view_allowed_roles': fx_permission_info['view_allowed_roles'],
        'view_allowed_full_access_orgs': list(filtered_orgs.intersection(
            set(fx_permission_info['view_allowed_full_access_orgs'])
        )),
        'view_allowed_course_access_orgs': list(filtered_orgs.intersection(
            set(fx_permission_info['view_allowed_course_access_orgs'])
        )),
    }

    return fx_permission_info_one_tenant


class FXBaseAuthenticatedPermission(IsAuthenticated):
    """Base permission class for FutureX Open edX Extensions."""

    def verify_access_roles(self, request: Any, view: Any) -> bool:
        """Verify access roles."""
        raise NotImplementedError(f'(verify_access_roles) is not implemented ({self.__class__.__name__})')

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

        is_system_staff_user = request.user.is_staff or request.user.is_superuser
        view_allowed_roles: List[str] = view.get_allowed_roles_all_views()[view.fx_view_name]
        tenant_ids_string: str | None = request.GET.get('tenant_ids')
        user_roles: dict = {} if is_system_staff_user else get_user_course_access_roles(request.user.id)['roles']

        list_of_roles: List[str] = list(user_roles.keys())
        if tenant_ids_string:
            has_access, details = check_tenant_access(request.user, tenant_ids_string)
            if not has_access:
                raise PermissionDenied(detail=json.dumps(details))
            tenant_ids = details['tenant_ids']
        else:
            tenant_ids = get_accessible_tenant_ids(request.user, roles_filter=list_of_roles or None)

        request.fx_permission_info = {
            'user': request.user,
            'user_roles': user_roles,
            'is_system_staff_user': is_system_staff_user,
            'permitted_tenant_ids': tenant_ids,
            'view_allowed_roles': view_allowed_roles,
        }

        if is_system_staff_user:
            request.fx_permission_info.update({
                'view_allowed_full_access_orgs': get_course_org_filter_list(tenant_ids)['course_org_filter_list'],
                'view_allowed_course_access_orgs': [],
            })
            return True

        permitted_orgs: set = set(get_course_org_filter_list(tenant_ids)['course_org_filter_list'])
        full_access_orgs: set = set()
        course_access_orgs: set = set()
        for role in view_allowed_roles:
            if role in list_of_roles:
                full_access_orgs.update(
                    permitted_orgs.intersection(set(user_roles[role]['orgs_full_access']))
                )
                course_access_orgs.update(
                    permitted_orgs.intersection(set(user_roles[role]['orgs_of_courses']))
                )

        request.fx_permission_info.update({
            'view_allowed_full_access_orgs': list(full_access_orgs),
            'view_allowed_course_access_orgs': list(course_access_orgs),
        })

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
        if (
            not request.fx_permission_info['view_allowed_full_access_orgs'] and
            not request.fx_permission_info['view_allowed_course_access_orgs']
        ):
            raise PermissionDenied(detail=json.dumps({'reason': 'User does not have course access to the tenant'}))

        return True


class IsSystemStaff(IsAuthenticated):
    """Permission class to check if the user is a staff member."""
    def has_permission(self, request: Any, view: Any) -> bool:
        """Check if the user is a staff member"""
        if not super().has_permission(request, view):
            raise NotAuthenticated()

        if not request.user.is_staff and not request.user.is_superuser:
            raise PermissionDenied(detail=json.dumps({'reason': 'User is not a system staff member'}))

        return True


class IsAnonymousOrSystemStaff(BasePermission):
    """Permission class to check if the user is anonymous or system staff."""
    def has_permission(self, request: Any, view: Any) -> bool:
        """Check if the user is anonymous"""
        if not hasattr(request, 'user') or not request.user or not request.user.is_authenticated:
            return True
        return request.user.is_staff or request.user.is_superuser
