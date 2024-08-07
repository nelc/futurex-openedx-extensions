"""Roles helpers for FutureX Open edX Extensions."""
from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Dict, List, Tuple

from common.djangoapps.student.models import CourseAccessRole
from django.contrib.auth import get_user_model
from django.db.models import OuterRef, Q, Subquery
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers.caching import cache_dict
from futurex_openedx_extensions.helpers.converters import error_details_to_dictionary, ids_string_to_list
from futurex_openedx_extensions.helpers.models import ViewAllowedRoles
from futurex_openedx_extensions.helpers.tenants import get_accessible_tenant_ids, get_all_tenant_ids

logger = logging.getLogger(__name__)


def is_valid_course_access_role(course_access_role: dict) -> bool:
    """
    Check if the course access role is valid.

    :param course_access_role: The course access role
    :type course_access_role: dict
    :return: True if the course access role is valid, False otherwise
    :rtype: bool
    """
    org = course_access_role['org'].strip()
    course_id = course_access_role['course_id'] or ''

    if not course_id and not org:
        logger.error('Invalid course access role (both course_id and org are empty!): id=%s', course_access_role['id'])
        return False

    if course_id and not org:
        logger.error('Invalid course access role (course_id with no org!): id=%s', course_access_role['id'])
        return False

    if course_id and org != course_access_role['course_org']:
        logger.error('Invalid course access role (org mismatch!): id=%s', course_access_role['id'])
        return False

    return True


def optimize_access_roles_result(access_roles: dict, course_org: dict) -> None:
    """
    Remove redundant course access roles that specify a course_id when the user already has access to the entire org.

    :param access_roles: The access roles
    :type access_roles: dict
    :param course_org: The quick lookup for organization for each course
    :type course_org: dict
    """
    for user_id, roles in access_roles.items():
        for role, data in roles.items():
            fixed_course_limited_access = []
            orgs_of_courses = []
            for course_id in data['course_limited_access']:
                org = course_org[course_id]
                if org not in data['orgs_full_access']:
                    fixed_course_limited_access.append(course_id)
                    if org not in orgs_of_courses:
                        orgs_of_courses.append(org)
            access_roles[user_id][role]['course_limited_access'] = fixed_course_limited_access
            access_roles[user_id][role]['orgs_of_courses'] = orgs_of_courses


@cache_dict(timeout='FX_CACHE_TIMEOUT_COURSE_ACCESS_ROLES', key_generator_or_name=cs.CACHE_NAME_ALL_COURSE_ACCESS_ROLES)
def get_all_course_access_roles() -> dict:
    """
    Get all course access roles.

    result:
    {
        <user_id>: {
            <role>: {
                'orgs_full_access': [org1, org2, ...],
                'course_limited_access': [course_id1, course_id2, ...],
                'orgs_of_courses': [org1, org2, ...],
            },
            ...
        },
        <user_id>: {
            <role>: {
                'orgs_full_access': [org1, org2, ...],
                'course_limited_access': [course_id1, course_id2, ...],
                'orgs_of_courses': [org1, org2, ...],
            },
            ...
        },
        ...
    }

    :return: All course access roles
    :rtype: dict
    """
    course_org = {}
    access_roles = CourseAccessRole.objects.filter(
        user__is_active=True,
        user__is_staff=False,
        user__is_superuser=False,
    ).annotate(
        course_org=Subquery(
            CourseOverview.objects.filter(id=OuterRef('course_id')).values('org')
        ),
    ).values(
        'id', 'user_id', 'role', 'org', 'course_id', 'course_org',
    )

    result: dict[int, dict] = {}
    for access_role in access_roles:
        if not is_valid_course_access_role(access_role):
            continue

        user_id = access_role['user_id']
        role = access_role['role']
        org = access_role['org']
        course_id = str(access_role['course_id']) if access_role['course_id'] else None

        if user_id not in result:
            result[user_id] = {}

        if role not in result[user_id]:
            result[user_id][role] = {
                'orgs_full_access': [],
                'course_limited_access': [],
            }

        if course_id:
            if course_id not in course_org:
                course_org[course_id] = org
            if course_id not in result[user_id][role]['course_limited_access']:
                result[user_id][role]['course_limited_access'].append(course_id)

        elif org not in result[user_id][role]['orgs_full_access']:
            result[user_id][role]['orgs_full_access'].append(org)

    optimize_access_roles_result(result, course_org)

    return result


