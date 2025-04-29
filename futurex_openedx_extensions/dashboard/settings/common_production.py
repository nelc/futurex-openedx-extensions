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
