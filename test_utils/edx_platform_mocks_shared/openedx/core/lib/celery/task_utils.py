"""edx-platform Mocks: celery task utils"""
from contextlib import contextmanager


@contextmanager
def emulate_http_request(site=None, user=None, middleware_classes=None):  # pylint: disable=unused-argument
    """Mock of emulate_http_request"""
    yield
