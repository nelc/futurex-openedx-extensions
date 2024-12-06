"""Models switch for different Open edX platform versions."""
from futurex_openedx_extensions.upgrade.utils import (
    FX_CURRENT_EDX_PLATFORM_VERSION,
    FX_EDX_PLATFORM_VERSION_PALM,
    FX_EDX_PLATFORM_VERSION_REDWOOD,
)

if FX_CURRENT_EDX_PLATFORM_VERSION == FX_EDX_PLATFORM_VERSION_PALM:
    from futurex_openedx_extensions.upgrade.releases.palm.models import (  # pylint: disable=unused-import
        CourseAccessRole,
        CourseEnrollment,
        SocialLink,
        UserProfile,
        UserSignupSource,
        get_user_by_username_or_email,
    )

elif FX_CURRENT_EDX_PLATFORM_VERSION == FX_EDX_PLATFORM_VERSION_REDWOOD:
    from futurex_openedx_extensions.upgrade.releases.redwood.models import (
        CourseAccessRole,
        CourseEnrollment,
        SocialLink,
        UserProfile,
        UserSignupSource,
        get_user_by_username_or_email,
    )
