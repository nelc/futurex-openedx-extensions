"""Clickhouse helper functions."""
from __future__ import annotations

import logging

from clickhouse_connect import get_client as clickhouse_get_client
from clickhouse_connect.driver.httpclient import HttpClient
from django.conf import settings

logger = logging.getLogger(__name__)


class ClickhouseClientNotConfiguredError(Exception):
    """Clickhouse client not configured error."""


class ClickhouseClientConnectionError(Exception):
    """Clickhouse client connection error."""


def get_client() -> HttpClient:
    """
    Get Clickhouse client.

    :return: Clickhouse client.
    :rtype: HttpClient
    """
    try:
        username = settings.FX_CLICKHOUSE_USER
        password = settings.FX_CLICKHOUSE_PASSWORD
    except AttributeError as exc:
        logger.error('Error getting Clickhouse credentials: %s', exc)
        raise ClickhouseClientNotConfiguredError() from exc

    try:
        client = clickhouse_get_client(host='clickhouse', port=8123, username=username, password=password)
    except Exception as exc:
        logger.error('Error getting Clickhouse client: %s', exc)
        raise ClickhouseClientConnectionError() from exc

    return client
