"""Tests for clickhouse helper functions."""
from unittest.mock import Mock, patch

import pytest
from django.core.paginator import EmptyPage

import futurex_openedx_extensions.helpers.clickhouse_operations as ch

SIMPLE_QUERY = 'SELECT * FROM table'


@pytest.fixture
def get_client_mock():
    """Mock clickhouse_get_client."""
    with patch('futurex_openedx_extensions.helpers.clickhouse_operations.clickhouse_get_client') as mocked:
        mocked.return_value = Mock(dummy_client=1)
        yield mocked


def test_get_client(get_client_mock):  # pylint: disable=redefined-outer-name
    """Verify that get_client works as expected."""

    client = ch.get_client()

    assert client == get_client_mock.return_value
    get_client_mock.assert_called_once()


@pytest.mark.parametrize('setting_to_delete, test_case', [
    ('FX_CLICKHOUSE_USER', 'Missing user setting'),
    ('FX_CLICKHOUSE_PASSWORD', 'Missing password setting'),
    ('FX_CLICKHOUSE_HOSTNAME', 'Missing hostname setting'),
    ('FX_CLICKHOUSE_PORT', 'Missing port setting'),
])
def test_get_client_settings_not_configured(
    get_client_mock, settings, setting_to_delete, test_case,
):  # pylint: disable=redefined-outer-name
    """Verify that get_client raises ClickhouseClientNotConfiguredError when required settings are not configured."""
    delattr(settings, setting_to_delete)
    with pytest.raises(ch.ClickhouseClientNotConfiguredError):
        ch.get_client()
    assert get_client_mock.call_count == 0, test_case


def test_get_client_failed_to_connect(get_client_mock):  # pylint: disable=redefined-outer-name
    """Verify that get_client raises ClickhouseClientNotConfiguredError when failed to connect."""
    get_client_mock.side_effect = Exception('Failed to connect')

    with pytest.raises(ch.ClickhouseClientConnectionError):
        ch.get_client()
    get_client_mock.assert_called_once()


def test_get_default_queries():
    """Verify that get_default_queries works as expected."""
    queries = ch.get_default_queries()

    assert queries['default_queries']['course']['v1']['activities-day']['description'] == \
           'Course activities per day for all users in the given tenants\n'


@patch('futurex_openedx_extensions.helpers.clickhouse_operations.yaml')
def test_get_default_queries_failed_to_load(mocked_yaml):
    """Verify that get_default_queries raises ClickhouseDefaultQueriesError when failed to load."""
    mocked_yaml.safe_load.side_effect = Exception('Failed to load queries')

    with pytest.raises(ch.ClickhouseDefaultQueriesError) as exc_info:
        ch.get_default_queries()
    mocked_yaml.safe_load.assert_called_once()
    assert exc_info.value.args[0] == 'Error loading default Clickhouse queries: Failed to load queries'


def test_validate_clickhouse_query(get_client_mock):  # pylint: disable=redefined-outer-name
    """Verify that validate_clickhouse_query works as expected."""
    ch.validate_clickhouse_query(get_client_mock, SIMPLE_QUERY)
    get_client_mock.query.assert_called_once_with(f'EXPLAIN {SIMPLE_QUERY}', parameters=None)


def test_validate_clickhouse_query_invalid_query(get_client_mock):  # pylint: disable=redefined-outer-name
    """Verify that validate_clickhouse_query raises ClickhouseQueryParamsError when invalid query."""
    get_client_mock.query.side_effect = Exception('Invalid query')

    with pytest.raises(ch.ClickhouseQueryParamsError) as exc_info:
        ch.validate_clickhouse_query(get_client_mock, SIMPLE_QUERY)
    assert exc_info.value.args[0] == 'Clickhouse query is not valid: Invalid query'


def test_count_result(get_client_mock):  # pylint: disable=redefined-outer-name
    """Verify that count_result works as expected."""
    get_client_mock.query.return_value = Mock(result_rows=[[1]])

    result = ch.count_result(get_client_mock, SIMPLE_QUERY, parameters=None)
    get_client_mock.query.assert_called_once_with(f'SELECT COUNT(*) FROM ({SIMPLE_QUERY})', parameters=None)
    assert result == get_client_mock.query.return_value.result_rows[0][0]


def test_count_result_invalid_query(get_client_mock):  # pylint: disable=redefined-outer-name
    """Verify that count_result raises ClickhouseQueryParamsError when invalid query."""
    get_client_mock.query.side_effect = Exception('Invalid query')

    with pytest.raises(ch.ClickhouseQueryParamsError) as exc_info:
        ch.count_result(get_client_mock, SIMPLE_QUERY, parameters=None)
    assert exc_info.value.args[0] == 'Error counting Clickhouse query results: Invalid query'


