"""Common Settings"""
from __future__ import annotations

from typing import Any


def plugin_settings(settings: Any) -> None:
    """plugin settings"""
    # Cache timeout for live statistics per tenant
    settings.FX_CACHE_TIMEOUT_LIVE_STATISTICS_PER_TENANT = getattr(
        settings,
        'FX_CACHE_TIMEOUT_LIVE_STATISTICS_PER_TENANT',
        60 * 60 * 2,  # 2 hours
    )

    # Cache timeout for course ratings per tenant
    settings.FX_CACHE_TIMEOUT_COURSES_RATINGS = getattr(
        settings,
        'FX_CACHE_TIMEOUT_COURSES_RATINGS',
        60 * 15,  # 15 minutes
    )

    settings.FX_DISABLE_CONFIG_VALIDATIONS = getattr(
        settings,
        'FX_DISABLE_CONFIG_VALIDATIONS',
        False,
    )

    settings.FX_ALLOWED_COURSE_LANGUAGE_CODES = getattr(
        settings,
        'FX_ALLOWED_COURSE_LANGUAGE_CODES',
        ['en', 'ar', 'fr'],
    )
