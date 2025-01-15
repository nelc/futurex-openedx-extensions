"""helpers Django application initialization"""
from __future__ import annotations

from bridgekeeper import perms
from django.apps import AppConfig


class HelpersConfig(AppConfig):
    """Configuration for the helpers Django application"""

    name = 'futurex_openedx_extensions.helpers'
    label = 'fx_helpers'

    # pylint: disable=duplicate-code
    plugin_app = {
        'settings_config': {
            'lms.djangoapp': {
                'production': {
                    'relative_path': 'settings.common_production',
                },
            },
            'cms.djangoapp': {
                'production': {
                    'relative_path': 'settings.common_production',
                },
            },
        },
    }
    # pylint: enable=duplicate-code

    def ready(self) -> None:
        """Connect handlers to send notifications about discussions."""
        from lms.djangoapps.course_home_api.permissions import (  # pylint: disable=import-outside-toplevel
            CAN_MASQUARADE_LEARNER_PROGRESS,
        )
        from lms.djangoapps.courseware.rules import (  # pylint: disable=import-outside-toplevel
            HasAccessRule,
            HasRolesRule,
        )

        from futurex_openedx_extensions.helpers import \
            custom_roles  # pylint: disable=unused-import, import-outside-toplevel
        from futurex_openedx_extensions.helpers import \
            monkey_patches  # pylint: disable=unused-import, import-outside-toplevel
        from futurex_openedx_extensions.helpers import signals  # pylint: disable=unused-import, import-outside-toplevel
        if CAN_MASQUARADE_LEARNER_PROGRESS in perms:
            del perms[CAN_MASQUARADE_LEARNER_PROGRESS]
        perms[CAN_MASQUARADE_LEARNER_PROGRESS] = HasAccessRule('staff') | HasRolesRule('data_researcher')
