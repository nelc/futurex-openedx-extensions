"""Utilit functions for upgrade tasks."""
from __future__ import annotations

import logging

from openedx.core.release import RELEASE_LINE

log = logging.getLogger(__name__)

FX_EDX_PLATFORM_VERSION_PALM = 'palm'
FX_EDX_PLATFORM_VERSION_REDWOOD = 'redwood'

FX_DASHBOARD_SUPPORTED_EDX_PLATFORM_VERSION = [FX_EDX_PLATFORM_VERSION_PALM, FX_EDX_PLATFORM_VERSION_REDWOOD]


def get_edx_platform_release() -> str:
    """Get the edx-platform release."""
    return RELEASE_LINE


def get_current_version() -> str:
    """Get the current version of the edx-platform."""
    result = get_edx_platform_release()
    if result not in FX_DASHBOARD_SUPPORTED_EDX_PLATFORM_VERSION:
        if result < FX_EDX_PLATFORM_VERSION_PALM and result != 'master':
            default = FX_EDX_PLATFORM_VERSION_PALM
        else:
            default = FX_EDX_PLATFORM_VERSION_REDWOOD
        log.error(
            'edx-platform release line is (%s) which is not a supported version. '
            'Defaulting to (%s).', result, default,
        )
        result = default
    return result


FX_CURRENT_EDX_PLATFORM_VERSION = get_current_version()
