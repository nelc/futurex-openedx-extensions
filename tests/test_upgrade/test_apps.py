"""Tests for the apps module of the helpers app"""
from futurex_openedx_extensions.upgrade.apps import UpgradeConfig
from futurex_openedx_extensions.upgrade.settings import common_production


def test_app_name():
    """Test that the app name is correct"""
    assert UpgradeConfig.name == 'futurex_openedx_extensions.upgrade'


def test_common_production_plugin_settings():
    """Verify settings contain the method plugin_settings"""
    assert hasattr(common_production, 'plugin_settings'), 'settings is missing the method plugin_settings!'
    common_production.plugin_settings({})
