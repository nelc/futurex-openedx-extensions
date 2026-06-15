"""Models switch for different Open edX platform versions."""
from futurex_openedx_extensions.upgrade.utils import (
    FX_CURRENT_EDX_PLATFORM_VERSION,
    FX_EDX_PLATFORM_VERSION_TEAK,
)

if FX_CURRENT_EDX_PLATFORM_VERSION == FX_EDX_PLATFORM_VERSION_TEAK:
    # from futurex_openedx_extensions.upgrade.releases.teak.models import .....
    pass  # nothing changed that we're using in this package
