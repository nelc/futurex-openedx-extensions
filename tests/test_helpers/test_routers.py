"""Tests for futurex_openedx_extensions.helpers.routers"""
from unittest.mock import MagicMock, patch

import pytest

from futurex_openedx_extensions.dashboard.views import routers as legacy_routers
from futurex_openedx_extensions.helpers import routers


def _make_mock_request(download=None):
    """Return a mock DRF-like request with configurable download query param."""
    mock_request = MagicMock()
    mock_request.query_params.get.return_value = download
    return mock_request


def test_db_for_read_with_replica_alias_and_decorator():
    """When FX_DASHBOARD_READ_REPLICA_DB_ALIAS is set and decorator is used, db_for_read returns alias."""
    with patch.dict(routers.settings.__dict__, {'FX_DASHBOARD_READ_REPLICA_DB_ALIAS': 'replica_db'}):
        router = routers.FXReadReplicaRouter()
        mock_request = _make_mock_request()

        class FakeView:  # pylint: disable=too-few-public-methods
            @routers.use_read_replica_if_available
            def inner(self, request):  # pylint: disable=no-self-use
                return router.db_for_read(object)

        assert FakeView().inner(mock_request) == 'replica_db'


def test_db_for_read_without_alias():
    """If no alias is configured, db_for_read returns None even when decorator sets context."""
    with patch.object(routers.settings, 'FX_DASHBOARD_READ_REPLICA_DB_ALIAS', new=None, create=True):
        router = routers.FXReadReplicaRouter()
        mock_request = _make_mock_request()

        class FakeView:  # pylint: disable=too-few-public-methods
            @routers.use_read_replica_if_available
            def inner(self, request):  # pylint: disable=no-self-use
                return router.db_for_read(object)

        assert FakeView().inner(mock_request) is None


def test_db_write_and_relations_and_migrate_return_none():
    """db_for_write, allow_relation and allow_migrate all explicitly return None."""
    router = routers.FXReadReplicaRouter()
    assert router.db_for_write(object) is None
    assert router.allow_relation() is None
    assert router.allow_migrate() is None


def test_allow_relation_true_inside_replica_context():
    """allow_relation returns True while the read replica context is active, and None outside it."""
    router = routers.FXReadReplicaRouter()
    assert router.allow_relation() is None

    token = routers._use_replica_db.set(True)  # pylint: disable=protected-access
    try:
        assert router.allow_relation() is True
    finally:
        routers._use_replica_db.reset(token)  # pylint: disable=protected-access

    assert router.allow_relation() is None


def test_decorator_raises_type_error_for_plain_function():
    """Decorator raises TypeError when applied to a plain function (no dot in qualname)."""
    def plain_function():
        pass  # pragma: no cover

    plain_function.__qualname__ = 'plain_function'
    decorated = routers.use_read_replica_if_available(plain_function)

    with pytest.raises(TypeError, match='only valid on class-based view methods'):
        decorated()


def test_decorator_skips_replica_when_download_csv():
    """Decorator bypasses replica and calls view directly when download=csv query param is set."""
    mock_request = _make_mock_request(download='csv')
    call_log = []

    class FakeView:  # pylint: disable=too-few-public-methods
        @routers.use_read_replica_if_available
        def inner(self, request):  # pylint: disable=no-self-use
            call_log.append(routers._use_replica_db.get())  # pylint: disable=protected-access

    FakeView().inner(mock_request)
    assert call_log == [False]


def test_contextvar_reset_on_exception():
    """The decorator should reset the context variable even if the wrapped function raises."""
    with patch.dict(routers.settings.__dict__, {'FX_DASHBOARD_READ_REPLICA_DB_ALIAS': 'rep'}):
        router = routers.FXReadReplicaRouter()
        mock_request = _make_mock_request()

        class FakeView:  # pylint: disable=too-few-public-methods
            @routers.use_read_replica_if_available
            def inner_raises(self, request):  # pylint: disable=no-self-use
                raise RuntimeError('boom')

        with pytest.raises(RuntimeError):
            FakeView().inner_raises(mock_request)

    # after the function raised, the contextvar must be reset so router.db_for_read returns None
    assert router.db_for_read(object) is None


def test_legacy_router_path_reexports_same_class():
    """Production DATABASE_ROUTERS references the old dotted path; it must keep resolving."""
    assert legacy_routers.FXReadReplicaRouter is routers.FXReadReplicaRouter
