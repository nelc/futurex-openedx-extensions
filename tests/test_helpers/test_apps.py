"""Tests for the apps module of the helpers app"""
import copy

import pytest

from futurex_openedx_extensions.dashboard.settings import common_production
from futurex_openedx_extensions.helpers.apps import HelpersConfig

dashboard_default_settings = [
    ('FX_CACHE_TIMEOUT_TENANTS_INFO', 60 * 60 * 2),  # 2 hours
]


def test_app_name():
    """Test that the app name is correct"""
    assert HelpersConfig.name == 'futurex_openedx_extensions.helpers'


def test_common_production_plugin_settings():
    """Verify settings contain the method plugin_settings"""
    assert hasattr(common_production, 'plugin_settings'), 'settings is missing the method plugin_settings!'


@pytest.mark.parametrize('setting_key, default_value', dashboard_default_settings)
def test_common_production_plugin_settings_new_attributes(settings, setting_key, default_value):
    """Verify that the plugin's settings contain the new settings"""
    settings = copy.deepcopy(settings)
    delattr(settings, setting_key)
    assert not hasattr(settings, setting_key), 'whaaaat?!!!'

    common_production.plugin_settings(settings)
    assert hasattr(settings, setting_key), f'Missing settings ({setting_key})!'
    assert getattr(settings, setting_key) == default_value, f'Unexpected settings value ({setting_key})!'


@pytest.mark.parametrize('setting_key, default_value', dashboard_default_settings)
def test_common_production_plugin_settings_explicit(settings, setting_key, default_value):
    """Verify that the plugin's settings read from env"""
    settings = copy.deepcopy(settings)

    new_value = getattr(settings, setting_key)
    assert new_value != default_value, 'Bad test data, default value is the same as the new value!'
    common_production.plugin_settings(settings)
    assert hasattr(settings, setting_key), f'Missing settings ({setting_key})!'
    assert getattr(settings, setting_key) == new_value, f'settings ({setting_key}) did not read from env correctly!'


def test_set_default_throttle_rates(settings):
    """Verify that the plugin's settings set the default throttle rates"""
    settings = copy.deepcopy(settings)
    settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {}
    throttle_rates = settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']
    assert 'fx_anonymous_data_retrieve' not in throttle_rates, 'fx_anonymous_data_retrieve already exists!'

    common_production.plugin_settings(settings)
    throttle_rates = settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']
    assert 'fx_anonymous_data_retrieve' in throttle_rates, 'fx_anonymous_data_retrieve was not set!'
    assert throttle_rates['fx_anonymous_data_retrieve'] == '5/hour', 'fx_anonymous_data_retrieve was not set!'
