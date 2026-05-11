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
        60 * 60,  # 1 hour
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

    # Enable the certificates_count annotation across all queries that expose
    # it. Disabled by default because the underlying subquery is slow.
    settings.FX_CERTIFICATES_COUNT = getattr(
        settings,
        'FX_CERTIFICATES_COUNT',
        False,
    )

    # Enable the completion_rate annotation across all queries that expose it.
    # Cheap arithmetic over certificates_count / enrolled_count, so it only
    # yields meaningful values when FX_CERTIFICATES_COUNT is also enabled.
    settings.FX_COMPLETION_RATE = getattr(
        settings,
        'FX_COMPLETION_RATE',
        True,
    )
