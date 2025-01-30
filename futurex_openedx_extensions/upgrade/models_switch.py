"""Models switch for different Open edX platform versions."""
from futurex_openedx_extensions.upgrade.utils import (
    FX_CURRENT_EDX_PLATFORM_VERSION,
    FX_EDX_PLATFORM_VERSION_REDWOOD,
    FX_EDX_PLATFORM_VERSION_SUMAC,
)

if FX_CURRENT_EDX_PLATFORM_VERSION == FX_EDX_PLATFORM_VERSION_REDWOOD:
    # from futurex_openedx_extensions.upgrade.releases.redwood.models import .....
    pass  # nothing changed that we're using in this package

elif FX_CURRENT_EDX_PLATFORM_VERSION == FX_EDX_PLATFORM_VERSION_SUMAC:
    # from futurex_openedx_extensions.upgrade.releases.sumac.models import .....
    pass  # nothing changed that we're using in this package
