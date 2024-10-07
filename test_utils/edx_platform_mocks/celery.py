"""Mock celery shared task to run tests independent of celery"""
from functools import wraps


def shared_task(base):  # pylint: disable=unused-argument
    """Empty decorator with a fake delay method to mock Celery Task delay."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        # Adding a delay method to the wrapper
        wrapper.delay = lambda *args, **kwargs: wrapper(*args, **kwargs)  # pylint: disable=unnecessary-lambda
        return wrapper
    return decorator
