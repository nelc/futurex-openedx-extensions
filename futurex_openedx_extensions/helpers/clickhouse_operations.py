"""Clickhouse helper functions."""
from __future__ import annotations

import os
from typing import Any, Dict

import yaml  # type: ignore
from clickhouse_connect import get_client as clickhouse_get_client
from clickhouse_connect.driver.httpclient import Client
from clickhouse_connect.driver.query import QueryResult
from django.conf import settings
from django.core.paginator import EmptyPage


class ClickhouseBaseError(Exception):
    """Clickhouse base error."""


class ClickhouseClientNotConfiguredError(ClickhouseBaseError):
    """Clickhouse client not configured error."""


class ClickhouseClientConnectionError(ClickhouseBaseError):
    """Clickhouse client connection error."""


class ClickhouseQueryParamsError(ClickhouseBaseError):
    """Clickhouse query parameters error."""


class ClickhouseDefaultQueriesError(ClickhouseBaseError):
    """Clickhouse default queries error."""


def get_client() -> Client:
    """
    Get Clickhouse client.

    :return: Clickhouse client.
    :rtype: Client
    """
    try:
        username = settings.FX_CLICKHOUSE_USER
        password = settings.FX_CLICKHOUSE_PASSWORD
    except AttributeError as exc:
        raise ClickhouseClientNotConfiguredError(f'Error getting Clickhouse credentials: {exc}') from exc

    try:
        client = clickhouse_get_client(host='clickhouse', port=8123, username=username, password=password)
    except Exception as exc:
        raise ClickhouseClientConnectionError(f'Error getting Clickhouse client: {exc}') from exc

    return client


def get_default_queries() -> dict:
    """
    Get the default Clickhouse queries.

    :return: The default Clickhouse queries.
    :rtype: dict
    """
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    yaml_file_path = os.path.join(plugin_dir, 'assets', 'clickhouse_default_queries.yml')

    try:
        with open(yaml_file_path, 'r', encoding='utf-8') as file:
            queries = yaml.safe_load(file)
    except Exception as exc:
        raise ClickhouseDefaultQueriesError(f'Error loading default Clickhouse queries: {exc}') from exc

    return queries


def validate_clickhouse_query(
    clickhouse_client: Client,
    query: str,
    parameters: Dict[str, Any] | None = None,
) -> None:
    """
    Validate the Clickhouse query.

    :param clickhouse_client: The Clickhouse client.
    :type clickhouse_client: Client
    :param query: The Clickhouse query to validate.
    :type query: str
    :param parameters: The parameters to format the query with.
    :type parameters: Dict[str, Any] | None
    """
    explain_query = f'EXPLAIN {query}'

    try:
        clickhouse_client.query(explain_query, parameters=parameters)
    except Exception as exc:
        raise ClickhouseQueryParamsError(f'Clickhouse query is not valid: {exc}') from exc


def count_result(clickhouse_client: Client, query: str, parameters: Dict[str, Any] | None) -> int:
    """
    Count the results of the Clickhouse query.

    :param clickhouse_client: The Clickhouse client.
    :type clickhouse_client: Client
    :param query: The Clickhouse query to count.
    :type query: str
    :param parameters: The parameters to format the query with.
    :type parameters: Dict[str, Any] | None
    :return: The count of the results.
    :rtype: int
    """
    count_query = f'SELECT COUNT(*) FROM ({query})'

    try:
        result = clickhouse_client.query(count_query, parameters=parameters).result_rows
    except Exception as exc:
        raise ClickhouseQueryParamsError(f'Error counting Clickhouse query results: {exc}') from exc

    return result[0][0]


def execute_query(
    clickhouse_client: Client,
    query: str,
    parameters: Dict[str, Any] | None = None,
    page: int | None = None,
    page_size: int = 20,
) -> tuple[int | None, int | None, QueryResult | None]:
    """
    Execute the Clickhouse query.

    :param clickhouse_client: The Clickhouse client.
    :type clickhouse_client: Client
    :param query: The Clickhouse query to execute.
    :type query: str
    :param parameters: The parameters to format the query with.
    :type parameters: Dict[str, Any] | None
    :param page: The page number.
    :type page: int
    :param page_size: The page size.
    :type page_size: int
    :return: The results of the query.
    :rtype: tuple[int | None, int | None, QueryResult | None]
    """
    max_count = None
    next_page = None

    if page is not None:
        if page < 1:
            raise EmptyPage('Page should be greater than or equal to 1')
        if page_size is None or page_size < 1 or page_size > 1000:
            raise EmptyPage('Page size should be an integer between 1 and 1000')

    if page:
        offset = (page - 1) * page_size
        max_count = count_result(clickhouse_client, query, parameters=parameters)
        if max_count == 0:
            return 0, None, None

        if offset >= max_count:
            raise EmptyPage('Page does not exist!')
        next_page = page + 1 if offset + page_size < max_count else None
        query = f'{query} LIMIT {page_size} OFFSET {offset}'

    try:
        result = clickhouse_client.query(query, parameters=parameters)
    except Exception as exc:
        raise ClickhouseQueryParamsError(f'Error executing Clickhouse query: {exc}') from exc

    return max_count, next_page, result


def result_to_json(result: QueryResult | None) -> list[dict]:
    """
    Convert the Clickhouse result to JSON.

    :param result: The Clickhouse result.
    :type result: QueryResult | None
    :return: The result as JSON.
    :rtype: list[dict]
    """
    if result is None:
        return []

    columns = result.column_names
    rows = result.result_rows

    return [dict(zip(columns, row)) for row in rows]