def check_tenant_access(user: get_user_model, tenant_ids_string: str) -> tuple[bool, dict]:
    """
    Check if the user has access to the provided tenant IDs

    :param user: The user to check.
    :type user: get_user_model
    :param tenant_ids_string: Comma-separated string of tenant IDs
    :type tenant_ids_string: str
    :return: Tuple of a boolean indicating if the user has access, and a dictionary of error details if any
    """
    try:
        tenant_ids = set(ids_string_to_list(tenant_ids_string))
    except ValueError as exc:
        return False, error_details_to_dictionary(
            reason='Invalid tenant IDs provided. It must be a comma-separated list of integers',
            error=str(exc)
        )

    wrong_tenant_ids = tenant_ids - set(get_all_tenant_ids())
    if wrong_tenant_ids:
        return False, error_details_to_dictionary(
            reason='Invalid tenant IDs provided',
            tenant_ids=list(wrong_tenant_ids)
        )

    user_roles = list(get_all_course_access_roles().get(user.id, {}).keys())
    accessible_tenant_ids = get_accessible_tenant_ids(user, user_roles)
    inaccessible_tenants = tenant_ids - set(accessible_tenant_ids)
    if inaccessible_tenants:
        return False, error_details_to_dictionary(
            reason='User does not have access to these tenants',
            tenant_ids=list(inaccessible_tenants),
        )

    return True, {'tenant_ids': list(tenant_ids)}


class FXViewRoleInfoMetaClass(type):
    """Metaclass to provide role information to the view."""
    _fx_views_with_roles: dict[str, Any] = {'_all_view_names': {}}
    fx_view_name = None
    fx_view_description = None
    fx_default_read_write_roles: List[str] = []
    fx_default_read_only_roles: List[str] = []
    fx_allowed_read_methods: List[str] = ['GET', 'HEAD', 'OPTIONS']
    fx_allowed_write_methods: List[str] = []

    @staticmethod
    def get_read_methods() -> List[str]:
        """Get a list of the read methods."""
        return ['GET', 'HEAD', 'OPTIONS']

    @staticmethod
    def get_write_methods() -> List[str]:
        """Get a list of the write methods."""
        return ['POST', 'PUT', 'PATCH', 'DELETE']

    @classmethod
    def check_allowed_read_methods(mcs) -> bool:
        """Check if the allowed read methods are valid."""
        wrong_methods = set(mcs.fx_allowed_read_methods) - set(mcs.get_read_methods())
        if wrong_methods:
            logger.error('fx_allowed_read_methods contains invalid methods (%s)', mcs.__name__)
            return False
        return True

    @classmethod
    def check_allowed_write_methods(mcs) -> bool:
        """Check if the allowed to write methods are valid."""
        wrong_methods = set(mcs.fx_allowed_write_methods) - set(mcs.get_write_methods())
        if wrong_methods:
            logger.error('fx_allowed_write_methods contains invalid methods (%s)', mcs.__name__)
            return False
        return True

    @classmethod
    def is_write_supported(mcs) -> bool:
        """Check if write is supported."""
        return bool(mcs.fx_allowed_write_methods)

    def __init__(cls, name: str, bases: Tuple, attrs: Dict[str, Any]) -> None:
        """Initialize the metaclass."""
        super().__init__(name, bases, attrs)

        if name.endswith('Mixin'):
            return

        cls.fx_view_name = (cls.fx_view_name or '').strip()
        if not cls.fx_view_name:
            logger.error('fx_view_name is not defined for view (%s)', name)
            return

        if len(cls.fx_view_name) > 255 or len(cls.fx_view_description or '') > 255:
            logger.error('fx_view_name and fx_view_description length must be below 256 characters (%s)', name)
            return

        if name in cls._fx_views_with_roles:
            logger.error('FXViewRoleInfoMetaClass error: Unexpected class redefinition (%s)', name)
            return

        if cls.fx_view_name in cls._fx_views_with_roles['_all_view_names']:
            logger.error('fx_view_name duplicate between (%s) and another view', name)
            return

        cls._fx_views_with_roles[name] = {
            'name': cls.fx_view_name,
            'description': cls.fx_view_description,
            'default_read_only_roles': cls.fx_default_read_only_roles,
            'default_read_write_roles': cls.fx_default_read_write_roles,
        }
        cls._fx_views_with_roles['_all_view_names'][cls.fx_view_name] = cls


