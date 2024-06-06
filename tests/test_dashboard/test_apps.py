"""Tests for the apps module of the helpers app"""
# pylint: disable=duplicate-code
from futurex_openedx_extensions.dashboard.apps import DashboardConfig
from futurex_openedx_extensions.dashboard.settings import common_production


def test_app_name():
    """Test that the app name is correct"""
    assert DashboardConfig.name == 'futurex_openedx_extensions.dashboard'


def test_app_config():
    """Verify that the app is compatible with edx-platform plugins"""
    assert DashboardConfig.plugin_app == {
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
    }, 'The app is not compatible with edx-platform plugins!'


def test_common_production_plugin_settings():
    """Verify that used settings contain the method plugin_settings"""
    assert hasattr(common_production, 'plugin_settings'), 'settings is missing the method plugin_settings!'
