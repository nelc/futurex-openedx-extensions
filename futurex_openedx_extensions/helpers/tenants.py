"""Tenant management helpers"""
from __future__ import annotations

from typing import Any, Dict, List

from common.djangoapps.student.models import CourseAccessRole, CourseEnrollment
from django.contrib.auth import get_user_model
from django.db.models import Exists, OuterRef
from django.db.models.query import Q, QuerySet
from eox_tenant.models import Route, TenantConfig
from rest_framework.request import Request

from futurex_openedx_extensions.helpers.converters import error_details_to_dictionary, ids_string_to_list
from futurex_openedx_extensions.helpers.querysets import get_has_site_login_queryset

TENANT_LIMITED_ADMIN_ROLES = ['org_course_creator_group']


def get_excluded_tenant_ids() -> List[int]:
    """
    Get list of IDs of tenants excluded because they are not exposed in the route table, or have empty configs

    :return: List of tenant IDs to exclude
    :rtype: List[int]
    """
    def bad_config(tenant):
        """Check if the tenant has a bad config"""
        return (
            tenant.no_route or
            not tenant.lms_configs.get('course_org_filter') or (
                not tenant.lms_configs.get('SITE_NAME') and
                not tenant.lms_configs.get('LMS_BASE')
            )
        )
    tenants = TenantConfig.objects.annotate(
        no_route=~Exists(Route.objects.filter(config_id=OuterRef('pk')))
    )
    return [tenant.id for tenant in tenants if bad_config(tenant)]


def get_all_tenants() -> QuerySet:
    """
    Get all tenants in the system that are exposed in the route table, and with a valid config

    Note: a tenant is a TenantConfig object

    :return: QuerySet of all tenants
    :rtype: QuerySet
    """
    return TenantConfig.objects.exclude(id__in=get_excluded_tenant_ids())


def get_all_tenants_info() -> Dict[str, Any]:
    """
    TODO: Cache the result of this function
    Get all tenants in the system that are exposed in the route table, and with a valid config

    Note: a tenant is a TenantConfig object

    :return: Dictionary of tenant IDs and Sites
    :rtype: Dict[str, Any]
    """
    tenant_ids = list(get_all_tenants().values_list('id', flat=True))
    info = TenantConfig.objects.filter(id__in=tenant_ids).values('id', 'route__domain')
    return {
        'tenant_ids': tenant_ids,
        'sites': {
            tenant['id']: tenant['route__domain'] for tenant in info
        }
    }


def get_all_tenant_ids() -> List[int]:
    """
    Get list of IDs of all tenants in the system

    :return: List of all tenant IDs
    :rtype: List[int]
    """
    return get_all_tenants_info()['tenant_ids']


def get_tenant_site(tenant_id: int) -> str:
    """
    Get the site for a tenant

    :param tenant_id: The tenant ID
    :type tenant_id: int
    :return: The site for the tenant
    :rtype: str
    """
    return get_all_tenants_info()['sites'].get(tenant_id)


def get_all_course_org_filter_list() -> Dict[int, List[str]]:
    """
    TODO: Cache the result of this function
    Get all course org filters for all tenants.

    :return: Dictionary of tenant IDs and their course org filters
    :rtype: Dict[int, List[str]]
    """
    tenant_configs = get_all_tenants().values_list('id', 'lms_configs')

    result = {}
    for t_id, config in tenant_configs:
        course_org_filter = config.get('course_org_filter', [])
        if isinstance(course_org_filter, str):
            course_org_filter = [course_org_filter]
        result[t_id] = course_org_filter

    return result


def get_course_org_filter_list(tenant_ids: List[int]) -> Dict[str, List | Dict[str, List[int]]]:
    """
    Get the filters to use for course orgs.

    returns two information:
    {
        'course_org_filter_list': List of course org filters,
        'duplicates': Dictionary of tenant IDs and their duplicates,
        'invalid': List of invalid tenant IDs,
    }

    duplicates looks like this:
    {
        1: [2, 3],
        2: [1, 3],
        3: [1, 2],
        4: [],
        5: [],
    }

    :param tenant_ids: List of tenant IDs to get the filters for
    :type tenant_ids: List[int]
    :return: Dictionary of course org filters and duplicates
    :rtype: Dict[str, List | Dict[str, List[int]]]
    """
    tenant_configs = get_all_course_org_filter_list()

    orgs_list = []
    duplicate_trace = {}
    duplicates = {}
    invalid = []
    for tenant_id in tenant_ids:
        course_org_filter = tenant_configs.get(tenant_id, [])
        if not course_org_filter:
            invalid.append(tenant_id)
            continue

        for org in course_org_filter:
            if org not in orgs_list:
                orgs_list.append(org)
                duplicate_trace[org] = [tenant_id]
            else:
                for other_id in duplicate_trace[org]:
                    if other_id not in duplicates:
                        duplicates[other_id] = [tenant_id]
                    else:
                        duplicates[other_id].append(tenant_id)
                duplicates[tenant_id] = list(duplicate_trace[org])
                duplicate_trace[org].append(tenant_id)

    return {
        'course_org_filter_list': orgs_list,
        'duplicates': duplicates,
        'invalid': invalid,
    }


