"""Permission classes for FutureX Open edX Extensions."""
import json

from common.djangoapps.student.models import CourseAccessRole
from django.db.models import Subquery
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.permissions import BasePermission, IsAuthenticated

from futurex_openedx_extensions.helpers.constants import TENANT_LIMITED_ADMIN_ROLES
from futurex_openedx_extensions.helpers.extractors import get_course_id_from_uri
from futurex_openedx_extensions.helpers.tenants import check_tenant_access


class HasCourseAccess(IsAuthenticated):
    """Permission class to check if the user has access to the course."""
    def has_permission(self, request, view):
        """Check if the user has access to the course."""
        if not super().has_permission(request, view):
            raise NotAuthenticated()

        course_id = get_course_id_from_uri(request.build_absolute_uri())
        if not course_id or not CourseOverview.objects.filter(id=course_id).exists():
            raise PermissionDenied(detail=json.dumps({"reason": "Invalid course_id"}))

        if request.user.is_staff or request.user.is_superuser:
            return True

        if not CourseAccessRole.objects.filter(
            user=request.user,
            org=Subquery(
                CourseOverview.objects.filter(id=course_id).values('org')
            ),
            role__in=TENANT_LIMITED_ADMIN_ROLES,
        ).exists():
            raise PermissionDenied(detail=json.dumps({"reason": "User does not have access to the course"}))

        return True


class HasTenantAccess(IsAuthenticated):
    """Permission class to check if the user is a tenant admin."""
    def has_permission(self, request, view):
        """Check if the user is a permission to the tenant"""
        if not super().has_permission(request, view):
            raise NotAuthenticated()

        tenant_ids = request.GET.get('tenant_ids')
        if tenant_ids:
            has_access, details = check_tenant_access(request.user, tenant_ids)
            if not has_access:
                raise PermissionDenied(detail=json.dumps(details))

        return True


class IsSystemStaff(IsAuthenticated):
    """Permission class to check if the user is a staff member."""
    def has_permission(self, request, view):
        """Check if the user is a staff member"""
        if not super().has_permission(request, view):
            raise NotAuthenticated()

        if not request.user.is_staff and not request.user.is_superuser:
            raise PermissionDenied(detail=json.dumps({"reason": "User is not a system staff member"}))

        return True


class IsAnonymousOrSystemStaff(BasePermission):
    """Permission class to check if the user is anonymous or system staff."""
    def has_permission(self, request, view):
        """Check if the user is anonymous"""
        if not hasattr(request, "user") or not request.user or not request.user.is_authenticated:
            return True
        return request.user.is_staff or request.user.is_superuser
