"""Helper functions for caching"""
from __future__ import annotations

import functools
import logging
from datetime import timedelta
from typing import Any, Callable, Dict

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from futurex_openedx_extensions.helpers import constants as cs

log = logging.getLogger(__name__)


def cache_dict(timeout: int | str, key_generator_or_name: str | Callable) -> Callable:
    """
    Cache the dictionary result returned by the function

    The caller can pass `___skip_cache` as a keyword argument to skip the cache. This will invoke a fresh call
    to the function and return the result without caching it nor invalidating the currently cached value.
    """
    def decorator(func: Callable) -> Callable:
        """Decorator definition"""
        @functools.wraps(func)
        def wrapped(*args: Any, **kwargs: Any) -> Dict[str, Any]:
            """Wrapped function"""
            cache_key = None
            timeout_seconds = None
            skip_cache = kwargs.pop('__skip_cache', False)
            try:
                if isinstance(timeout, str):
                    timeout_seconds = getattr(settings, timeout, None)
                    if timeout_seconds is None:
                        raise ValueError(f'timeout setting ({timeout}) not found')
                else:
                    timeout_seconds = timeout

                if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
                    raise ValueError(
                        'unexpected timeout value. Should be an integer greater than 0'
                    )
                if not callable(key_generator_or_name) and not isinstance(key_generator_or_name, str):
                    raise TypeError('key_generator_or_name must be a callable or a string')

                cache_key = key_generator_or_name(
                    *args, **kwargs
                ) if callable(key_generator_or_name) else key_generator_or_name

            except Exception as exc:
                log.exception('cache_dict: error generating cache key: %s', exc)

            if skip_cache:
                return func(*args, **kwargs)

            result = cache.get(cache_key) if cache_key else None
            if result is not None:
                result = result.get('data')

            if result is None:
                result = func(*args, **kwargs)
                now_datetime = timezone.now()
                if cache_key and result and isinstance(result, dict):
                    timeout_seconds = float(timeout_seconds)  # type: ignore
                    cache.set(
                        cache_key,
                        {
                            'created_datetime': now_datetime,
                            'expiry_datetime': now_datetime + timedelta(seconds=timeout_seconds),
                            'data': result,
                        },
                        timeout_seconds,
                    )
                elif cache_key and result:
                    log.error(
                        'cache_dict: expecting dictionary result from %s but got %s',
                        func.__name__, type(result)
                    )
            return result

        return wrapped
    return decorator


def invalidate_cache(cache_name: str = None) -> None:
    """
    Invalidate a specific cache or all predefined caches.

    - To invalidate a specific cache, provide the cache name.
    - To reset all predefined caches, pass None as `cache_name`.

    :param cache_name: The name of the cache to invalidate.
    :raises FXCodedException: If the provided `cache_name` is invalid (and not `"__all__"`).
    """
    if not cache_name:
        cache.delete(cs.CACHE_NAME_ALL_COURSE_ORG_FILTER_LIST)
        cache.delete(cs.CACHE_NAME_ALL_TENANTS_INFO)
        cache.delete(cs.CACHE_NAME_ALL_VIEW_ROLES)
        cache.delete(cs.CACHE_NAME_ORG_TO_TENANT_MAP)
    else:
        cache.delete(cache_name)
