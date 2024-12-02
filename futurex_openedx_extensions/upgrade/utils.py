"""Utilit functions for upgrade tasks."""
from __future__ import annotations

import logging

from django.conf import settings

log = logging.getLogger(__name__)

FX_EDX_PLATFORM_VERSION_PALM = 'palm'
FX_EDX_PLATFORM_VERSION_REDWOOD = 'redwood'

FX_DASHBOARD_DEFAULT_EDX_PLATFORM_VERSION = FX_EDX_PLATFORM_VERSION_PALM
FX_DASHBOARD_SUPPORTED_EDX_PLATFORM_VERSION = [FX_EDX_PLATFORM_VERSION_PALM, FX_EDX_PLATFORM_VERSION_REDWOOD]


def get_default_version() -> str:
    """Get the default version of the edx-platform."""
    return FX_DASHBOARD_DEFAULT_EDX_PLATFORM_VERSION


def get_current_version() -> str:
    """Get the current version of the edx-platform."""
    default = get_default_version()
    result = getattr(settings, 'FX_EDX_PLATFORM_VERSION', default) or default
    if result not in FX_DASHBOARD_SUPPORTED_EDX_PLATFORM_VERSION:
        log.error(
            'FX_EDX_PLATFORM_VERSION was set to (%s) which is not a supported version. '
            'Defaulting to (%s).', result, default,
        )
        result = default
    return result


FX_CURRENT_EDX_PLATFORM_VERSION = get_current_version()
