"""Helper functions for caching"""
import functools
import logging

from django.conf import settings
from django.core.cache import cache

log = logging.getLogger(__name__)


def cache_dict(timeout, key_generator_or_name):
    """Cache the dictionary result returned by the function"""
    def decorator(func):
        """Decorator definition"""
        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            """Wrapped function"""
            cache_key = None
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

            except Exception as exc:  # pylint: disable=broad-except
                log.exception('cache_dict: error generating cache key: %s', exc)

            result = cache.get(cache_key) if cache_key else None
            if result is None:
                result = func(*args, **kwargs)
                if cache_key and result and isinstance(result, dict):
                    cache.set(cache_key, result, timeout_seconds)
                elif cache_key and result:
                    # log: cache_dict: expecting dictionary result from <<function name>> but got <<result type>>
                    log.error(
                        'cache_dict: expecting dictionary result from %s but got %s',
                        func.__name__, type(result)
                    )
            return result

        return wrapped
    return decorator