def get_accessible_tenant_ids(user: get_user_model()) -> List[int]:
    """
    Get the tenants that the user has access to.

    :param user: The user to check.
    :type user: get_user_model()
    :return: List of accessible tenant IDs
    :rtype: List[int]
    """
    if not user:
        return []
    if user.is_superuser or user.is_staff:
        return get_all_tenant_ids()

    course_org_filter_list = get_all_course_org_filter_list()
    accessible_orgs = CourseAccessRole.objects.filter(
        user_id=user.id,
        role__in=TENANT_LIMITED_ADMIN_ROLES,
    ).values_list('org', flat=True).distinct()

    return [t_id for t_id, course_org_filter in course_org_filter_list.items() if any(
        org in course_org_filter for org in accessible_orgs
    )]


def check_tenant_access(user: get_user_model(), tenant_ids_string: str) -> tuple[bool, dict]:
    """
    Check if the user has access to the provided tenant IDs

    :param user: The user to check.
    :type user: get_user_model()
    :param tenant_ids_string: Comma-separated string of tenant IDs
    :type tenant_ids_string: str
    :return: Tuple of a boolean indicating if the user has access, and a dictionary of error details if any
    """
    try:
        tenant_ids = set(ids_string_to_list(tenant_ids_string))
    except ValueError as exc:
        return False, error_details_to_dictionary(
            reason="Invalid tenant IDs provided. It must be a comma-separated list of integers",
            error=str(exc)
        )

    wrong_tenant_ids = tenant_ids - set(get_all_tenant_ids())
    if wrong_tenant_ids:
        return False, error_details_to_dictionary(
            reason="Invalid tenant IDs provided",
            tenant_ids=list(wrong_tenant_ids)
        )

    inaccessible_tenants = tenant_ids - set(get_accessible_tenant_ids(user))
    if inaccessible_tenants:
        return False, error_details_to_dictionary(
            reason="User does not have access to these tenants",
            tenant_ids=list(inaccessible_tenants),
        )

    return True, {}


def get_tenants_by_org(org: str) -> List[int]:
    """
    Get the tenants that have <org> in their course org filter

    :param org: The org to check
    :type org: str
    :return: List of tenant IDs
    :rtype: List[int]
    """
    tenant_configs = get_all_course_org_filter_list()
    return [t_id for t_id, course_org_filter in tenant_configs.items() if org in course_org_filter]


def get_selected_tenants(request: Request) -> List[int]:
    """
    Get the tenant IDs from the request

    :param request: The request
    :type request: Request
    :return: List of tenant IDs
    :rtype: List[int]
    """
    tenant_ids = request.query_params.get('tenant_ids')
    if tenant_ids is None:
        return get_accessible_tenant_ids(request.user)
    return ids_string_to_list(tenant_ids)


def get_tenants_sites(tenant_ids: List[int]) -> List[str]:
    """
    Get the sites for the given tenant IDs

    :param tenant_ids: List of tenant IDs
    :type tenant_ids: List[int]
    :return: List of sites
    :rtype: List[str]
    """
    if not tenant_ids:
        return []

    tenant_sites = []
    for tenant_id in tenant_ids:
        if site := get_tenant_site(tenant_id):
            tenant_sites.append(site)
    return tenant_sites


def get_user_id_from_username_tenants(username: str, tenant_ids: List[int]) -> int:
    """
    Check if the given username is in any of the given tenants. Returns the user ID if found, and zero otherwise.

    :param username: The username to check
    :type username: str
    :param tenant_ids: List of tenant IDs to check
    :type tenant_ids: List[int]
    :return: The user ID if found, and zero otherwise
    :rtype: int
    """
    if not tenant_ids or not username:
        return 0

    course_org_filter_list = get_course_org_filter_list(tenant_ids)['course_org_filter_list']
    tenant_sites = get_tenants_sites(tenant_ids)

    user_id = get_user_model().objects.filter(username=username).annotate(
        courseenrollment_count=Exists(
            CourseEnrollment.objects.filter(
                user_id=OuterRef('id'),
                course__org__in=course_org_filter_list,
            )
        )
    ).annotate(
        has_site_login=get_has_site_login_queryset(tenant_sites)
    ).filter(Q(courseenrollment_count=True) | Q(has_site_login=True)).values_list('id', flat=True)

    return user_id[0] if user_id else 0