def test_execute_query(get_client_mock):  # pylint: disable=redefined-outer-name
    """Verify that execute_query works as expected."""
    result = ch.execute_query(get_client_mock, SIMPLE_QUERY)
    get_client_mock.query.assert_called_once_with(SIMPLE_QUERY, parameters=None)
    assert result == (None, None, get_client_mock.query.return_value)


def test_execute_query_empty_result_when_paginated(get_client_mock):  # pylint: disable=redefined-outer-name
    """Verify that execute_query works as expected when result is empty."""
    with patch('futurex_openedx_extensions.helpers.clickhouse_operations.count_result') as count_result_mock:
        count_result_mock.return_value = 0
        result = ch.execute_query(get_client_mock, SIMPLE_QUERY, page=1, page_size=10)
    get_client_mock.query.assert_not_called()
    assert result == (0, None, None)


def test_execute_query_invalid_query(get_client_mock):  # pylint: disable=redefined-outer-name
    """Verify that execute_query raises ClickhouseQueryParamsError when invalid query."""
    get_client_mock.query.side_effect = Exception('Invalid query')

    with pytest.raises(ch.ClickhouseQueryParamsError) as exc_info:
        ch.execute_query(get_client_mock, SIMPLE_QUERY)
    assert exc_info.value.args[0] == 'Error executing Clickhouse query: Invalid query'


def test_execute_query_paginated(get_client_mock):  # pylint: disable=redefined-outer-name
    """Verify that execute_query works as expected when paginated."""
    get_client_mock.query.return_value = Mock(result_rows=[['result1', 'result2']])

    with patch('futurex_openedx_extensions.helpers.clickhouse_operations.count_result') as count_result_mock:
        count_result_mock.return_value = 100
        result = ch.execute_query(get_client_mock, SIMPLE_QUERY, page=2, page_size=10)
        get_client_mock.query.assert_called_once_with(f'{SIMPLE_QUERY} LIMIT 10 OFFSET 10', parameters=None)
        assert result == (100, 3, get_client_mock.query.return_value)


@pytest.mark.parametrize('page, expected_error_msg', [
    (0, 'Page should be greater than or equal to 1'),
    (50, 'Page does not exist!'),
]
)
def test_execute_query_invalid_page(
    get_client_mock, page, expected_error_msg
):  # pylint: disable=redefined-outer-name
    """Verify that execute_query raises EmptyPage when page value is invalid."""
    with patch('futurex_openedx_extensions.helpers.clickhouse_operations.count_result') as count_result_mock:
        count_result_mock.return_value = 100
        with pytest.raises(EmptyPage) as exc_info:
            ch.execute_query(get_client_mock, SIMPLE_QUERY, page=page, page_size=10)
        assert exc_info.value.args[0] == expected_error_msg
        get_client_mock.query.assert_not_called()


@pytest.mark.parametrize('page_size, expected_error_msg', [
    (None, 'Page size should be an integer between 1 and 1000'),
    (0, 'Page size should be an integer between 1 and 1000'),
    (-1, 'Page size should be an integer between 1 and 1000'),
    (1001, 'Page size should be an integer between 1 and 1000'),
    (500, 'Page does not exist!'),
]
)
def test_execute_query_invalid_page_size(
    get_client_mock, page_size, expected_error_msg
):  # pylint: disable=redefined-outer-name
    """Verify that execute_query raises EmptyPage when page_size value is invalid."""
    with patch('futurex_openedx_extensions.helpers.clickhouse_operations.count_result') as count_result_mock:
        count_result_mock.return_value = 100
        with pytest.raises(EmptyPage) as exc_info:
            ch.execute_query(get_client_mock, SIMPLE_QUERY, page=3, page_size=page_size)
        assert exc_info.value.args[0] == expected_error_msg
        get_client_mock.query.assert_not_called()


def test_result_to_json():
    """Verify that result_to_json works as expected."""
    assert ch.result_to_json(None) == []

    result = Mock()
    result.result_rows = [
        ['value1', 1, 1.1, None],
        ['value2', 2, 2.2, 3],
    ]
    result.column_names = ['column1', 'column2', 'column3', 'column7']

    json_result = ch.result_to_json(result)
    expected_result = [
        {'column1': 'value1', 'column2': 1, 'column3': 1.1, 'column7': None},
        {'column1': 'value2', 'column2': 2, 'column3': 2.2, 'column7': 3},
    ]
    assert json_result == expected_result
