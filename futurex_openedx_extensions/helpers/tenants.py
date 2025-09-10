"""Tenant management helpers"""
from __future__ import annotations

import copy
import json
import logging
from typing import Any, Dict, List
from urllib.parse import urlparse

from common.djangoapps.third_party_auth.models import SAMLProviderConfig
from crum import get_current_request
from django.conf import settings
from django.contrib.sites.models import Site
from django.db import transaction
from django.db.models import Count, OuterRef, QuerySet, Subquery
from eox_tenant.models import Route, TenantConfig

from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers.caching import cache_dict, invalidate_cache
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.extractors import (
    dot_separated_path_extract_all,
    dot_separated_path_force_set_value,
    dot_separated_path_get_value,
    get_first_not_empty_item,
)
from futurex_openedx_extensions.helpers.models import ConfigAccessControl, ConfigMirror, DraftConfig, TenantAsset

logger = logging.getLogger(__name__)


def get_excluded_tenant_ids() -> Dict[int, List[int]]:
    """
    Get dictionary of tenant IDs excluded for bad configuration, along with the reasons of exclusion

    :return: List of tenant IDs to exclude
    :rtype: Dict[int, List[int]]
    """
    def check_bad_config(tenant: TenantConfig) -> List[int]:
        """Check if the tenant has a bad config"""
        reasons = []
        if tenant.routes_count == 0:
            reasons.append(FXExceptionCodes.TENANT_HAS_NO_SITE.value)
        if tenant.routes_count > 1:
            reasons.append(FXExceptionCodes.TENANT_HAS_MORE_THAN_ONE_SITE.value)

        lms_base = tenant.lms_configs.get('LMS_BASE')
        if not lms_base:
            reasons.append(FXExceptionCodes.TENANT_HAS_NO_LMS_BASE.value)

        if lms_base and not reasons:
            lms_base = lms_base.split(':')[-2] if ':' in lms_base else lms_base
            if lms_base != tenant.route_domain:
                reasons.append(FXExceptionCodes.TENANT_LMS_BASE_SITE_MISMATCH.value)

        if not tenant.lms_configs.get('IS_FX_DASHBOARD_ENABLED', True):
            reasons.append(FXExceptionCodes.TENANT_DASHBOARD_NOT_ENABLED.value)

        course_org_filter = tenant.lms_configs.get('course_org_filter')
        if not course_org_filter or (
            isinstance(course_org_filter, list) and not all(isinstance(org, str) for org in course_org_filter)
        ) or (
            isinstance(course_org_filter, str) and not course_org_filter.strip()
        ):
            reasons.append(FXExceptionCodes.TENANT_COURSE_ORG_FILTER_NOT_VALID.value)

        return reasons

    tenants = TenantConfig.objects.annotate(
        routes_count=Count('route'),
    ).annotate(
        route_domain=Subquery(Route.objects.filter(config_id=OuterRef('pk')).values('domain')[:1]),
    )
    return {tenant.id: check_bad_config(tenant) for tenant in tenants if check_bad_config(tenant)}


def get_all_tenants() -> QuerySet:
    """
    Get all tenants in the system that are exposed in the route table, and with a valid config

    Note: a tenant is a TenantConfig object

    :return: QuerySet of all tenants
    :rtype: QuerySet
    """
    return TenantConfig.objects.exclude(id__in=get_excluded_tenant_ids())


def fix_lms_base(domain_name: str) -> str:
    """Fix the LMS base URL"""
    if not domain_name:
        return ''

    lms_root_parts = urlparse(settings.LMS_ROOT_URL)

    if not (domain_name.startswith('http://') or domain_name.startswith('https://')):
        domain_name = f'{lms_root_parts.scheme}://{domain_name}'
    domain_name_parts = urlparse(domain_name)

    port = f':{domain_name_parts.port}' if domain_name_parts.port else ''

    if not port:
        port = f':{lms_root_parts.port}' if lms_root_parts.port else ''

    return f'{domain_name_parts.scheme}://{domain_name_parts.hostname}{port}'


