"""Tests for futurex_openedx_extensions.dashboard.views.routers"""
from unittest.mock import patch

import pytest

from futurex_openedx_extensions.dashboard.views import routers


def test_db_for_read_with_replica_alias_and_decorator():
    """When FX_DASHBOARD_READ_REPLICA_DB_ALIAS is set and decorator is used, db_for_read returns alias."""
    with patch.dict(routers.settings.__dict__, {'FX_DASHBOARD_READ_REPLICA_DB_ALIAS': 'replica_db'}):
        router = routers.FXReadReplicaRouter()

        @routers.use_read_replica_if_available
        def inner():
            return router.db_for_read(object)

        assert inner() == 'replica_db'


def test_db_for_read_without_alias():
    """If no alias is configured, db_for_read returns None even when decorator sets context."""
    with patch.object(routers.settings, 'FX_DASHBOARD_READ_REPLICA_DB_ALIAS', new=None, create=True):
        router = routers.FXReadReplicaRouter()

        @routers.use_read_replica_if_available
        def inner():
            return router.db_for_read(object)

        assert inner() is None


def test_db_write_and_relations_and_migrate_return_none():
    """db_for_write, allow_relation and allow_migrate all explicitly return None."""
    router = routers.FXReadReplicaRouter()
    assert router.db_for_write(object) is None
    assert router.allow_relation() is None
    assert router.allow_migrate() is None


def test_contextvar_reset_on_exception():
    """The decorator should reset the context variable even if the wrapped function raises."""
    with patch.dict(routers.settings.__dict__, {'FX_DASHBOARD_READ_REPLICA_DB_ALIAS': 'rep'}):
        router = routers.FXReadReplicaRouter()

        @routers.use_read_replica_if_available
        def inner_raises():
            raise RuntimeError('boom')

        with pytest.raises(RuntimeError):
            inner_raises()

    # after the function raised, the contextvar must be reset so router.db_for_read returns None
    assert router.db_for_read(object) is None
