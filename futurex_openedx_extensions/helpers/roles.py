"""Roles helpers for FutureX Open edX Extensions."""
# pylint: disable=too-many-lines
from __future__ import annotations

import logging
from copy import deepcopy
from enum import Enum
from typing import Any, Dict, List, Tuple

from common.djangoapps.student.models import CourseAccessRole, UserSignupSource
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import DatabaseError, transaction
from django.db.models import BooleanField, Exists, OuterRef, Q, QuerySet, Subquery, Value
from django.db.models.functions import Lower
from opaque_keys.edx.django.models import CourseKeyField
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers.caching import cache_dict
from futurex_openedx_extensions.helpers.converters import (
    error_details_to_dictionary,
    get_allowed_roles,
    ids_string_to_list,
)
from futurex_openedx_extensions.helpers.course_creator_manager import CourseCreatorManager
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.extractors import (
    DictHashcode,
    DictHashcodeSet,
    get_orgs_of_courses,
    verify_course_ids,
)
from futurex_openedx_extensions.helpers.models import ViewAllowedRoles
from futurex_openedx_extensions.helpers.querysets import check_staff_exist_queryset
from futurex_openedx_extensions.helpers.tenants import (
    get_all_tenant_ids,
    get_course_org_filter_list,
    get_tenants_by_org,
    get_tenants_sites,
)
from futurex_openedx_extensions.helpers.users import get_user_by_key, is_system_staff_user

logger = logging.getLogger(__name__)


def validate_course_access_role(course_access_role: dict) -> None:
    """
    Validate the course access role.

    :param course_access_role: The course access role
    :type course_access_role: dict
    """
    def check_broken_rule(broken_rule: bool, code: FXExceptionCodes, message: str) -> None:
        """Validate the rule."""
        message = f'Invalid course access role: {message} (id: {course_access_role["id"]})'
        if broken_rule:
            raise FXCodedException(code=code, message=message)

    org = course_access_role['org'].strip()
    course_id = course_access_role['course_id']
    role = course_access_role['role']

    check_broken_rule(
        role not in cs.COURSE_ACCESS_ROLES_ALL,
        FXExceptionCodes.ROLE_INVALID_ENTRY,
        f'invalid role ({role})!',
    )

    check_broken_rule(
        role not in cs.COURSE_ACCESS_ROLES_SUPPORTED_READ,
        FXExceptionCodes.ROLE_UNSUPPORTED,
        f'unsupported role ({role})!',
    )

    check_broken_rule(
        role in cs.COURSE_ACCESS_ROLES_COURSE_ONLY and not (course_id and org),
        FXExceptionCodes.ROLE_INVALID_ENTRY,
        f'role {role} must have both course_id and org!',
    )

    check_broken_rule(
        role in cs.COURSE_ACCESS_ROLES_TENANT_ONLY and (course_id or not org),
        FXExceptionCodes.ROLE_INVALID_ENTRY,
        f'role {role} must have an org without course_id!',
    )

    check_broken_rule(
        role in cs.COURSE_ACCESS_ROLES_TENANT_OR_COURSE and not org,
        FXExceptionCodes.ROLE_INVALID_ENTRY,
        f'role {role} must have at least an org, it can also have a course_id!',
    )

    check_broken_rule(
        role in cs.COURSE_ACCESS_ROLES_ACCEPT_COURSE_ID and course_id and (
            org != course_access_role['course_org']
        ),
        FXExceptionCodes.ROLE_INVALID_ENTRY,
        f'expected org value to be ({course_access_role["course_org"]}), but got ({org})!',
    )

    check_broken_rule(
        role in cs.COURSE_ACCESS_ROLES_GLOBAL and (course_id or org),
        FXExceptionCodes.ROLE_INVALID_ENTRY,
        f'{role} role must have both org and course_id empty!',
    )

    if role in [cs.COURSE_CREATOR_ROLE_GLOBAL, cs.COURSE_CREATOR_ROLE_TENANT]:
        creator = CourseCreatorManager(user_id=course_access_role['user_id'])

        check_broken_rule(
            not creator.db_record,
            FXExceptionCodes.ROLE_INVALID_ENTRY,
            f'missing course-creator record for {role} role!',
        )

        check_broken_rule(
            not creator.is_granted(),
            FXExceptionCodes.ROLE_INACTIVE,
            f'course-creator record for {role} role is inactive!',
        )

        check_broken_rule(
            role == cs.COURSE_CREATOR_ROLE_GLOBAL and (not creator.is_all_orgs() or not creator.is_orgs_empty()),
            FXExceptionCodes.ROLE_INVALID_ENTRY,
            f'{role} role must have all_organizations=True with no details for organizations!',
        )

        check_broken_rule(
            role == cs.COURSE_CREATOR_ROLE_TENANT and (creator.is_all_orgs() or creator.is_orgs_empty()),
            FXExceptionCodes.ROLE_INVALID_ENTRY,
            f'{role} role must have all_organizations=False with at least one organization set!',
        )

        check_broken_rule(
            role == cs.COURSE_CREATOR_ROLE_TENANT and org not in creator.get_orgs(),
            FXExceptionCodes.ROLE_INACTIVE,
            f'missing organization in course-creator record for {role} role!',
        )


def cache_name_user_course_access_roles(user_id: int) -> str:
    """
    Get the cache name for the user course access roles.

    :param user_id: The user ID
    :type user_id: int
    :return: The cache name
    :rtype: str
    """
    return f'{cs.CACHE_NAME_USER_COURSE_ACCESS_ROLES}_{user_id}'


