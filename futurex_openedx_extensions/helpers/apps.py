"""helpers Django application initialization"""

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

    def ready(self):
        """Connect handlers to send notifications about discussions."""
        from futurex_openedx_extensions.helpers import signals  # pylint: disable=unused-import, import-outside-toplevel
