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