@cache_dict(timeout='FX_CACHE_TIMEOUT_TENANTS_INFO', key_generator_or_name=cs.CACHE_NAME_ALL_TENANTS_INFO)
def get_all_tenants_info() -> Dict[str, str | dict | List[int]]:
    """
    Get all tenants in the system that are exposed in the route table, and with a valid config

    Note: a tenant is a TenantConfig object

    :return: Dictionary of tenant IDs and Sites
    :rtype: Dict[str, Any]
    """
    tenant_ids = list(get_all_tenants().values_list('id', flat=True))
    info = TenantConfig.objects.filter(id__in=tenant_ids).values('id', 'lms_configs')
    sso_sites: Dict[str, List[Dict[str, str]]] = {}
    for sso_site in SAMLProviderConfig.objects.current_set().filter(
        entity_id__in=settings.FX_SSO_INFO, enabled=True,
    ).values('site__domain', 'slug', 'entity_id'):
        site_domain = sso_site['site__domain']
        if site_domain not in sso_sites:
            sso_sites[site_domain] = []
        sso_sites[site_domain].append({
            'slug': sso_site['slug'],
            'entity_id': sso_site['entity_id'],
        })

    tenant_by_site = {}
    for tenant in info:
        lms_base = tenant['lms_configs']['LMS_BASE']
        lms_base_no_port = lms_base.split(':')[0]
        tenant_by_site[lms_base_no_port] = tenant['id']
        tenant_by_site[lms_base] = tenant['id']

    template_tenant = None
    template_assets: Dict[str, str] | None = None
    try:
        template_tenant = TenantConfig.objects.get(external_key=settings.FX_TEMPLATE_TENANT_SITE)
    except TenantConfig.DoesNotExist:
        logger.error('CONFIGURATION ERROR: Template tenant not found! (%s)', settings.FX_TEMPLATE_TENANT_SITE)

    if template_tenant:
        template_assets = {
            asset.slug: asset.file.url for asset in TenantAsset.objects.filter(tenant=template_tenant)
        }

    return {
        'tenant_ids': tenant_ids,
        'sites': {
            tenant['id']: tenant['lms_configs']['LMS_BASE'] for tenant in info
        },
        'info': {
            tenant['id']: {
                'lms_root_url': get_first_not_empty_item([
                    (tenant['lms_configs'].get('LMS_ROOT_URL') or '').strip(),
                    fix_lms_base((tenant['lms_configs']['LMS_BASE']).strip()),
                ], default=''),
                'studio_root_url': settings.CMS_ROOT_URL,
                'platform_name': get_first_not_empty_item([
                    (tenant['lms_configs'].get('PLATFORM_NAME') or '').strip(),
                    (tenant['lms_configs'].get('platform_name') or '').strip(),
                ], default=''),
                'logo_image_url': (tenant['lms_configs'].get('logo_image_url') or '').strip(),
            } for tenant in info
        },
        'default_org_per_tenant': {
            tenant['id']: tenant['lms_configs'].get('DEFAULT_COURSE_ORG', None) for tenant in info
        },
        'tenant_by_site': tenant_by_site,
        'sso_sites': sso_sites,
        'template_tenant': {
            'tenant_id': template_tenant.id if template_tenant else None,
            'tenant_site': settings.FX_TEMPLATE_TENANT_SITE if template_tenant else None,
            'assets': template_assets,
        },
    }


def get_all_tenant_ids() -> List[int]:
    """
    Get list of IDs of all tenants in the system

    :return: List of all tenant IDs
    :rtype: List[int]
    """
    return get_all_tenants_info()['tenant_ids']


def get_tenants_info(tenant_ids: List[int]) -> Dict[int, Any]:
    """
    Get the information for the given tenant IDs

    :param tenant_ids: List of tenant IDs to get the information for
    :type tenant_ids: List[int]
    :return: Dictionary of tenant information
    :rtype: Dict[str, Any]
    """
    all_tenants_info = get_all_tenants_info()
    return {t_id: all_tenants_info['info'].get(t_id) for t_id in tenant_ids}


