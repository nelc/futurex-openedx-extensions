"""Tests for the apps module of the helpers app"""
# pylint: disable=duplicate-code
import copy

import pytest

from futurex_openedx_extensions.dashboard.apps import DashboardConfig
from futurex_openedx_extensions.dashboard.settings import common_production

helpers_default_settings = [
    ('FX_CACHE_TIMEOUT_LIVE_STATISTICS_PER_TENANT', 60 * 60 * 2),  # 2 hours
    ('FX_ALLOWED_COURSE_LANGUAGE_CODES', ['en', 'ar', 'fr']),
]


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


@pytest.mark.parametrize('setting_key, default_value', helpers_default_settings)
def test_common_production_plugin_settings_new_attributes(settings, setting_key, default_value):
    """Verify that the plugin's settings contain the new settings"""
    settings = copy.deepcopy(settings)
    delattr(settings, setting_key)
    assert not hasattr(settings, setting_key), 'whaaaat?!!!'

    common_production.plugin_settings(settings)
    assert hasattr(settings, setting_key), f'Missing settings ({setting_key})!'
    assert getattr(settings, setting_key) == default_value, f'Unexpected settings value ({setting_key})!'


@pytest.mark.parametrize('setting_key, default_value', helpers_default_settings)
def test_common_production_plugin_settings_explicit(settings, setting_key, default_value):
    """Verify that the plugin's settings read from env"""
    settings = copy.deepcopy(settings)

    new_value = getattr(settings, setting_key)
    assert new_value != default_value, \
        f'Bad data, make sure that the value of {setting_key} in test_settings.py is different from the default value!'
    common_production.plugin_settings(settings)
    assert hasattr(settings, setting_key), f'Missing settings ({setting_key})!'
    assert getattr(settings, setting_key) == new_value, f'settings ({setting_key}) did not read from env correctly!'


def test_common_production_plugin_settings():
    """Verify that used settings contain the method plugin_settings"""
    assert hasattr(common_production, 'plugin_settings'), 'settings is missing the method plugin_settings!'
