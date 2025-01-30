"""Tests for the utils module of the upgrade app"""
from unittest.mock import patch

import pytest

from futurex_openedx_extensions.upgrade import utils


def test_get_edx_platform_release():
    """Verify that the release line is returned"""
    with patch('futurex_openedx_extensions.upgrade.utils.RELEASE_LINE', 'testing-release'):
        assert utils.get_edx_platform_release() == 'testing-release'


@pytest.mark.parametrize('release_line, expected_result, log_message', [
    ('redwood', 'redwood', False),
    ('sumac', 'sumac', False),
    ('master', 'sumac', True),
    ('juniper', 'redwood', True),
    ('tulip', 'sumac', True),
])
def test_get_current_version(release_line, expected_result, log_message, caplog):
    """Verify that the current version is returned and logs are correct"""
    with patch('futurex_openedx_extensions.upgrade.utils.get_edx_platform_release', return_value=release_line):
        assert utils.get_current_version() == expected_result

    if log_message:
        assert f'edx-platform release line is ({release_line}) which is not a supported version. ' \
               f'Defaulting to ({expected_result}).' in caplog.text
    else:
        assert 'edx-platform release line is (' not in caplog.text
