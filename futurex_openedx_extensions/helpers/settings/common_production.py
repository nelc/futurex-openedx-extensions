"""Common Settings"""
from __future__ import annotations

from typing import Any


def plugin_settings(settings: Any) -> None:
    """plugin settings"""
    # Cache timeout for long living cache
    settings.FX_CACHE_TIMEOUT_COURSE_ACCESS_ROLES = getattr(
        settings,
        'FX_CACHE_TIMEOUT_COURSE_ACCESS_ROLES',
        60 * 30,  # 30 minutes
    )

    # Cache timeout for tenants info
    settings.FX_CACHE_TIMEOUT_TENANTS_INFO = getattr(
        settings,
        'FX_CACHE_TIMEOUT_TENANTS_INFO',
        60 * 60 * 2,  # 2 hours
    )

    settings.FX_CACHE_TIMEOUT_VIEW_ROLES = getattr(
        settings,
        'FX_CACHE_TIMEOUT_VIEW_ROLES',
        60 * 30,  # 30 minutes
    )

    # Exported CSV files directive name
    settings.FX_DASHBOARD_STORAGE_DIR = getattr(
        settings,
        'FX_DASHBOARD_STORAGE_DIR',
        'fx_dashboard'
    )

    # Default Course Effort
    settings.FX_DEFAULT_COURSE_EFFORT = getattr(
        settings,
        'FX_DEFAULT_COURSE_EFFORT',
        12,
    )

    # Minutes limit for export tasks
    settings.FX_TASK_MINUTES_LIMIT = getattr(
        settings,
        'FX_TASK_MINUTES_LIMIT',
        5,
    )

    # Max Period Chunks
    settings.FX_MAX_PERIOD_CHUNKS_MAP = getattr(
        settings,
        'FX_MAX_PERIOD_CHUNKS_MAP',
        {
            'day': 365,
            'month': 12,
            'quarter': 4,
            'year': 1,
        },
    )

    # Nafath Entry Id
    settings.FX_NAFATH_ENTRY_ID = getattr(
        settings,
        'FX_NAFATH_ENTRY_ID',
        '',
    )

    # Nafath Social Auth Provider
    settings.FX_NAFATH_AUTH_PROVIDER = getattr(
        settings,
        'FX_NAFATH_AUTH_PROVIDER',
        'tpa-saml',
    )

    # Default Tenant site
    settings.FX_DEFAULT_TENANT_SITE = getattr(
        settings,
        'FX_DEFAULT_TENANT_SITE',
        'template.futurex.sa',
    )
