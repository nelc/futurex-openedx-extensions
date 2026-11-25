"""Middlewares"""
import logging
from typing import Any, Dict

from crum import get_current_request
from django.utils.deprecation import MiddlewareMixin
from eox_theming.edxapp_wrapper.models import get_openedx_site_theme_model

from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers.exceptions import FXCodedException
from futurex_openedx_extensions.helpers.tenants import (
    get_all_tenants_info,
    get_learner_theme_options,
    get_tenant_config,
    is_theme_preview_request,
)

logger = logging.getLogger(__name__)

PREVIEW_THEME_REQUEST_ATTRIBUTE = 'fx_preview_theme'
PREVIEW_THEME_OPTION_KEYS = ('name', 'parent', 'grandparent')


def get_preview_theme_name(request: Any) -> str:
    """
    Return the theme to preview: `fx-learner` when the DRAFT-overlaid config of the request's tenant has the learner
    theme both allowed and enabled, otherwise `indigo`.

    :param request: The current request
    :type request: Any
    :return: The theme directory name
    :rtype: str
    """
    domain = getattr(getattr(request, 'site', None), 'domain', None)
    tenant_id = get_all_tenants_info()['tenant_by_site'].get(domain) if domain else None
    if not tenant_id:
        return cs.LEARNER_THEME_PARENT_NAME

    try:
        values = get_tenant_config(
            tenant_id=tenant_id,
            keys=[cs.LEARNER_THEME_ALLOWED_KEY, cs.LEARNER_THEME_ENABLED_KEY],
            published_only=False,
        )['values']
    except FXCodedException:
        return cs.LEARNER_THEME_PARENT_NAME

    if values.get(cs.LEARNER_THEME_ALLOWED_KEY) is True and values.get(cs.LEARNER_THEME_ENABLED_KEY) is True:
        return cs.LEARNER_THEME_NAME
    return cs.LEARNER_THEME_PARENT_NAME


def get_preview_theme_options(theme_name: str) -> Dict[str, str]:
    """
    Return the `THEME_OPTIONS.theme` value that publishing would write for the previewed theme (the same values
    `apply_learner_theme` writes): `{"name": "fx-learner", "parent": "indigo"}`, or `{"name": "indigo"}`.

    :param theme_name: The previewed theme directory name
    :type theme_name: str
    :return: The theme options
    :rtype: Dict[str, str]
    """
    if theme_name == cs.LEARNER_THEME_NAME:
        return get_learner_theme_options()
    return {'name': theme_name}


def theme_preview_config_source(*args: Any) -> Any:
    """
    eox-theming config source that answers `('theme', 'name' | 'parent' | 'grandparent')` from the theme options the
    preview middleware stored on the CURRENT request, so the whole theme chain (templates and static files) of a
    preview request follows the previewed theme instead of the tenant's published THEME_OPTIONS.

    The value lives on the request object (read through crum's thread-local current request), never in settings, so
    it cannot leak into another request or thread. A key the previewed theme does not set answers '' (not None) so
    eox-theming does not fall through to the published value: an unset parent then resolves to
    EOX_THEMING_DEFAULT_THEME_NAME, exactly as it would after publishing. Anything else answers None (fall through).

    :param args: The option path, e.g. ('theme', 'parent')
    :type args: Any
    :return: The option value, or None to let the next source answer
    :rtype: Any
    """
    preview_options = getattr(get_current_request(), PREVIEW_THEME_REQUEST_ATTRIBUTE, None)
    if not isinstance(preview_options, dict) or len(args) != 2 or args[0] != 'theme':
        return None
    if args[1] not in PREVIEW_THEME_OPTION_KEYS:
        return None
    return preview_options.get(args[1], '')


def install_theme_preview_config_source() -> bool:
    """
    Put `theme_preview_config_source` first in eox-theming's config sources (once per process). When eox-theming
    changes its internals the preview falls back to the published parent theme and a warning is logged.

    :return: True if the source is installed
    :rtype: bool
    """
    try:
        from eox_theming.configuration import ThemingConfiguration  # pylint: disable=import-outside-toplevel
        sources = ThemingConfiguration.source_functions
    except (ImportError, AttributeError) as exc:
        logger.warning('theme preview: unable to install the eox-theming config source (%s)', exc)
        return False

    if not isinstance(sources, list):
        logger.warning('theme preview: eox-theming source_functions is not a list; config source not installed')
        return False

    if theme_preview_config_source not in sources:
        sources.insert(0, theme_preview_config_source)
    return True


class FutureXThemePreviewMiddleware(MiddlewareMixin):  # pylint: disable=too-few-public-methods
    """This Middleware should run after the EoxThemeMiddleware to ensure that the preview theme is set correctly."""
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Install the request-scoped eox-theming config source used by the preview."""
        super().__init__(*args, **kwargs)
        install_theme_preview_config_source()

    def process_request(self, request: Any) -> None:  # pylint: disable=no-self-use
        """
        Set the request's 'site_theme' if the `theme-preview` cookie is set on a signed-in request, and the theme
        options (name and parents) the preview resolves through `theme_preview_config_source` for this request only.
        """
        if not is_theme_preview_request(request):
            return

        theme_name = get_preview_theme_name(request)
        current_theme = get_openedx_site_theme_model()(
            site_id=1,
            theme_dir_name=theme_name,
        )
        current_theme.id = 1
        request.site_theme = current_theme
        setattr(request, PREVIEW_THEME_REQUEST_ATTRIBUTE, get_preview_theme_options(theme_name))
