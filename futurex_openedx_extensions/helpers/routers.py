"""Routers for dashboard views"""
import functools
from contextvars import ContextVar
from typing import Any, Callable, Optional

from django.conf import settings

_use_replica_db: ContextVar[bool] = ContextVar('use_replica_db', default=False)


class FXReadReplicaRouter:  # pylint: disable=no-self-use
    """Dashboard router to use read replica if available"""
    def __init__(self) -> None:
        """Initialize the router"""

    def db_for_read(self, model: Any, **hints: Any) -> Optional[str]:  # pylint: disable=unused-argument
        """Use read replica if available"""
        alias = getattr(settings, 'FX_DASHBOARD_READ_REPLICA_DB_ALIAS', None)
        return alias if (alias and _use_replica_db.get()) else None

    def db_for_write(self, model: Any, **hints: Any) -> None:  # pylint: disable=unused-argument
        """No route for writing"""
        return None

    def allow_relation(self, *a: Any, **kw: Any) -> Optional[bool]:  # pylint: disable=unused-argument
        """Allow relations if read replica context is active."""
        if _use_replica_db.get():
            return True
        return None

    def allow_migrate(self, *a: Any, **kw: Any) -> None:  # pylint: disable=unused-argument
        """No migration allowed"""
        return None


def use_read_replica_if_available(view_func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to use read replica if available"""
    @functools.wraps(view_func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        """Wrapper function to set the context variable to use read replica"""
        request = args[1] if len(args) > 1 else None

        if '.' not in view_func.__qualname__:
            raise TypeError(
                f'use_read_replica_if_available: expected a DRF Request as second argument in '
                f'{view_func.__name__!r}, got {type(request).__name__!r} instead. '
                'This decorator is only valid on class-based view methods.'
            )

        if request is not None and request.query_params.get('download') == 'csv':
            return view_func(*args, **kwargs)

        token = _use_replica_db.set(True)
        try:
            return view_func(*args, **kwargs)
        finally:
            _use_replica_db.reset(token)
    return wrapper
