"""upgrade Django application initialization"""
from __future__ import annotations

from django.apps import AppConfig


class UpgradeConfig(AppConfig):
    """Configuration for the helpers Django application"""

    name = 'futurex_openedx_extensions.upgrade'
    label = 'fx_upgrade'

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
