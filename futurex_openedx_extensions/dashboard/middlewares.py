"""Middlewares"""
from typing import Any

from django.utils.deprecation import MiddlewareMixin
from eox_theming.edxapp_wrapper.models import get_openedx_site_theme_model


class FutureXThemePreviewMiddleware(MiddlewareMixin):  # pylint: disable=too-few-public-methods
    """This Middleware should run after the EoxThemeMiddleware to ensure that the preview theme is set correctly."""
    def process_request(self, request: Any) -> None:  # pylint: disable=no-self-use
        """Set the request's 'site_theme' if `theme-preview` cookie is set."""
        if request.COOKIES.get('theme-preview') != 'yes':
            return

        current_theme = get_openedx_site_theme_model()(
            site_id=1,
            theme_dir_name='indigo',
        )
        current_theme.id = 1
        request.site_theme = current_theme
