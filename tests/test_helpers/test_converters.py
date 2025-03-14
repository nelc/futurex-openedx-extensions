
"""Tests for converters helpers."""
from datetime import date, datetime
from unittest.mock import Mock, patch

import pytest

from futurex_openedx_extensions.helpers import converters
from futurex_openedx_extensions.helpers.converters import DateMethods


@pytest.mark.parametrize('ids_string, expected', [
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


@pytest.mark.parametrize('ids_string', [
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
    request = Mock(site=Mock(domain='example-converter.com'), scheme='https')
    assert converters.relative_url_to_absolute_url('/test9', request) == 'https://example-converter.com/test9'


@pytest.mark.parametrize('date_method_string, expected_error_msg', [
    ('bad_method', 'Invalid date method: bad_method'),
    (
        f'bad_method{DateMethods.ARG_SEPARATOR}9',
        f'Invalid date method: bad_method{DateMethods.ARG_SEPARATOR}',
    ),
    (
        f'today{DateMethods.ARG_SEPARATOR}not_a_number',
        f'Invalid integer given to method: today{DateMethods.ARG_SEPARATOR}not_a_number',
    ),
    (
        f'many_separators{DateMethods.ARG_SEPARATOR}{DateMethods.ARG_SEPARATOR}',
        (
            f'Date method contains many separators: many_separators{DateMethods.ARG_SEPARATOR}'
            f'{DateMethods.ARG_SEPARATOR}'
        ),
    ),
    (None, 'Date method string is empty'),
    ('', 'Date method string is empty'),
])
def test_date_methods_parse_date_method_invalid_argument(date_method_string, expected_error_msg):
    """Verify that DateMethods.parse_date_method raises ValueError for invalid date method."""
    with pytest.raises(ValueError) as exc_info:
        DateMethods.parse_date_method(date_method_string)
    assert exc_info.value.args[0] == expected_error_msg


@pytest.mark.parametrize('method, expected', [
    ('today', '2023-12-26'),
    ('yesterday', '2023-12-25'),
    ('tomorrow', '2023-12-27'),
    ('month_start', '2023-12-01'),
    ('month_end', '2023-12-31'),
    ('year_start', '2023-01-01'),
    ('year_end', '2023-12-31'),
    ('next_month_start', '2024-01-01'),
    ('next_month_end', '2024-01-31'),
    ('next_year_start', '2024-01-01'),
    ('next_year_end', '2024-12-31'),
    ('last_month_start', '2023-11-01'),
    ('last_month_end', '2023-11-30'),
    ('last_year_start', '2022-01-01'),
    ('last_year_end', '2022-12-31'),
    ('days,1', '2023-12-27'),
    ('days,-1', '2023-12-25'),
    ('months,1', '2024-01-26'),
    ('months,-1', '2023-11-26'),
    ('years,1', '2024-12-26'),
    ('years,-1', '2022-12-26'),
    ('2024-12-26', '2024-12-26'),
])
def test_date_methods_parse_date_method(method, expected):
    """Verify that DateMethods.parse_date_method return correct values."""
    time_freeze = date(2023, 12, 26)

    with patch('futurex_openedx_extensions.helpers.converters.datetime') as mock_datetime:
        mock_datetime.now.return_value = time_freeze
        assert DateMethods.parse_date_method(method) == expected


def test_date_methods_valid_supported_methods():
    """Verify that all methods in DateMethods.DATE_METHODS are valid."""
    for method_id in DateMethods.DATE_METHODS:
        method_parts = method_id.split(DateMethods.ARG_SEPARATOR)
        method = method_parts[0]
        assert hasattr(DateMethods, method), f'DateMethods.DATE_METHODS contains a non-existing method! ({method})'
        assert all(not item for item in method_parts[1:]), f'Bad DateMethods.DATE_METHODS format! ({method_id})'


@pytest.mark.parametrize('value, expected_result', [
    (date(2023, 12, 26), '2023-12-26T00:00:00Z'),
    (datetime(2023, 12, 26, 12, 30, 45), '2023-12-26T12:30:45Z'),
    (datetime(2023, 12, 26, 12, 30, 45).replace(microsecond=315), '2023-12-26T12:30:45Z'),
    (None, None),
])
def test_dt_to_str(value, expected_result):
    """Verify that dt_to_str return the correct string."""
    assert converters.dt_to_str(value) == expected_result


@pytest.mark.parametrize(
    'path, value, expected_output',
    [
        ('key1', 'value1', {'key1': 'value1'}),
        ('key1.key2.key3', 'value3', {'key1': {'key2': {'key3': 'value3'}}}),
        ('key1.key2.key3.key4', 'value4', {'key1': {'key2': {'key3': {'key4': 'value4'}}}}),
    ]
)
def test_path_to_json(path, value, expected_output):
    """Verify that path_to_json returns correct data"""
    result = converters.path_to_json(path, value)
    assert result == expected_output, f'Expected {expected_output}, but got {result}'


@pytest.mark.parametrize(
    'input_text, expected_output, test_case',
    [
        ('123', '١٢٣', 'Basic conversion'),
        ('0', '٠', 'Single digit'),
        ('9876543210', '٩٨٧٦٥٤٣٢١٠', 'All numbers reversed'),
        ('abc123xyz', 'abc١٢٣xyz', 'Mixed text with numbers'),
        ('No numbers here!', 'No numbers here!', 'No numbers'),
        ('', '', 'Empty string'),
        ('١٢٣', '١٢٣', 'Already Indian numerals'),
        ('Mixed 123 and ٤٥٦', 'Mixed ١٢٣ and ٤٥٦', 'Mixed Arabic & Indian numerals'),
    ],
)
def test_to_indian_numerals(input_text, expected_output, test_case):
    """Verify that to_indian_numerals returns correct data"""
    assert converters.to_indian_numerals(input_text) == expected_output, f'Failed: {test_case}'