@cache_dict(timeout='FX_CACHE_TIMEOUT_COURSE_ACCESS_ROLES', key_generator_or_name=cache_name_user_course_access_roles)
def get_user_course_access_roles(user_id: int) -> dict:
    """
    Get all course access roles for one user.

    result:
    {
        'roles': {
            <role1>: {
                'orgs_full_access': [org1, org2, ...],
                'tenant_ids_full_access': [1, 2, ...],
                'course_limited_access': [course_id1, course_id2, ...],
                'orgs_of_courses': [org3, org4, ...],
                'tenant_ids': [1, 2, 3, ...],
            },
            <role2>: {
                'orgs_full_access': [org1, org2, ...],
                'tenant_ids_full_access': [1, 2, ...],
                'course_limited_access': [course_id1, course_id2, ...],
                'orgs_of_courses': [org3, org4, ...],
                'tenant_ids': [1, 2, 3, ...],
            },
            ...
        },
        'useless_entries_exist': bool,
    }

    :param user_id: The user ID
    :type user_id: int
    :return: All course access roles for the user
    :rtype: dict
    """
    access_roles = CourseAccessRole.objects.filter(
        user_id=user_id,
    ).annotate(
        course_org=Subquery(
            CourseOverview.objects.filter(id=OuterRef('course_id')).values('org')
        ),
    ).annotate(
        org_lower_case=Lower('org'),
    ).annotate(
        course_org_lower_case=Lower('course_org'),
    ).values(
        'id', 'user_id', 'role', 'org_lower_case', 'course_id', 'course_org_lower_case',
    ).order_by('role', 'org_lower_case', 'course_id')  # ordering is crucial for the result

    result: Dict[str, Any] = {}
    useless_entry = False
    for access_role in access_roles:
        access_role['org'] = access_role['org_lower_case']
        access_role['course_org'] = access_role['course_org_lower_case']
        if access_role['course_id'] is None or access_role['course_id'] == CourseKeyField.Empty:
            access_role['course_id'] = ''
        else:
            access_role['course_id'] = str(access_role['course_id'])

        try:
            validate_course_access_role(access_role)
        except FXCodedException:
            useless_entry = True
            continue

        role = access_role['role']
        org = access_role['org'].lower() if access_role['org'] else None
        course_id = access_role['course_id']
        course_org = access_role['course_org'].lower() if access_role['course_org'] else None

        if role not in result:
            result[role] = {
                'orgs_full_access': set(),
                'tenant_ids_full_access': set(),
                'course_limited_access': [],
                'orgs_of_courses': set(),
                'tenant_ids': set(),
            }

        if role in cs.COURSE_ACCESS_ROLES_GLOBAL:
            continue

        # ordering of access_roles is crucial for the following logic
        if not course_id:
            result[role]['orgs_full_access'].add(org)
            result[role]['tenant_ids_full_access'].update(get_tenants_by_org(org))
            result[role]['tenant_ids'].update(get_tenants_by_org(org))
        elif course_org in result[role]['orgs_full_access']:
            useless_entry = True
        else:
            result[role]['course_limited_access'].append(course_id)
            result[role]['orgs_of_courses'].add(course_org)
            result[role]['tenant_ids'].update(get_tenants_by_org(course_org))

    for _, role_data in result.items():
        role_data['orgs_full_access'] = list(role_data['orgs_full_access'])
        role_data['tenant_ids_full_access'] = list(role_data['tenant_ids_full_access'])
        role_data['orgs_of_courses'] = list(role_data['orgs_of_courses'])
        role_data['tenant_ids'] = list(role_data['tenant_ids'])

    return {
        'roles': result,
        'useless_entries_exist': useless_entry,
    }


def get_accessible_tenant_ids(user: get_user_model, roles_filter: List[str] | None = None) -> List[int]:
    """
    Get the tenants that the user has access to.

    :param user: The user to check.
    :type user: get_user_model
    :param roles_filter: List of roles to filter by. None means no filter. Empty list means no access at all.
    :type roles_filter: List[str] | None
    :return: List of accessible tenant IDs
    :rtype: List[int]
    """
    if not user:
        return []
    if is_system_staff_user(user):
        return get_all_tenant_ids()

    user_roles = get_user_course_access_roles(user.id)['roles']

    if roles_filter is None:
        roles_filter = list(user_roles.keys())
    elif not isinstance(roles_filter, list):
        raise TypeError('roles_filter must be a list')
    elif not roles_filter:
        return []

    tenant_ids = set()
    for role_name in roles_filter:
        tenant_ids.update(user_roles.get(role_name, {}).get('tenant_ids', []))

    return list(tenant_ids)