def get_tenant_site(tenant_id: int) -> str:
    """
    Get the site for a tenant

    :param tenant_id: The tenant ID
    :type tenant_id: int
    :return: The site for the tenant
    :rtype: str
    """
    return get_all_tenants_info()['sites'].get(tenant_id)


@cache_dict(timeout='FX_CACHE_TIMEOUT_TENANTS_INFO', key_generator_or_name=cs.CACHE_NAME_ALL_COURSE_ORG_FILTER_LIST)
def get_all_course_org_filter_list() -> Dict[int, List[str]]:
    """
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
        result[t_id] = sorted(list({org.strip().lower() for org in course_org_filter}))

    return result


def get_course_org_filter_list(tenant_ids: List[int], ignore_invalid_tenant_ids: bool = False) -> Dict[str, Any]:
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
    :param ignore_invalid_tenant_ids: If True, don't raise an error if a tenant ID is invalid. Otherwise, raise an error
        with the list of invalid tenant IDs.
    :type ignore_invalid_tenant_ids: bool
    :return: Dictionary of course org filters and duplicates
    :rtype: Dict[str, List | Dict[str, List[int]]]
    """
    tenant_configs = get_all_course_org_filter_list()

    tenant_ids = tenant_ids or []
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

    if invalid and not ignore_invalid_tenant_ids:
        raise ValueError(f'Invalid tenant IDs: {invalid}')

    return {
        'course_org_filter_list': orgs_list,
        'duplicates': duplicates,
        'invalid': invalid,
    }


@cache_dict(timeout='FX_CACHE_TIMEOUT_TENANTS_INFO', key_generator_or_name=cs.CACHE_NAME_ORG_TO_TENANT_MAP)
def get_org_to_tenant_map() -> Dict[str, List[int]]:
    """
    Get the map of orgs to tenant IDs

    {
        'org1': [1, 2, 3],
        'org2': [2, 3, 4],
        ....
    }

    :return: Dictionary of orgs and their tenant IDs
    :rtype: Dict[str, List[int]]
    """
    tenant_configs = get_all_course_org_filter_list()
    result: Dict[str, Any] = {}
    for t_id, course_org_filter in tenant_configs.items():
        for org in course_org_filter:
            if org not in result:
                result[org] = {t_id}
            else:
                result[org].add(t_id)

    for org, tenant_ids in result.items():
        result[org] = list(tenant_ids)

    return result


def get_tenants_by_org(org: str) -> List[int]:
    """
    Get the tenants that have <org> in their course org filter

    :param org: The org to check
    :type org: str
    :return: List of tenant IDs
    :rtype: List[int]
    """
    return get_org_to_tenant_map().get(org.lower(), [])


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


def get_sso_sites() -> Dict[str, List[Dict[str, int]]]:
    """Get all SSO sites"""
    return get_all_tenants_info()['sso_sites']


def generate_tenant_config(sub_domain: str, platform_name: str) -> dict:
    """
    Generate a tenant configuration by copying the default config and replacing placeholders.

    :param sub_domain: The subdomain to be used for the tenant
    :param platform_name: The platform name to be used for the tenant
    :return: Updated tenant configuration with placeholders replaced
    :rtype: dict
    """
    try:
        default_config = TenantConfig.objects.get(route__domain=settings.FX_TEMPLATE_TENANT_SITE)
        config_lms_dict = json.dumps(default_config.lms_configs)
        config_lms_dict = config_lms_dict.replace('{{platform_name}}', platform_name)
        config_lms_dict = config_lms_dict.replace('{{sub_domain}}', sub_domain)
        return json.loads(config_lms_dict)
    except TenantConfig.DoesNotExist as exc:
        raise FXCodedException(
            code=FXExceptionCodes.TENANT_NOT_FOUND,
            message=f'Default TenantConfig not found! default site: ({settings.FX_TEMPLATE_TENANT_SITE})',
        ) from exc


