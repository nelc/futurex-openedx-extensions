"""Tests for converters helpers."""
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
