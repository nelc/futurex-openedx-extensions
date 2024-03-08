"""Tests for the apps module of the helpers app"""
from futurex_openedx_extensions.helpers.apps import HelpersConfig


def test_app_name():
    """Test that the app name is correct"""
    assert HelpersConfig.name == 'futurex_openedx_extensions.helpers'
