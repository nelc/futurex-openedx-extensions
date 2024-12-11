"""Tests for the utils module of the upgrade app"""
from unittest.mock import patch

import pytest
from django.conf import settings
from django.test import override_settings

from futurex_openedx_extensions.upgrade import utils


def test_default_version_and_supported_versions():
    """Verify versions definitions"""
    assert isinstance(utils.FX_DASHBOARD_SUPPORTED_EDX_PLATFORM_VERSION, list)
    assert utils.FX_DASHBOARD_SUPPORTED_EDX_PLATFORM_VERSION
    assert isinstance(utils.FX_DASHBOARD_DEFAULT_EDX_PLATFORM_VERSION, str) and len(
        utils.FX_DASHBOARD_DEFAULT_EDX_PLATFORM_VERSION
    ) > 2
    assert all(
        isinstance(version, str) and len(version) > 2 for version in utils.FX_DASHBOARD_SUPPORTED_EDX_PLATFORM_VERSION
    )


def test_default_version_must_be_in_supported_versions():
    """Test that the default version is in the supported versions"""
    assert utils.FX_DASHBOARD_DEFAULT_EDX_PLATFORM_VERSION in utils.FX_DASHBOARD_SUPPORTED_EDX_PLATFORM_VERSION


@patch('futurex_openedx_extensions.upgrade.utils.FX_DASHBOARD_DEFAULT_EDX_PLATFORM_VERSION', 'lolipop')
def test_get_default_version():
    """Verify that the default version is returned"""
    assert utils.get_default_version() == 'lolipop'


@pytest.mark.parametrize('in_settings, test_in_log, expected_result', [
    ({'FX_EDX_PLATFORM_VERSION': None}, None, 'lolipop'),
    ({'FX_EDX_PLATFORM_VERSION': ''}, None, 'lolipop'),
    ({'FX_EDX_PLATFORM_VERSION': 'lolipop'}, None, 'lolipop'),
    ({'FX_EDX_PLATFORM_VERSION': 'candy'}, None, 'candy'),
    ({'FX_EDX_PLATFORM_VERSION': 'unsupported'}, 'unsupported', 'lolipop'),
])
@patch('futurex_openedx_extensions.upgrade.utils.FX_DASHBOARD_DEFAULT_EDX_PLATFORM_VERSION', 'lolipop')
@patch('futurex_openedx_extensions.upgrade.utils.FX_DASHBOARD_SUPPORTED_EDX_PLATFORM_VERSION', ['lolipop', 'candy'])
def test_get_current_version(in_settings, test_in_log, expected_result, caplog):
    """Verify that the current version is returned"""
    assert hasattr(settings, 'FX_EDX_PLATFORM_VERSION')

    with override_settings(**in_settings):
        assert utils.get_current_version() == expected_result
    if test_in_log:
        assert f'FX_EDX_PLATFORM_VERSION was set to ({test_in_log}) which is not a supported version. ' \
               f'Defaulting to ({expected_result}).' in caplog.text
    else:
        assert 'FX_EDX_PLATFORM_VERSION was set to' not in caplog.text


@patch('futurex_openedx_extensions.upgrade.utils.FX_DASHBOARD_DEFAULT_EDX_PLATFORM_VERSION', 'lolipop')
@patch('futurex_openedx_extensions.upgrade.utils.FX_DASHBOARD_SUPPORTED_EDX_PLATFORM_VERSION', ['lolipop', 'candy'])
def test_get_current_version_missing_settings():
    """Verify that the current version is returned from the default when the settings are missing"""
    assert hasattr(settings, 'FX_EDX_PLATFORM_VERSION')
    del settings.FX_EDX_PLATFORM_VERSION
    assert not hasattr(settings, 'FX_EDX_PLATFORM_VERSION')

    assert utils.get_current_version() == 'lolipop'
