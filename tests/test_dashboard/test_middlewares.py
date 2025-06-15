"""Tests for middlewares."""
import pytest
from django.test import RequestFactory

from futurex_openedx_extensions.dashboard.middlewares import FutureXThemePreviewMiddleware


@pytest.fixture
def request_factory():
    return RequestFactory()


@pytest.fixture
def middleware():
    return FutureXThemePreviewMiddleware(get_response=lambda request: None)


def test_process_request_with_theme_preview_cookie(
    request_factory, middleware,
):  # pylint: disable=redefined-outer-name
    """Verify that the middleware sets the site_theme when the theme-preview cookie is set to `yes`."""
    request = request_factory.get('/')
    request.COOKIES['theme-preview'] = 'yes'
    assert not hasattr(request, 'site_theme')

    middleware.process_request(request)

    assert hasattr(request, 'site_theme')
    assert request.site_theme.site_id == 1
    assert request.site_theme.theme_dir_name == 'indigo'


def test_process_request_without_theme_preview_cookie(
    request_factory, middleware,
):  # pylint: disable=redefined-outer-name
    """Verify that the middleware does not set the site_theme when the theme-preview cookie is not set."""
    request = request_factory.get('/')

    middleware.process_request(request)

    assert not hasattr(request, 'site_theme')
