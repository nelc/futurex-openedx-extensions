"""Tests for clickhouse helper functions."""
from unittest.mock import Mock, patch

import pytest

import futurex_openedx_extensions.helpers.clickhouse as ch


@pytest.fixture
def get_client_mock(settings):
    """Mock clickhouse_get_client."""
    settings.FX_CLICKHOUSE_USER = 'user'
    settings.FX_CLICKHOUSE_PASSWORD = 'password'

    with patch('futurex_openedx_extensions.helpers.clickhouse.clickhouse_get_client') as mocked:
        mocked.return_value = Mock(dummy_client=1)
        yield mocked


def test_get_client(get_client_mock):  # pylint: disable=redefined-outer-name
    """Verify that get_client works as expected."""

    client = ch.get_client()

    assert client == get_client_mock.return_value
    get_client_mock.assert_called_once()


def test_get_client_user_settings_not_configured(get_client_mock, settings):  # pylint: disable=redefined-outer-name
    """Verify that get_client raises ClickhouseClientNotConfiguredError when user settings are not configured."""
    with pytest.raises(ch.ClickhouseClientNotConfiguredError):
        del settings.FX_CLICKHOUSE_USER
        ch.get_client()
    get_client_mock.assert_not_called()


def test_get_client_password_settings_not_configured(get_client_mock, settings):  # pylint: disable=redefined-outer-name
    """Verify that get_client raises ClickhouseClientNotConfiguredError when password settings are not configured."""
    with pytest.raises(ch.ClickhouseClientNotConfiguredError):
        del settings.FX_CLICKHOUSE_PASSWORD
        ch.get_client()
    get_client_mock.assert_not_called()


def test_get_client_failed_to_connect(get_client_mock):  # pylint: disable=redefined-outer-name
    """Verify that get_client raises ClickhouseClientNotConfiguredError when failed to connect."""
    get_client_mock.side_effect = Exception('Failed to connect')

    with pytest.raises(ch.ClickhouseClientConnectionError):
        ch.get_client()
    get_client_mock.assert_called_once()
