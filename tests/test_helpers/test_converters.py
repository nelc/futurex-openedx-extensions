
"""Tests for converters helpers."""
from unittest.mock import Mock

import pytest

from futurex_openedx_extensions.helpers import converters


@pytest.mark.parametrize("ids_string, expected", [
    ('1,2,3,7', [1, 2, 3, 7]),
    (', 1, 2, 3, 7, 8, ', [1, 2, 3, 7, 8]),
    (None, []),
    ('', []),
    (' ', []),
    (', , ', []),
])
def test_ids_string_to_list(ids_string, expected):
    """Verify ids_string_to_list function."""
    result = converters.ids_string_to_list(ids_string)
    assert result == expected


@pytest.mark.parametrize("ids_string", [
    '1.1, 2',
    '1, 2, 3, 7, 8, a',
])
def test_ids_string_to_list_bad_string(ids_string):
    """Verify ids_string_to_list function."""
    with pytest.raises(ValueError):
        converters.ids_string_to_list(ids_string)


def test_error_details_to_dictionary():
    """Verify error_details_to_dictionary function."""
    result = converters.error_details_to_dictionary(
        'This is an error message',
        code=123,
        key1='value1',
        key2='value2',
        anything={'key': 'value'},
    )
    assert result == {
        'reason': 'This is an error message',
        'details': {
            'code': 123,
            'key1': 'value1',
            'key2': 'value2',
            'anything': {'key': 'value'},
        },
    }


def test_relative_url_to_absolute_url_no_request():
    """Verify that relative_url_to_absolute_url return None when no request is provided."""
    assert converters.relative_url_to_absolute_url('/test', None) is None


def test_relative_url_to_absolute_url_no_site():
    """Verify that relative_url_to_absolute_url return None when no site is in the provided request."""
    request = Mock()
    delattr(request, 'site')  # pylint: disable=literal-used-as-attribute
    assert not hasattr(request, 'site')
    assert converters.relative_url_to_absolute_url('/test', request) is None


def test_relative_url_to_absolute_url_with_site():
    """Verify that relative_url_to_absolute_url return the correct absolute URL."""
    request = Mock()
    request.site.domain = 'https://example-converter.com'
    assert converters.relative_url_to_absolute_url('/test9', request) == 'https://example-converter.com/test9'
