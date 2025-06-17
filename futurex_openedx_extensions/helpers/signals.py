"""Signals for the futurex_openedx_extensions app"""
from __future__ import annotations

from typing import Any

from common.djangoapps.student.models import CourseAccessRole
from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers.caching import invalidate_cache
from futurex_openedx_extensions.helpers.models import ConfigAccessControl, TenantAsset, ViewAllowedRoles
from futurex_openedx_extensions.helpers.roles import (
    add_missing_signup_source_record,
    cache_name_user_course_access_roles,
)
from futurex_openedx_extensions.helpers.tenants import invalidate_tenant_readable_lms_configs


@receiver(post_save, sender=CourseAccessRole)
def refresh_course_access_role_cache_on_save(
    sender: Any, instance: CourseAccessRole, **kwargs: Any,  # pylint: disable=unused-argument
) -> None:
    """Receiver to refresh the course access role cache when a course access role is saved"""
    if instance.org:
        add_missing_signup_source_record(instance.user_id, instance.org)
    cache_name = cache_name_user_course_access_roles(instance.user_id)
    cache.delete(cache_name)


@receiver(post_delete, sender=CourseAccessRole)
def refresh_course_access_role_cache_on_delete(
    sender: Any, instance: CourseAccessRole, **kwargs: Any,  # pylint: disable=unused-argument
) -> None:
    """Receiver to refresh the course access role cache when a course access role is deleted"""
    cache_name = cache_name_user_course_access_roles(instance.user_id)
    cache.delete(cache_name)


@receiver(post_save, sender=ViewAllowedRoles)
def refresh_view_allowed_roles_cache_on_save(
    sender: Any, instance: ViewAllowedRoles, **kwargs: Any,  # pylint: disable=unused-argument
) -> None:
    """Receiver to refresh the view allowed roles cache when a view allowed role is saved"""
    cache.delete(cs.CACHE_NAME_ALL_VIEW_ROLES)


@receiver(post_delete, sender=ViewAllowedRoles)
def refresh_view_allowed_roles_cache_on_delete(
    sender: Any, instance: ViewAllowedRoles, **kwargs: Any,  # pylint: disable=unused-argument
) -> None:
    """Receiver to refresh the view allowed roles cache when a view allowed role is deleted"""
    cache.delete(cs.CACHE_NAME_ALL_VIEW_ROLES)


@receiver(post_save, sender=ConfigAccessControl)
def refresh_config_access_control_cache_on_save(
    sender: Any, instance: ConfigAccessControl, **kwargs: Any,  # pylint: disable=unused-argument
) -> None:
    """Receiver to refresh the config access control cache when a config access control is saved"""
    cache.delete(cs.CACHE_NAME_CONFIG_ACCESS_CONTROL)
    invalidate_tenant_readable_lms_configs(tenant_id=0)


@receiver(post_delete, sender=ConfigAccessControl)
def refresh_config_access_control_cache_on_delete(
    sender: Any, instance: ConfigAccessControl, **kwargs: Any,  # pylint: disable=unused-argument
) -> None:
    """Receiver to refresh the config access control cache when a config access control is deleted"""
    cache.delete(cs.CACHE_NAME_CONFIG_ACCESS_CONTROL)
    invalidate_tenant_readable_lms_configs(tenant_id=0)


@receiver(post_save, sender=TenantAsset)
def refresh_tenant_info_cache_on_save_template_asset(
    sender: Any, instance: TenantAsset, **kwargs: Any,  # pylint: disable=unused-argument
) -> None:
    """Receiver to refresh the tenant info cache when a tenant asset is saved"""
    invalidate_cache()


@receiver(post_delete, sender=TenantAsset)
def refresh_tenant_info_cache_on_delete_template_asset(
    sender: Any, instance: TenantAsset, **kwargs: Any,  # pylint: disable=unused-argument
) -> None:
    """Receiver to refresh the tenant info cache when a tenant asset is deleted"""
    invalidate_cache()
