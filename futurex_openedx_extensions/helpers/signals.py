"""Signals for the futurex_openedx_extensions app"""
from __future__ import annotations

from typing import Any

from common.djangoapps.student.models import CourseAccessRole
from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers.models import ViewAllowedRoles


@receiver(post_save, sender=CourseAccessRole)
def refresh_course_access_role_cache_on_save(
    sender: Any, instance: CourseAccessRole, **kwargs: Any,  # pylint: disable=unused-argument
) -> None:
    """Receiver to refresh the course access role cache when a course access role is saved"""
    cache.delete(cs.CACHE_NAME_ALL_COURSE_ACCESS_ROLES)


@receiver(post_delete, sender=CourseAccessRole)
def refresh_course_access_role_cache_on_delete(
    sender: Any, instance: CourseAccessRole, **kwargs: Any,  # pylint: disable=unused-argument
) -> None:
    """Receiver to refresh the course access role cache when a course access role is deleted"""
    cache.delete(cs.CACHE_NAME_ALL_COURSE_ACCESS_ROLES)


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
