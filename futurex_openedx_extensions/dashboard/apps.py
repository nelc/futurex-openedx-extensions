"""dashbord Django application initialization"""

from django.apps import AppConfig


class DashboardConfig(AppConfig):
    """Configuration for the dashboard Django application"""

    name = 'futurex_openedx_extensions.dashboard'

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
        'url_config': {
            'lms.djangoapp': {
                'namespace': 'fx_dashboard',
            },
        },
    }
