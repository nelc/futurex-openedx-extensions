"""Roles helpers for FutureX Open edX Extensions."""
from __future__ import annotations

import logging
import re
from copy import deepcopy
from enum import Enum
from typing import Any, Dict, List, Tuple

from common.djangoapps.student.models import CourseAccessRole
from django.contrib.auth import get_user_model
from django.db.models import Exists, OuterRef, Q, Subquery
from django_mysql.models import QuerySet
from opaque_keys.edx.django.models import CourseKeyField
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers.caching import cache_dict
from futurex_openedx_extensions.helpers.constants import COURSE_ID_REGX
from futurex_openedx_extensions.helpers.converters import error_details_to_dictionary, ids_string_to_list
from futurex_openedx_extensions.helpers.models import ViewAllowedRoles
from futurex_openedx_extensions.helpers.tenants import (
    get_accessible_tenant_ids,
    get_all_tenant_ids,
    get_course_org_filter_list,
    get_tenants_by_org,
)

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

    if course_id and org.lower() != course_access_role['course_org'].lower():
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
        org = access_role['org'].lower()
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
            result[user_id][role]['course_limited_access'].append(course_id)

        else:
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


class RoleType(Enum):
    """Role types."""
    ORG_WIDE = 'org_wide'
    COURSE_SPECIFIC = 'course_specific'


def _apply_special_filters(  # pylint: disable=too-many-locals
    queryset: QuerySet,
    course_ids_filter: list[str] | None,
    remove_redundant: bool,
    exclude_role_type: RoleType | None,
    user_id_distinct: bool = False,
) -> QuerySet:
    """
    Apply special filters to the queryset.

    :param queryset: The queryset to filter
    :type queryset: QuerySet
    :param course_ids_filter: The course IDs to filter on. None for no filter
    :type course_ids_filter: list
    :param remove_redundant: True to exclude redundant roles, False otherwise
    :type remove_redundant: bool
    :param exclude_role_type: The role type to exclude. None for no filter
    :type exclude_role_type: RoleType
    :param user_id_distinct: True to return only distinct user IDs, False otherwise
    :type user_id_distinct: bool
    :return: The filtered queryset
    :rtype: QuerySet
    """
    def _no_filter(qs: QuerySet) -> QuerySet:
        """Keep it as it is."""
        if user_id_distinct:
            qs = qs.values('user_id').distinct().order_by()
        return qs

    def _just_remove_org_wide_roles(qs: QuerySet) -> QuerySet:
        """Remove org-wide roles."""
        qs = qs.exclude(course_id=CourseKeyField.Empty)
        if user_id_distinct:
            qs = qs.values('user_id').distinct().order_by()
        return qs

    def _just_remove_course_roles(qs: QuerySet) -> QuerySet:
        """Remove course-specific roles."""
        qs = qs.filter(course_id=CourseKeyField.Empty)
        if user_id_distinct:
            qs = qs.values('user_id').distinct().order_by()
        return qs

    def _just_no_redundant(qs: QuerySet) -> QuerySet:
        """Remove redundant roles."""
        if user_id_distinct:
            return qs.filter(
                course_id=CourseKeyField.Empty
            ).values('user_id').distinct().order_by().union(
                _no_redundant_no_org_roles(qs).values('user_id').distinct().order_by()
            )

        return qs.filter(
            course_id=CourseKeyField.Empty
        ).union(
            _no_redundant_no_org_roles(qs)
        )

    def _no_redundant_no_org_roles(qs: QuerySet) -> QuerySet:
        """Remove redundant roles and org-wide roles."""
        qs = qs.exclude(course_id=CourseKeyField.Empty).filter(
            ~Exists(
                qs.filter(
                    course_id=CourseKeyField.Empty,
                    user=OuterRef('user'),
                    role=OuterRef('role'),
                    org=OuterRef('org'),
                )
            )
        )
        if user_id_distinct:
            qs = qs.values('user_id').distinct().order_by()
        return qs

    def _select_courses(qs: QuerySet) -> QuerySet:
        """Keep only selected courses along with org-wide roles."""
        qs = qs.filter(Q(course_id__in=course_ids_filter) | Q(course_id=CourseKeyField.Empty))
        if user_id_distinct:
            qs = qs.values('user_id').distinct().order_by()
        return qs

    def _keep_only_select_courses(qs: QuerySet) -> QuerySet:
        """Keep only selected courses and remove org-wide roles."""
        qs = qs.filter(course_id__in=course_ids_filter)
        if user_id_distinct:
            qs = qs.values('user_id').distinct().order_by()
        return qs

    def _no_redundant_and_select_courses(qs: QuerySet) -> QuerySet:
        """Remove redundant roles and keep only selected courses."""
        if user_id_distinct:
            return qs.filter(
                course_id=CourseKeyField.Empty
            ).values('user_id').distinct().order_by().union(
                _no_redundant_no_org_roles_and_select_courses(qs).values('user_id').distinct().order_by()
            )

        return qs.filter(
            course_id=CourseKeyField.Empty
        ).union(
            _no_redundant_no_org_roles_and_select_courses(qs)
        )

    def _no_redundant_no_org_roles_and_select_courses(qs: QuerySet) -> QuerySet:
        """Remove redundant roles and org-wide roles and keep only selected courses."""
        qs = qs.filter(
            course_id__in=course_ids_filter
        ).filter(
            ~Exists(
                qs.filter(
                    course_id=CourseKeyField.Empty,
                    user=OuterRef('user'),
                    role=OuterRef('role'),
                    org=OuterRef('org'),
                )
            )
        )
        if user_id_distinct:
            qs = qs.values('user_id').distinct().order_by()
        return qs

    _remove_redundant = True
    _keep_redundant = False
    _selected_courses = True
    _all_courses = False
    _exclude_org_wide_roles = str(RoleType.ORG_WIDE)
    _exclude_course_specific_roles = str(RoleType.COURSE_SPECIFIC)
    _no_exclusion = 'None'

    decision_matrix = {
        _all_courses: {
            _keep_redundant: {
                _no_exclusion: _no_filter,
                _exclude_org_wide_roles: _just_remove_org_wide_roles,
                _exclude_course_specific_roles: _just_remove_course_roles,
            },
            _remove_redundant: {
                _no_exclusion: _just_no_redundant,
                _exclude_org_wide_roles: _no_redundant_no_org_roles,
                _exclude_course_specific_roles: _just_remove_course_roles,
            },
        },
        _selected_courses: {
            _keep_redundant: {
                _no_exclusion: _select_courses,
                _exclude_org_wide_roles: _keep_only_select_courses,
                _exclude_course_specific_roles: _just_remove_course_roles,
            },
            _remove_redundant: {
                _no_exclusion: _no_redundant_and_select_courses,
                _exclude_org_wide_roles: _no_redundant_no_org_roles_and_select_courses,
                _exclude_course_specific_roles: _just_remove_course_roles,
            },
        },
    }

    queryset = decision_matrix[bool(course_ids_filter)][remove_redundant][str(exclude_role_type or _no_exclusion)](
        queryset
    )
    return queryset