def create_new_tenant_config(sub_domain: str, platform_name: str) -> TenantConfig:
    """
    Creates a new TenantConfig and associated Route with the provided subdomain and domain name.

    :param sub_domain: The subdomain to be used for the tenant
    :param platform_name: The platform name to be used for the tenant
    :return: The created TenantConfig object
    """
    site_domain = f'{sub_domain}.{settings.FX_TENANTS_BASE_DOMAIN}'
    for model, code, label in [
        (Route, FXExceptionCodes.ROUTE_ALREADY_EXIST, 'Route'),
        (Site, FXExceptionCodes.SITE_ALREADY_EXIST, 'Site'),
    ]:
        if model.objects.filter(domain=site_domain).exists():
            raise FXCodedException(
                code=code,
                message=f'{label} already exists with domain: ({site_domain}).',
            )

    config_data = generate_tenant_config(sub_domain, platform_name)
    config_data.update({'LMS_BASE': site_domain})

    with transaction.atomic():
        tenant_config = TenantConfig.objects.create(
            external_key=sub_domain,
            lms_configs=config_data
        )
        Route.objects.create(
            domain=site_domain,
            config=tenant_config
        )
        Site.objects.create(domain=site_domain, name=site_domain)
        invalidate_cache()
    return tenant_config


@cache_dict(
    timeout='FX_CACHE_TIMEOUT_CONFIG_ACCESS_CONTROL',
    key_generator_or_name=cs.CACHE_NAME_CONFIG_ACCESS_CONTROL,
)
def get_config_access_control() -> Dict[str, Dict[str, Any]]:
    """
    Get the configuration access control dictionary.

    :return: Dictionary of configuration access control
    :rtype: Dict[str, Dict[str, Any]]
    """
    result = {}
    for record in ConfigAccessControl.objects.all():
        result[record.key_name] = {
            'key_type': record.key_type,
            'path': record.path,
            'writable': record.writable,
        }

    return result


def cache_name_tenant_readable_lms_configs(tenant_id: int) -> str:
    """
    Get the cache name for the tenants' readable LMS configs.
    :param tenant_id: The tenant ID
    :type tenant_id: int
    :return: The cache name
    :rtype: str
    """
    return f'{cs.CACHE_NAME_TENANT_READABLE_LMS_CONFIG}_{tenant_id}'


@cache_dict(
    timeout='FX_CACHE_TIMEOUT_CONFIG_ACCESS_CONTROL',
    key_generator_or_name=cache_name_tenant_readable_lms_configs,
)
def get_tenant_readable_lms_config(tenant_id: int) -> dict:
    """
    Retrieve the LMS configuration for a given tenant ID. It only includes keys that are defined in the
    ConfigAccessControl model to avoid loading too much data.

    Note: the function will not return the CONFIG_DRAFT key. Make sure not to use it when draft values are needed.

    :param tenant_id: The ID of the tenant.
    :type tenant_id: int
    :return: The LMS configuration dictionary.
    :rtype: dict
    :raises FXCodedException: If the tenant is not found.
    """
    try:
        tenant = TenantConfig.objects.get(id=tenant_id)
    except TenantConfig.DoesNotExist as exc:
        raise FXCodedException(
            code=FXExceptionCodes.TENANT_NOT_FOUND,
            message=f'Unable to find tenant with id: ({tenant_id})'
        ) from exc

    config_paths = [
        access_control_value['path'] for access_control_key, access_control_value in get_config_access_control().items()
    ]
    unique_paths = sorted(set(config_paths))
    readable_root_paths: List[str] = []
    for path in unique_paths:
        if not any(path == existing or path.startswith(existing + '.') for existing in readable_root_paths):
            readable_root_paths.append(path)

    result: Dict[str, Any] = {}
    lms_configs = tenant.lms_configs
    for root_path in readable_root_paths:
        exists, value = dot_separated_path_get_value(lms_configs, root_path)
        if exists:
            dot_separated_path_force_set_value(result, root_path, value)

    return result