def check_tenant_access(
    user: get_user_model,
    tenant_ids_string: str,
    roles_filter: List[str] | None,
) -> tuple[bool, dict]:
    """
    Check if the user has access to the provided tenant IDs

    :param user: The user to check.
    :type user: get_user_model
    :param tenant_ids_string: Comma-separated string of tenant IDs
    :type tenant_ids_string: str
    :param roles_filter: List of roles to filter by. None means no filter. Empty list means no access at all.
    :type roles_filter: List[str] | None
    :return: Tuple of a boolean indicating if the user has access, and a dictionary of error details if any
    :rtype: tuple[bool, dict]
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

    accessible_tenant_ids = get_accessible_tenant_ids(user, roles_filter=roles_filter)
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
        Q(is_staff=True) | Q(is_superuser=True) |
        check_staff_exist_queryset(
            ref_user_id='id',
            ref_org=orgs,
            ref_course_id=None,
        ),
    )

    if active_filter is not None:
        queryset = queryset.filter(is_active=active_filter)

    return list(queryset.distinct().values_list('username', flat=True))


class RoleType(Enum):
    """Role types."""
    ORG_WIDE = 'org_wide'
    COURSE_SPECIFIC = 'course_specific'


def get_course_access_roles_queryset(  # pylint: disable=too-many-arguments, too-many-branches
    orgs_filter: list[str],
    remove_redundant: bool,
    users: list[get_user_model] | None = None,
    search_text: str | None = None,
    roles_filter: list[str] | None = None,
    active_filter: bool | None = None,
    course_ids_filter: list[str] | None = None,
    exclude_role_type: RoleType | None = None,
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

    if course_ids_filter:
        verify_course_ids(course_ids_filter)

    queryset = CourseAccessRole.objects.filter(
        user__is_staff=False,
        user__is_superuser=False,
    )

    if users:
        queryset = queryset.filter(user__in=users)

    if search_text:
        queryset = queryset.filter(
            Q(user__username__icontains=search_text) |
            Q(user__extrainfo__national_id__icontains=search_text) |
            Q(user__email__icontains=search_text) |
            Q(user__profile__name__icontains=search_text),
        )

    if active_filter is not None:
        queryset = queryset.filter(user__is_active=active_filter)

    if course_ids_filter:
        tenants_of_courses = []
        for org in CourseOverview.objects.filter(id__in=course_ids_filter).values_list('org', flat=True).distinct():
            tenants_of_courses.extend(get_tenants_by_org(org))
        tenants_of_courses = list(set(tenants_of_courses))
        orgs_of_courses = set(get_course_org_filter_list(tenants_of_courses)['course_org_filter_list'])

        orgs_filter = list(set(orgs_filter).intersection(orgs_of_courses))
        course_ids_filter_query = (Q(course_id=CourseKeyField.Empty) | Q(course_id__in=course_ids_filter))
    else:
        course_ids_filter_query = Q(Value(True, output_field=BooleanField()))

    if not roles_filter:
        roles_filter = cs.COURSE_ACCESS_ROLES_SUPPORTED_READ
    else:
        roles_filter = list(set(roles_filter).intersection(cs.COURSE_ACCESS_ROLES_SUPPORTED_READ))

    allowed_roles = get_allowed_roles(roles_filter)
    queryset = queryset.filter(
        Q(role__in=allowed_roles['global']) |
        (Q(role__in=allowed_roles['tenant_only']) & Q(org__in=orgs_filter) & Q(course_id=CourseKeyField.Empty)) |
        (Q(role__in=allowed_roles['course_only']) & Q(org__in=orgs_filter) & ~Q(course_id=CourseKeyField.Empty)) |
        (Q(role__in=allowed_roles['tenant_or_course']) & Q(org__in=orgs_filter) & course_ids_filter_query)
    )

    queryset = queryset.annotate(org_lower_case=Lower('org'))

    if remove_redundant:
        queryset = queryset.filter(
            Q(course_id=CourseKeyField.Empty) |
            (
                ~Q(course_id=CourseKeyField.Empty) &
                ~Exists(
                    CourseAccessRole.objects.filter(
                        course_id=CourseKeyField.Empty,
                        user=OuterRef('user'),
                        role=OuterRef('role'),
                        org=OuterRef('org'),
                    )
                )
            )
        )

    if exclude_role_type == RoleType.ORG_WIDE:
        queryset = queryset.exclude(course_id=CourseKeyField.Empty)

    elif exclude_role_type == RoleType.COURSE_SPECIFIC:
        queryset = queryset.filter(course_id=CourseKeyField.Empty)

    return queryset


def cache_refresh_course_access_roles(user_id: int) -> None:
    """
    Refresh the course access roles cache.

    :param user_id: The user ID
    :type user_id: int
    """
    if cache.delete(cache_name_user_course_access_roles(user_id)):
        get_user_course_access_roles(user_id)


def _verify_can_delete_course_access_roles_partial(
    caller: get_user_model, tenant_ids: list[int], user_roles: Dict[str, Any], username: str,
) -> None:
    """
    Verify if the caller can delete the course access roles for the given tenant IDs and user.

    :param caller: The caller user to check the authority
    :type caller: get_user_model
    :param tenant_ids: The tenant IDs to filter on
    :type tenant_ids: list
    :param user_roles: The user roles
    :type user_roles: Dict[str, Any]
    :return: True if the caller can delete the course access roles, False otherwise
    :rtype: bool
    """
    def collect_user_tenant_ids(list_name: str) -> set[int]:
        """Collect the tenant IDs."""
        result = set()
        for role_name, role_info in user_roles.items():
            if role_name in cs.COURSE_ACCESS_ROLES_SUPPORTED_EDIT:
                result.update(set(role_info[list_name]))
        return result

    if is_system_staff_user(caller):
        return

    tenant_ids_with_staff_role: set | list = set(tenant_ids).intersection(
        set(user_roles.get(cs.COURSE_ACCESS_ROLES_STAFF_EDITOR, {}).get('tenant_ids_full_access', []))
    )
    if tenant_ids_with_staff_role:
        tenant_ids_with_staff_role = sorted(list(tenant_ids_with_staff_role))
        raise FXCodedException(
            code=FXExceptionCodes.ROLE_DELETE,
            message=(
                f'Permission denied: cannot delete roles of user ({username}) from tenants '
                f'{tenant_ids_with_staff_role}, because the user has a tenant-wide '
                f'[{cs.COURSE_ACCESS_ROLES_STAFF_EDITOR}] role there! the caller must be a system-staff or a superuser '
                'to perform this operation.'
            ),
        )

    caller_roles = get_user_course_access_roles(caller.id)['roles']
    caller_allowed = {
        'tenant_wide': set(caller_roles.get(cs.COURSE_ACCESS_ROLES_STAFF_EDITOR, {}).get('tenant_ids_full_access', [])),
        'course_limited': set(caller_roles.get(cs.COURSE_CREATOR_ROLE_TENANT, {}).get('tenant_ids_full_access', [])),
    }
    caller_allowed['course_limited'].update(caller_allowed['tenant_wide'])

    restricted_tenant_ids: set | list = set(tenant_ids).intersection(
        collect_user_tenant_ids('tenant_ids_full_access')
    ) - caller_allowed['tenant_wide']
    if restricted_tenant_ids:
        restricted_tenant_ids = sorted(list(restricted_tenant_ids))
        raise FXCodedException(
            code=FXExceptionCodes.ROLE_DELETE,
            message=(
                f'Permission denied: cannot delete roles of user ({username}) from tenants '
                f'{restricted_tenant_ids}, because the user has a tenant-wide roles there! the caller must have '
                f'[{cs.COURSE_ACCESS_ROLES_STAFF_EDITOR}] role in the tenant to perform this operation.'
            ),
        )

    restricted_tenant_ids = set(tenant_ids).intersection(
        collect_user_tenant_ids('tenant_ids')
    ) - caller_allowed['course_limited']
    if restricted_tenant_ids:
        restricted_tenant_ids = sorted(list(restricted_tenant_ids))
        raise FXCodedException(
            code=FXExceptionCodes.ROLE_DELETE,
            message=(
                f'Permission denied: cannot delete roles of user ({username}) from tenants '
                f'{restricted_tenant_ids}, because the caller has no enough authority there! the caller must have '
                f'[{cs.COURSE_ACCESS_ROLES_STAFF_EDITOR}] or [{cs.COURSE_CREATOR_ROLE_TENANT}] role in the tenant to '
                'perform this operation.'
            ),
        )


def _verify_can_delete_course_access_roles(caller: get_user_model, tenant_ids: list[int], user: get_user_model) -> None:
    """
    Verify if the caller can delete the course access roles for the given tenant IDs and user.

    :param caller: The caller user to check the authority
    :type caller: get_user_model
    :param tenant_ids: The tenant IDs to filter on
    :type tenant_ids: list
    :param user: The user to filter on
    :type user: get_user_model
    :return: True if the caller can delete the course access roles, False otherwise
    :rtype: bool
    """
    user_roles = get_user_course_access_roles(user.id)['roles']

    _verify_can_delete_course_access_roles_partial(caller, tenant_ids, user_roles, user.username)


def _delete_course_access_roles(tenant_ids: list[int], user: get_user_model) -> None:
    """
    Delete the course access roles for the given tenant IDs and user

    :param tenant_ids: The tenant IDs to filter on
    :type tenant_ids: list
    :param user: The user to filter on
    :type user: get_user_model
    """
    orgs = get_course_org_filter_list(tenant_ids)['course_org_filter_list']

    delete_count, _ = CourseAccessRole.objects.filter(user=user).filter(
        Q(org__in=orgs) | Q(org=''),
    ).filter(
        role__in=cs.COURSE_ACCESS_ROLES_SUPPORTED_EDIT
    ).delete()

    if not delete_count:
        raise FXCodedException(
            code=FXExceptionCodes.ROLE_DELETE,
            message=f'No role found to delete for the user ({user.username}) within the given tenants {tenant_ids}!',
        )

    CourseCreatorManager(user.id).remove_orgs(orgs=orgs)

    cache_refresh_course_access_roles(user.id)


def delete_course_access_roles(caller: get_user_model, tenant_ids: list[int], user: get_user_model) -> None:
    """
    Delete the course access roles for the given tenant IDs and user

    :param caller: The caller user to check the authority
    :type caller: get_user_model
    :param tenant_ids: The tenant IDs to filter on
    :type tenant_ids: list
    :param user: The user to filter on
    :type user: get_user_model
    """
    _verify_can_delete_course_access_roles(caller, tenant_ids, user)

    _delete_course_access_roles(tenant_ids, user)

    cache_refresh_course_access_roles(user.id)


def _clean_course_access_roles(redundant_hashes: set[DictHashcode], user: get_user_model) -> None:
    """
    Clean the redundant course access roles by deleting related records of the given hashes. This function
    assumes that the input is valid.

    :param redundant_hashes: The redundant hashes to clean
    :type redundant_hashes: set
    :param user: The user to filter on
    :type user: get_user_model
    """
    for hashcode in redundant_hashes:
        try:
            course_id: str | object = hashcode.dict_item['course_id']
            if course_id is None:
                course_id = CourseKeyField.Empty

            delete_count, _ = CourseAccessRole.objects.filter(
                user=user,
                role=hashcode.dict_item['role'],
                org=hashcode.dict_item['org_lower_case'],
                course_id=course_id,
            ).delete()
            if not delete_count:
                raise FXCodedException(
                    code=FXExceptionCodes.ROLE_DELETE,
                    message=f'No role found to delete! {hashcode}',
                )

        except KeyError as exc:
            raise FXCodedException(
                code=FXExceptionCodes.ROLE_DELETE,
                message=f'Unexpected internal error! {str(exc)} is missing from the hashcode!',
            ) from exc

        except DatabaseError as exc:
            raise FXCodedException(
                code=FXExceptionCodes.ROLE_DELETE,
                message=f'Database error while deleting course access roles! {hashcode}. Error: {exc}',
            ) from exc


def _verify_can_add_org_course_creator(caller: get_user_model, orgs: list[str]) -> None:
    """
    Verify if the caller can add the course creator role for the given user and orgs.

    :param caller: The caller user to check the authority
    :type caller: get_user_model
    :param orgs: The orgs to filter on
    :type orgs: list
    """
    if is_system_staff_user(caller):
        return

    caller_roles = get_user_course_access_roles(caller.id)['roles']
    allowed_tenants = set(caller_roles.get(cs.COURSE_ACCESS_ROLES_STAFF_EDITOR, {}).get('tenant_ids_full_access', []))
    to_check_tenants = set()
    for org in orgs:
        to_check_tenants.update(get_tenants_by_org(org))

    restricted_tenant_ids: set | list = to_check_tenants - allowed_tenants
    if restricted_tenant_ids:
        restricted_tenant_ids = sorted(list(restricted_tenant_ids))
        raise FXCodedException(
            code=FXExceptionCodes.ROLE_CREATE,
            message=(
                f'Permission denied: caller ({caller.username}) does not have enough authority to add course-creator '
                f'role to other users in tenants {restricted_tenant_ids}. The caller must have '
                f'[{cs.COURSE_ACCESS_ROLES_STAFF_EDITOR}] role there!'
            ),
        )


def add_org_course_creator(caller: get_user_model, user: get_user_model, orgs: list[str]) -> None:
    """
    Add the course creator role for the given user and orgs.

    :param caller: The caller user to check the authority
    :type caller: get_user_model
    :param user: The user to add the role for
    :type user: get_user_model
    :param orgs: The orgs to filter on
    :type orgs: list
    """
    if not orgs:
        return

    orgs = [org.lower() for org in orgs]
    _verify_can_add_org_course_creator(caller, orgs)

    cache_refresh_course_access_roles(user.id)
    access_roles = get_user_course_access_roles(user.id)

    if cs.COURSE_CREATOR_ROLE_GLOBAL in access_roles['roles']:
        return
    if access_roles['useless_entries_exist']:
        raise FXCodedException(
            code=FXExceptionCodes.ROLE_INVALID_ENTRY,
            message=f'Cannot add course creator role due to invalid entries in CourseAccessRole! user: {user.username}',
        )

    role = access_roles['roles'].get(cs.COURSE_CREATOR_ROLE_TENANT, {})
    to_add = []
    for org in orgs:
        if org not in role.get('orgs_full_access', []):
            to_add.append(CourseAccessRole(
                user=user,
                role=cs.COURSE_CREATOR_ROLE_TENANT,
                org=org,
            ))
    if not to_add:
        return

    CourseAccessRole.objects.bulk_create(to_add)

    course_creator = CourseCreatorManager(user.id)
    course_creator.add_orgs(orgs)

    cache_refresh_course_access_roles(user.id)


def _verify_can_add_course_access_roles(
    caller: get_user_model,
    course_access_roles: list[CourseAccessRole],
) -> None:
    """
    Verify if the caller can add the course access roles for the given user. This is a helper function for
    add_course_access_roles that assumes valid inputs.

    :param caller: The caller user to check the authority
    :type caller: get_user_model
    :param course_access_roles: The course access roles to add
    :type course_access_roles: list
    """
    if is_system_staff_user(caller):
        return

    caller_roles = get_user_course_access_roles(caller.id)['roles']
    caller_allowed = {
        'tenant_wide': set(caller_roles.get(cs.COURSE_ACCESS_ROLES_STAFF_EDITOR, {}).get('tenant_ids_full_access', [])),
        'course_limited': set(caller_roles.get(cs.COURSE_CREATOR_ROLE_TENANT, {}).get('tenant_ids_full_access', [])),
    }
    caller_allowed['course_limited'].update(caller_allowed['tenant_wide'])

    for role in course_access_roles:
        if role.role in cs.COURSE_ACCESS_ROLES_STAFF_EDITOR and (
            role.course_id is None or role.course_id == CourseKeyField.Empty
        ):
            raise FXCodedException(
                code=FXExceptionCodes.ROLE_CREATE,
                message=(
                    f'Permission denied: caller ({caller.username}) does not have enough authority to add tenant-wide '
                    f'[{cs.COURSE_ACCESS_ROLES_STAFF_EDITOR}] role to other users. The caller must be a system-staff '
                    f'or superuser to perform this operation.'
                ),
            )

        org_tenants = set(get_tenants_by_org(role.org))
        if role.course_id is None or role.course_id == CourseKeyField.Empty:
            restricted_tenant_ids: set | list = org_tenants - caller_allowed['tenant_wide']
            if restricted_tenant_ids:
                restricted_tenant_ids = sorted(list(restricted_tenant_ids))
                raise FXCodedException(
                    code=FXExceptionCodes.ROLE_CREATE,
                    message=(
                        f'Permission denied: caller ({caller.username}) does not have enough authority to add '
                        f'tenant-wide role [{role.role}] to other users in tenants {restricted_tenant_ids}. The '
                        f'caller must have [{cs.COURSE_ACCESS_ROLES_STAFF_EDITOR}] role to perform this operation.'
                    ),
                )

        else:
            restricted_tenant_ids = org_tenants - caller_allowed['course_limited']
            if restricted_tenant_ids:
                restricted_tenant_ids = sorted(list(restricted_tenant_ids))
                raise FXCodedException(
                    code=FXExceptionCodes.ROLE_CREATE,
                    message=(
                        f'Permission denied: caller ({caller.username}) does not have enough authority to add '
                        f'[{role.role}] role to other users in tenants {restricted_tenant_ids}. The caller must have '
                        f'[{cs.COURSE_ACCESS_ROLES_STAFF_EDITOR}] or [{cs.COURSE_CREATOR_ROLE_TENANT}] role to '
                        'perform this operation.'
                    ),
                )


def _add_course_access_roles_one_user(  # pylint: disable=too-many-arguments
    caller: get_user_model,
    user: get_user_model,
    role: str,
    orgs: list[str],
    course_ids: list[str] | None,
    orgs_of_courses: Dict[str, str],
    dry_run: bool,
) -> str:
    """
    Add the course access roles for the given user. This is a helper function for add_course_access_roles that
    assumes valid inputs.

    :param caller: The caller user to check the authority
    :type caller: get_user_model
    :param user: The user to add the roles for
    :type user: get_user_model
    :param role: The role to add
    :type role: str
    :param orgs: The orgs to filter on
    :type orgs: list
    :param course_ids: The course IDs to filter on. None for no filter
    :type course_ids: list
    :param orgs_of_courses: The orgs of the courses
    :type orgs_of_courses: Dict[str, str]
    :param dry_run: True for dry run, False otherwise
    :type dry_run: bool
    :return: The status of the operation (added, updated, or not_updated)
    """
    new_entry = not get_course_access_roles_queryset(
        orgs_filter=orgs,
        remove_redundant=False,
        users=[user],
    ).exists()

    existing_roles_hash = DictHashcodeSet(
        list(get_course_access_roles_queryset(
            orgs_filter=orgs,
            remove_redundant=False,
            users=[user],
            roles_filter=[role],
            course_ids_filter=course_ids,
        ).values('role', 'org_lower_case', 'course_id')),
    )

    clean_existing_roles_hash = DictHashcodeSet(
        list(get_course_access_roles_queryset(
            orgs_filter=orgs,
            remove_redundant=True,
            users=[user],
            roles_filter=[role],
            course_ids_filter=course_ids,
        ).values('role', 'org_lower_case', 'course_id')),
    )

    if course_ids:
        new_roles: List[Dict[str, str | None]] = [{
            'role': role,
            'org_lower_case': orgs_of_courses[course_id].lower(),
            'course_id': course_id,
        } for course_id in course_ids if DictHashcode(
            {'role': role, 'org_lower_case': orgs_of_courses[course_id], 'course_id': ''},
        ) not in existing_roles_hash]
    else:
        for item in list(clean_existing_roles_hash.dict_hash_codes):
            if item.dict_item['course_id'] is not None and item.dict_item['role'] == role:
                clean_existing_roles_hash.dict_hash_codes.remove(item)
        new_roles = [{
            'role': role,
            'org_lower_case': org.lower(),
            'course_id': None,
        } for org in orgs]

    new_roles = [new_role for new_role in new_roles if DictHashcode(
        {
            'role': new_role['role'],
            'org_lower_case': new_role['org_lower_case'],
            'course_id': new_role['course_id'],
        },
    ) not in clean_existing_roles_hash]

    if not new_roles and existing_roles_hash == clean_existing_roles_hash:
        return 'not_updated'

    if not dry_run:
        _clean_course_access_roles(
            redundant_hashes=existing_roles_hash.dict_hash_codes - clean_existing_roles_hash.dict_hash_codes,
            user=user,
        )

    if not dry_run and new_roles:
        try:
            with transaction.atomic():
                if role == cs.COURSE_CREATOR_ROLE_TENANT:
                    add_org_course_creator(caller, user, orgs)

                    _add_missing_signup_source_records(user, orgs)
                else:
                    bulk_roles = [CourseAccessRole(
                        user=user,
                        role=new_role['role'],
                        org=new_role['org_lower_case'],
                        course_id=new_role['course_id'],
                    ) for new_role in new_roles]
                    _verify_can_add_course_access_roles(caller, bulk_roles)
                    CourseAccessRole.objects.bulk_create(bulk_roles)

                    _add_missing_signup_source_records(
                        user,
                        [new_role['org_lower_case'] for new_role in new_roles if new_role['org_lower_case']],
                    )

        except DatabaseError as exc:
            raise FXCodedException(
                code=FXExceptionCodes.ROLE_CREATE,
                message='Database error while adding course access roles!',
            ) from exc

        cache_refresh_course_access_roles(user.id)

    return 'added' if new_entry else 'updated'


def add_course_access_roles(  # pylint: disable=too-many-arguments, too-many-branches
    caller: get_user_model,
    tenant_ids: list[int],
    user_keys: list[get_user_model | str | int],
    role: str,
    tenant_wide: bool,
    course_ids: list[str] | None,
    dry_run: bool = False,
) -> dict:
    """
    Add the course access roles for the given tenant IDs and user.

    :param caller: The caller user to check the authority
    :type caller: get_user_model
    :param tenant_ids: The tenant IDs to filter on. If more than one tenant is provided, then tenant_wide must be set
        True, and course_ids must be None or empty list
    :type tenant_ids: list
    :param user_keys: List of users, by object, username, email, or ID. Mix of types is allowed
    :type user_keys: list[get_user_model | str | int]
    :param role: The role to add
    :type role: str
    :param tenant_wide: True for tenant-wide access, False otherwise. If True, then course_ids must be None
        or empty list
    :type tenant_wide: bool
    :param course_ids: The course IDs for course-specific access. If tenant_wide is True, then course_ids must be None
        or empty list. If tenant_wide is False, then course_ids must be provided
    :type course_ids: list
    :param dry_run: True for dry run, False otherwise
    :type dry_run: bool
    :return: Operation details
    :type: dict
    """
    try:
        orgs = get_course_org_filter_list(tenant_ids)['course_org_filter_list']
        if not orgs:
            raise ValueError('No valid tenant IDs provided')

        role = role.strip().lower()
        if role not in cs.COURSE_ACCESS_ROLES_SUPPORTED_EDIT:
            raise ValueError(f'Invalid role: {role}')

        if role in cs.COURSE_ACCESS_ROLES_TENANT_ONLY and not tenant_wide:
            raise ValueError(f'Role ({role}) can only be tenant-wide!')

        if role in cs.COURSE_ACCESS_ROLES_COURSE_ONLY and tenant_wide:
            raise ValueError(f'Role ({role}) can not be tenant-wide!')

        if (tenant_wide and course_ids) or (not tenant_wide and not course_ids):
            raise ValueError('Conflict between tenant_wide and course_ids')

        if not user_keys:
            raise ValueError('No users provided!')

        if not isinstance(user_keys, list):
            raise ValueError('Invalid user keys provided! must be a list')

        if len(user_keys) > cs.COURSE_ACCESS_ROLES_MAX_USERS_PER_OPERATION:
            raise ValueError(
                'add_course_access_roles cannot proces more than '
                f'{cs.COURSE_ACCESS_ROLES_MAX_USERS_PER_OPERATION} users at a time!'
            )

        course_ids = list(set(course_ids or []))
        orgs_of_courses = get_orgs_of_courses(course_ids)

        for course_id in course_ids:
            if orgs_of_courses['courses'][course_id] not in orgs:
                raise ValueError(f'Course ID {course_id} does not belong to the provided tenant IDs')
    except ValueError as exc:
        raise FXCodedException(
            code=FXExceptionCodes.INVALID_INPUT,
            message=str(exc),
        ) from exc

    result: Dict[str, List] = {
        'failed': [],
        'added': [],
        'updated': [],
        'not_updated': [],
    }
    for user_key in user_keys:
        user_info = get_user_by_key(user_key, fail_if_inactive=True)
        if not user_info['user']:
            result['failed'].append({
                'user_id': user_key if user_info['key_type'] == cs.USER_KEY_TYPE_ID else None,
                'username': None if user_info['key_type'] == cs.USER_KEY_TYPE_ID else user_key,
                'email': None if user_info['key_type'] == cs.USER_KEY_TYPE_ID else user_key,
                'reason_code': user_info['error_code'],
                'reason_message': user_info['error_message'],
            })
            continue

        if isinstance(user_key, get_user_model()):
            user_key = user_key.id

        try:
            status = _add_course_access_roles_one_user(
                caller, user_info['user'], role, orgs, course_ids, orgs_of_courses['courses'], dry_run
            )
        except Exception as exc:  # pylint: disable=broad-except
            result['failed'].append({
                'user_id': user_info['user'].id,
                'username': user_info['user'].username,
                'email': user_info['user'].email,
                'reason_code': exc.code if isinstance(exc, FXCodedException) else FXExceptionCodes.UNKNOWN_ERROR.value,
                'reason_message': f'{type(exc).__name__}: {str(exc)}' if not (
                    isinstance(exc, FXCodedException)
                ) else str(exc),
            })
        else:
            result[status].append(user_key)

    return result


def get_tenant_user_roles(tenant_id: int, user_id: int, only_editable_roles: bool = False) -> dict:
    """
    Get the tenant user roles.

    :param tenant_id: The tenant ID
    :type tenant_id: int
    :param user_id: The user ID
    :type user_id: int
    :param only_editable_roles: True to get only editable roles, False otherwise
    :type only_editable_roles: bool
    :return: The tenant user roles
    :rtype: dict
    """
    roles = get_user_course_access_roles(user_id)['roles']

    result: dict = {
        'tenant_id': tenant_id,
        'tenant_roles': [],
        'course_roles': {},
    }

    all_roles = cs.COURSE_ACCESS_ROLES_SUPPORTED_EDIT if only_editable_roles else cs.COURSE_ACCESS_ROLES_SUPPORTED_READ
    course_ids = set()
    for role_name, role_info in roles.items():
        if role_name in all_roles:
            if role_name in cs.COURSE_ACCESS_ROLES_GLOBAL or tenant_id in role_info['tenant_ids_full_access']:
                result['tenant_roles'].append(role_name)
            course_ids.update(role_info['course_limited_access'])

    org_of_courses = get_orgs_of_courses(list(course_ids))['courses']
    orgs_of_tenant = get_course_org_filter_list([tenant_id])['course_org_filter_list']
    for role_name, role_info in roles.items():
        if role_name in all_roles and role_name not in result['tenant_roles']:
            for course_id in role_info['course_limited_access']:
                course_org = org_of_courses[course_id]
                if course_org in orgs_of_tenant:
                    if course_id not in result['course_roles']:
                        result['course_roles'][course_id] = []
                    result['course_roles'][course_id].append(role_name)

    return result


def _clean_course_access_roles_partial(
    caller: get_user_model,
    user: get_user_model,
    tenant_ids: list[int],
    roles_to_restore: List[CourseAccessRole] | None,
) -> None:
    """
    Clean the course access roles by deleting related records of the given tenant IDs and user. This function

    :param caller: The caller user to check the authority
    :type caller: get_user_model
    :param tenant_ids: The tenant IDs to filter on
    :type tenant_ids: list
    :param user: The user to filter on
    :type user: get_user_model
    :param roles_to_restore: The roles to restore
    :type roles_to_restore: list | None
    """
    _delete_course_access_roles(tenant_ids, user)
    if not roles_to_restore:
        return

    creator_orgs = []
    non_creator_roles = []
    for role in roles_to_restore:
        if role.role == cs.COURSE_CREATOR_ROLE_TENANT:
            creator_orgs.append(role.org)
        else:
            non_creator_roles.append(role)

    CourseAccessRole.objects.bulk_create(non_creator_roles)
    add_org_course_creator(caller, user, creator_orgs)


def _group_clean_extract_roles_to_keep(
    tenant_id: int,
    cleaned_course_roles: Dict[str, list],
    user_roles: Dict[str, Any],
    user: get_user_model,
    keep_roles: list,
) -> None:
    """
    Helper to process the user roles by:
    1- Verify that all courses are in the given tenant
    2- Extract the roles to keep from the user_roles['course_roles'] and append them into the keep_roles list
    3- Remove the extracted roles from cleaned_course_roles
    4- Group the course roles by the role name and save that into the user_roles['course_roles']

    :param tenant_id: The tenant ID
    :type tenant_id: int
    :param cleaned_course_roles: The cleaned course roles
    :type cleaned_course_roles: dict
    :param user_roles: The user roles
    :type user_roles: dict
    :param user: The user object
    :type user: get_user_model
    :param keep_roles: The roles to keep
    :type keep_roles: list
    """
    all_course_ids = []
    for role, course_ids in cleaned_course_roles.items():
        all_course_ids.extend(course_ids)
    all_course_ids = list(set(all_course_ids))
    org_of_courses = get_orgs_of_courses(all_course_ids)['courses']
    invalid_org_of_courses = list(set(org_of_courses.values()) - set(
        get_course_org_filter_list([tenant_id])['course_org_filter_list']
    ))
    if invalid_org_of_courses:
        raise FXCodedException(
            code=FXExceptionCodes.ROLE_INVALID_ENTRY,
            message=(
                f'Courses are related to organizations that are not in the tenant ({tenant_id})! '
                f'invalid organizations: {invalid_org_of_courses}'
            ),
        )

    grouped_course_roles: Dict[str, List[str]] = {}
    for course_id, _course_roles in user_roles['course_roles'].items():
        for role in _course_roles:
            if course_id in cleaned_course_roles.get(role, []):
                keep_roles.append(CourseAccessRole(
                    user=user,
                    role=role,
                    org=org_of_courses[course_id],
                    course_id=course_id,
                ))

                cleaned_course_roles[role].remove(course_id)
                if not cleaned_course_roles[role]:
                    del cleaned_course_roles[role]
            else:
                if role not in grouped_course_roles:
                    grouped_course_roles[role] = []
                grouped_course_roles[role].append(course_id)

    user_roles['course_roles'] = grouped_course_roles


def update_course_access_roles(  # pylint: disable=too-many-branches, too-many-statements, too-many-locals
    caller: get_user_model,
    user: get_user_model,
    new_roles_details: Dict[str, Any],
    dry_run: bool = False
) -> Dict[str, str | None]:
    """
    Update the course access roles for the given tenant ID and user. And returns error details if any.

    :param caller: The caller user to check the authority
    :type caller: get_user_model
    :param user: The user to update the roles for
    :type user: get_user_model
    :param new_roles_details: The new roles details
    :type new_roles_details: dict
    :param dry_run: True for dry run, False otherwise
    :type dry_run: bool
    """
    tenant_id = new_roles_details.get('tenant_id', 0)
    tenant_roles = new_roles_details.get('tenant_roles', [])
    course_roles = new_roles_details.get('course_roles', {})
    result: Dict[str, list] = {'failed': []}

    if not user or not isinstance(user, get_user_model()):
        raise ValueError('Invalid user provided!')

    try:
        if not tenant_id or not isinstance(tenant_id, int):
            raise ValueError('No valid tenant ID provided')

        if not isinstance(tenant_roles, list) or not all(isinstance(role, str) for role in tenant_roles):
            raise ValueError('tenant_roles must be a list of strings, or an empty list')
        tenant_roles = list(set(tenant_roles))

        if not isinstance(course_roles, dict):
            raise ValueError('course_roles must be a dictionary of (roles: course_ids)')
        for course_id, roles in course_roles.items():
            if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
                raise ValueError('roles of courses must be a list of strings')
            course_roles[course_id] = list(set(roles))

        cleaned_course_roles: Dict[str, list] = {}
        for course_id, roles in course_roles.items():
            for role in roles:
                if role in tenant_roles:
                    continue
                if role not in cleaned_course_roles:
                    cleaned_course_roles[role] = []
                cleaned_course_roles[role].append(course_id)

        if not cleaned_course_roles and not tenant_roles:
            raise ValueError('Cannot use empty data in roles update! use delete instead')

        cache_refresh_course_access_roles(user.id)
        user_roles = get_tenant_user_roles(tenant_id, user.id, only_editable_roles=True)
        if not user_roles['tenant_roles'] and not user_roles['course_roles']:
            raise FXCodedException(
                code=FXExceptionCodes.ROLE_UPDATE,
                message=f'No roles found to update for user ({user.username}) in tenant ({tenant_id})!',
            )

        keep_roles: List[str] = []
        _group_clean_extract_roles_to_keep(tenant_id, cleaned_course_roles, user_roles, user, keep_roles)

        tenant_orgs = get_course_org_filter_list([tenant_id])['course_org_filter_list']
        for role in set(user_roles['tenant_roles']).intersection(set(tenant_roles)):
            for org in tenant_orgs:
                keep_roles.append(CourseAccessRole(
                    user=user,
                    role=role,
                    org=org,
                    course_id=CourseKeyField.Empty,
                ))
        _temp: set | Dict[str, Any] = set(user_roles['tenant_roles']) - set(tenant_roles)
        tenant_roles = list(set(tenant_roles) - set(user_roles['tenant_roles']))
        user_roles['tenant_roles'] = list(_temp)

        if not dry_run:
            with transaction.atomic():
                _verify_can_delete_course_access_roles_partial(caller, [tenant_id], user_roles, user.username)
                _clean_course_access_roles_partial(caller, user, [tenant_id], keep_roles)

                for role in tenant_roles:
                    result = add_course_access_roles(
                        caller=caller,
                        tenant_ids=[tenant_id],
                        user_keys=[user],
                        role=role,
                        tenant_wide=True,
                        course_ids=None,
                        dry_run=False,
                    )
                    if result['failed']:
                        break

                if not result['failed']:
                    for role, course_ids in cleaned_course_roles.items():
                        result = add_course_access_roles(
                            caller=caller,
                            tenant_ids=[tenant_id],
                            user_keys=[user],
                            role=role,
                            tenant_wide=False,
                            course_ids=course_ids,
                            dry_run=False,
                        )
                        if result['failed']:
                            break

    except ValueError as exc:
        result['failed'].append({
            'reason_code': FXExceptionCodes.INVALID_INPUT.value,
            'reason_message': str(exc),
        })

    except FXCodedException as exc:
        result['failed'].append({
            'reason_code': exc.code,
            'reason_message': str(exc),
        })

    except Exception as exc:  # pylint: disable=broad-except
        result['failed'].append({
            'reason_code': FXExceptionCodes.UNKNOWN_ERROR.value,
            'reason_message': f'{type(exc).__name__}: {str(exc)}',
        })

    if result['failed']:
        return {
            'error_code': result['failed'][0]['reason_code'],
            'error_message': result['failed'][0]['reason_message'],
        }

    if not dry_run:
        cache_refresh_course_access_roles(user.id)

    return {
        'error_code': None,
        'error_message': None,
    }


def _add_missing_signup_source_records(user: get_user_model, orgs: list[str]) -> None:
    """
    Add missing signup source records for the given user for the given orgs.

    :param user: The user to add the records for
    :type user: get_user_model
    :param orgs: The orgs to add the records for
    :type orgs: list
    """
    orgs = list(set(orgs))
    tenants_of_orgs = set()
    for org in orgs:
        tenants_of_orgs.update(get_tenants_by_org(org))
    sites_of_tenants = set(get_tenants_sites(list(tenants_of_orgs)))

    existing_sites = set(UserSignupSource.objects.filter(user=user).values_list('site', flat=True))
    to_add = []
    for site in sites_of_tenants - existing_sites:
        to_add.append(UserSignupSource(user=user, site=site))

    if to_add:
        UserSignupSource.objects.bulk_create(to_add)


def add_missing_signup_source_record(user_id: int, org: str) -> bool:
    """
    Add missing signup source records for the given user for the given orgs.

    :param user_id: The user ID
    :type user_id: int
    :param org: The org to add the records for
    :type org: str
    :return: False if one of the orgs is not valid, True otherwise
    """
    if not get_tenants_by_org(org):
        return False

    _add_missing_signup_source_records(user=get_user_model().objects.get(id=user_id), orgs=[org])
    return True