def get_course_access_roles_queryset(  # pylint: disable=too-many-arguments
    orgs_filter: list[str],
    remove_redundant: bool,
    users: list[get_user_model] | None = None,
    search_text: str | None = None,
    roles_filter: list[str] | None = None,
    active_filter: bool | None = None,
    course_ids_filter: list[str] | None = None,
    exclude_role_type: RoleType | None = None,
    user_id_distinct: bool = False,
) -> QuerySet:
    """
    Get the course access roles queryset.

    :param orgs_filter: The orgs to filter on
    :type orgs_filter: list
    :param remove_redundant: True to exclude redundant roles, False otherwise. Redundant roles are course-specific roles
        that are already covered by another org-wide role for the same user
    :type remove_redundant: bool
    :param users: The users queryset. None for no filter
    :type users: list
    :param search_text: The search text to filter on. Search in email, username, and name. None for no filter
    :type search_text: str
    :param roles_filter: The roles to filter on. None for no filter
    :type roles_filter: list
    :param active_filter: The active filter to apply. None for no filter
    :type active_filter: bool
    :param course_ids_filter: The course IDs to filter on. None for no filter
    :type course_ids_filter: list
    :param exclude_role_type: The role type to exclude. None for no filter
    :type exclude_role_type: RoleType
    :param user_id_distinct: True to return only distinct user IDs, False otherwise
    :type user_id_distinct: bool
    :return: The roles for the users queryset
    :rtype: QuerySet
    """
    if exclude_role_type is not None and not isinstance(exclude_role_type, RoleType):
        try:
            exclude_role_type = RoleType(exclude_role_type)
        except ValueError as exc:
            if exclude_role_type == '':
                exclude_role_type = 'EmptyString'
            raise TypeError(f'Invalid exclude_role_type: {exclude_role_type}') from exc

    for course_id in course_ids_filter or []:
        if not re.search(r'^' + COURSE_ID_REGX, course_id):
            raise ValueError(f'Invalid course ID format: {course_id}')

    queryset = CourseAccessRole.objects.filter(
        user__is_staff=False,
        user__is_superuser=False,
    )

    if users:
        queryset = queryset.filter(user__in=users)

    if search_text:
        queryset = queryset.filter(
            Q(user__username__icontains=search_text) |
            Q(user__email__icontains=search_text) |
            Q(user__profile__name__icontains=search_text),
        )

    if active_filter is not None:
        queryset = queryset.filter(user__is_active=active_filter)

    if roles_filter:
        queryset = queryset.filter(role__in=roles_filter)

    if course_ids_filter:
        tenants_of_courses = []
        for org in CourseOverview.objects.filter(id__in=course_ids_filter).values_list('org', flat=True).distinct():
            tenants_of_courses.extend(get_tenants_by_org(org))
        tenants_of_courses = list(set(tenants_of_courses))
        orgs_of_courses = set(get_course_org_filter_list(tenants_of_courses)['course_org_filter_list'])

        queryset = queryset.filter(org__in=list(set(orgs_filter).intersection(orgs_of_courses)))

    else:
        queryset = queryset.filter(org__in=orgs_filter)

    return _apply_special_filters(queryset, course_ids_filter, remove_redundant, exclude_role_type, user_id_distinct)