def get_tenant_config(tenant_id: int, keys: List[str], published_only: bool = True) -> Dict[str, Any]:
    """
    Retrieve tenant configuration details for the given tenant ID.

    :param tenant_id: The ID of the tenant.
    :param keys: A list of configuration keys to retrieve.
    :param published_only: Whether to fetch only published configurations. Defaults to True.
    :return: A dictionary containing key values, not permitted keys, and bad keys.
    :raises FXCodedException: If the tenant is not found.
    """
    lms_configs = get_tenant_readable_lms_config(tenant_id)
    config_access_control = get_config_access_control()

    cleaned_keys = {key.strip() for key in keys}

    draft_configs = {}
    if not published_only:
        search_keys = list(cleaned_keys & set(config_access_control.keys()))
        config_paths = [config_access_control[key]['path'] for key in search_keys]
        draft_configs = DraftConfig.loads_into(tenant_id=tenant_id, config_paths=config_paths, dest=lms_configs)

    details: Dict[str, Any] = {
        'values': {},
        'not_permitted': [],
        'bad_keys': [],
        'revision_ids': {},
    }

    for key in list(cleaned_keys):
        if key in config_access_control:
            config = config_access_control[key]
            _, config_value = dot_separated_path_get_value(lms_configs, config['path'])
            details['values'][key] = config_value
            if not published_only:
                details['revision_ids'][key] = draft_configs[config['path']]['revision_id']
        else:
            details['bad_keys'].append(key)

    return details


def get_config_current_request(keys: List[str]) -> dict | None:
    """
    Retrieve tenant configuration details for the given request.

    :param keys: A list of configuration keys to retrieve.
    :type keys: List[str]
    :return: A dictionary containing key values, not permitted keys, and bad keys.
    :rtype: dict | None
    """
    request = get_current_request()
    missing = 'request' if not request else 'site' if not hasattr(request, 'site') else None
    if missing:
        logger.warning('get_config_current_request called without a %s object!', missing)
        return None

    tenant_id = get_all_tenants_info()['tenant_by_site'].get(request.site.domain)
    if not tenant_id:
        logger.warning('get_config_current_request could not find a tenant for site: %s', request.site.domain)
        return None

    theme_preview = request.COOKIES.get('theme-preview', None) or 'no'
    return get_tenant_config(
        tenant_id=tenant_id,
        keys=keys,
        published_only=theme_preview.lower() != 'yes',
    )


def get_fx_theme_css_override() -> Dict[str, Any]:
    """
    Get the CSS override for the FX theme.

    :return: A dictionary containing the CSS override.
    :rtype: Dict[str, str]
    """
    configs = get_config_current_request(keys=['fx_css_override_asset_slug', 'fx_dev_css_enabled'])
    override_slug = configs['values'].get('fx_css_override_asset_slug', '') if configs else None

    assets: Dict[str, Any] = {}
    if override_slug:
        assets = get_all_tenants_info()['template_tenant']['assets'] or {}

    return {
        'css_override_file': assets.get(override_slug, '') if override_slug else '',
        'dev_css_enabled': configs['values'].get('fx_dev_css_enabled', False) is True if configs else False,
    }


def get_draft_tenant_config(tenant_id: int) -> dict:
    """
    Fetches configuration for the specified tenant and returns all draft fields with published and draft values

    :param tenant_id: The ID of the tenant whose draft configuration is to be retrieved.
    :type tenant_id: int
    :return: A dictionary containing updated fields with published and draft values.
    """
    config_access_control = get_config_access_control()
    config_paths = [
        access_control_value['path'] for access_control_value in config_access_control.values()
    ]
    lms_configs = get_tenant_readable_lms_config(tenant_id)
    draft_configs: Dict[str, Any] = {}
    DraftConfig.loads_into(
        tenant_id=tenant_id,
        config_paths=config_paths,
        dest=draft_configs,
    )

    updated_fields = {}
    for access_control_key, access_control_value in config_access_control.items():
        draft_path_exist, draft_value = dot_separated_path_get_value(draft_configs, access_control_value['path'])
        if draft_path_exist:
            _, published_value = dot_separated_path_get_value(lms_configs, access_control_value['path'])
            updated_fields[access_control_key] = {
                'published_value': published_value,
                'draft_value': draft_value,
            }

    return updated_fields


