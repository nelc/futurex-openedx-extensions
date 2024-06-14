"""Common Settings"""


def plugin_settings(settings):
    """
    plugin settings
    """
    # Cache timeout for tenants info
    settings.FX_CACHE_TIMEOUT_TENANTS_INFO = getattr(
        settings,
        "FX_CACHE_TIMEOUT_TENANTS_INFO",
        60 * 60 * 2,  # 2 hours
    )

    settings.FX_RATE_LIMIT_ANONYMOUS_DATA_RETRIEVE = getattr(
        settings,
        "FX_RATE_LIMIT_ANONYMOUS_DATA_RETRIEVE",
        "1/minute",
    )

    if settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].get("fx_anonymous_data_retrieve") is None:
        settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["fx_anonymous_data_retrieve"] = "5/hour"