def get_fx_view_with_roles() -> dict:
    """
    Get the view with roles.

    :return: The view with roles
    :rtype: dict
    """
    return deepcopy(FXViewRoleInfoMetaClass._fx_views_with_roles)  # pylint: disable=protected-access


def is_view_exist(view_name: str) -> bool:
    """
    Check if the view supports write.

    :param view_name: The view name
    :type view_name: str
    :return: True if the view exists, False otherwise
    :rtype: bool
    """
    return view_name in get_fx_view_with_roles()['_all_view_names']


def is_view_support_write(view_name: str) -> bool:
    """
    Check if the view supports write.

    :param view_name: The view name
    :type view_name: str
    :return: True if the view supports write, False otherwise
    :rtype: bool
    """
    view_class = get_fx_view_with_roles()['_all_view_names'].get(view_name)
    if not view_class:
        return False

    return view_class.is_write_supported()


class FXViewRoleInfoMixin(metaclass=FXViewRoleInfoMetaClass):
    """View mixin to provide role information to the view."""
    @property
    def fx_permission_info(self) -> dict:
        """Get fx_permission_info from the request."""
        return self.request.fx_permission_info if hasattr(  # type: ignore[attr-defined]
            self.request, 'fx_permission_info') else {}  # type: ignore[attr-defined]

    @staticmethod
    @cache_dict(timeout='FX_CACHE_TIMEOUT_VIEW_ROLES', key_generator_or_name=cs.CACHE_NAME_ALL_VIEW_ROLES)
    def get_allowed_roles_all_views() -> Dict[str, List[str]]:
        """
        Get the allowed roles for all views.

        :return: The allowed roles for all views
        :rtype: dict
        """
        fx_views_with_roles = get_fx_view_with_roles()

        result: dict[str, List] = {}
        for info in ViewAllowedRoles.objects.all():
            if info.view_name in result:
                result[info.view_name].append(info.allowed_role)
            else:
                result[info.view_name] = [info.allowed_role]

        to_delete = [
            view_name for view_name in result
            if view_name not in fx_views_with_roles['_all_view_names']
        ]

        if to_delete:
            ViewAllowedRoles.objects.filter(view_name__in=to_delete).delete()
            for view_name in to_delete:
                result.pop(view_name)

        fx_views_with_roles.pop('_all_view_names')
        for info in fx_views_with_roles.values():
            view_name = info['name']
            if view_name not in result:
                result[view_name] = info['default_read_only_roles'].copy()
                ViewAllowedRoles.objects.bulk_create([
                    ViewAllowedRoles(
                        view_name=view_name,
                        view_description=info['description'],
                        allowed_role=role,
                        allow_write=role in info['default_read_only_roles'],
                    )
                    for role in result[view_name]
                ])

        return result


def get_usernames_with_access_roles(orgs: list[str], active_filter: None | bool = None) -> list[str]:
    """
    Get the users with access roles for the given orgs. Including all staff and superusers.

    :param orgs: The orgs to filter on
    :type orgs: list
    :param active_filter: The active filter to apply. None for no filter
    :type active_filter: None | bool
    :return: The list of usernames with access roles
    :rtype: list
    """
    queryset = get_user_model().objects.filter(
        Q(is_staff=True) | Q(is_superuser=True) | Q(courseaccessrole__org__in=orgs),
    )

    if active_filter is not None:
        queryset = queryset.filter(is_active=active_filter)

    return list(queryset.distinct().values_list('username', flat=True))