def delete_draft_tenant_config(tenant_id: int) -> None:
    """
    Deletes the draft configuration for the specified tenant.

    :param tenant_id: The ID of the tenant whose draft config needs to be deleted.
    :type tenant_id: int
    """
    DraftConfig.objects.filter(tenant_id=tenant_id).delete()


def update_draft_tenant_config(  # pylint: disable=too-many-arguments
    tenant_id: int,
    config_path: str,
    current_revision_id: int,
    new_value: Any,
    user: Any,
    reset: bool = False,
) -> None:
    """
    Updates 'config_draft.<key_path>' inside the JSON field 'lms_configs' in TenantConfig. The function will also
    update all draft records for parent keys of the specified path.

    :param tenant_id: ID of the tenant.
    :type tenant_id: int
    :param config_path: JSON key path to update.
    :type config_path: str
    :param current_revision_id: Expected current revision ID of the draft config for multi-user-edit protection.
    :type current_revision_id: Any
    :param new_value: New value to be updated.
    :type new_value: Any
    :param user: The user who is updating the config.
    :type user: Any
    :param reset: Whether to reset the value to None.
    :type reset: bool
    :raises FXCodedException: If the tenant does not exist or the update fails.
    """
    config_paths = dot_separated_path_extract_all(config_path)
    config_paths.extend(DraftConfig.objects.filter(
        tenant_id=tenant_id, config_path__startswith=f'{config_path}.',
    ).values_list('config_path', flat=True))

    current_draft: Dict[str, Any] = {}
    draft_configs = DraftConfig.loads_into(
        tenant_id=tenant_id,
        config_paths=config_paths,
        dest=current_draft,
    )

    if reset:
        new_value = None

    dot_separated_path_force_set_value(target_dict=current_draft, dot_separated_path=config_path, value=new_value)
    config_paths = [
        draft_path for draft_path, draft_value in draft_configs.items() if draft_value['revision_id'] != 0
    ]
    config_paths.append(config_path)
    DraftConfig.update_from_dict(
        tenant_id=tenant_id,
        config_paths=config_paths,
        src=current_draft,
        user=user,
        verify_revision_ids={config_path: current_revision_id},
    )


def publish_tenant_config(tenant_id: int) -> None:
    """
    Publish draft config for the given tenant

    :param tenant_id: ID of the tenant.
    :raises FXCodedException: If publish fails.
    """
    config_paths = list(DraftConfig.objects.filter(tenant_id=tenant_id).values_list('config_path', flat=True))
    if not config_paths:
        ConfigMirror.sync_tenant(tenant_id=tenant_id)
        return

    tenant_config = TenantConfig.objects.get(id=tenant_id)
    lms_configs = copy.deepcopy(tenant_config.lms_configs)
    DraftConfig.loads_into(tenant_id=tenant_id, config_paths=config_paths, dest=lms_configs)
    tenant_config.lms_configs = lms_configs
    tenant_config.save()
    delete_draft_tenant_config(tenant_id)
    ConfigMirror.sync_tenant(tenant_id=tenant_id)


def get_accessible_config_keys(
    user_id: int,  # pylint: disable=unused-argument
    tenant_id: int,  # pylint: disable=unused-argument
    writable_fields_filter: bool | None = None,
) -> List[str]:
    """
    TODO: permissions control is not implemented yet. No use for `user_id` and `tenant` parameters for now.

    Get the list of accessible config keys for the given user and tenant.

    :param user_id: The ID of the user.
    :type user_id: int
    :param tenant_id: The ID of the tenant.
    :type tenant_id: int
    :param writable_fields_filter: If True, return only writable fields. If False, return only read-only fields.
        Default is None: return all fields.
    :return: A list of accessible config keys.
    """
    config_access_control = get_config_access_control()

    if writable_fields_filter is not None:
        config_access_control = {
            key: value for key, value in config_access_control.items() if value['writable'] is writable_fields_filter
        }

    return list(config_access_control.keys())
