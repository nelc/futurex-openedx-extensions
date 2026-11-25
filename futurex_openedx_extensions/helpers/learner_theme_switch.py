"""
Learner theme (fx-learner) switch pieces that need no tenant lookup: the theme options the switch writes and the
brand colour of the learner pages. Kept apart from `tenants` and `learner_theme` so both can use them.
"""
from __future__ import annotations

import re
from typing import Any, Dict

from django.conf import settings

from futurex_openedx_extensions.helpers import constants as cs

# The colour form the theme accepts
HEX_COLOR = re.compile(r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$')
BRAND_COLOR_TYPE = 'primary_color'


def get_learner_theme_options() -> Dict[str, str]:
    """
    Return the `THEME_OPTIONS.theme` value of an active learner theme: `fx-learner` on top of `indigo`. A tenant on
    plain `indigo` falls back to the platform default theme (`EOX_THEMING_DEFAULT_THEME_NAME`) for templates indigo
    does not have; that theme is kept as the grandparent so the fallback chain stays the same.

    :return: The theme options
    :rtype: Dict[str, str]
    """
    options = {'name': cs.LEARNER_THEME_NAME, 'parent': cs.LEARNER_THEME_PARENT_NAME}
    default_theme = getattr(settings, 'EOX_THEMING_DEFAULT_THEME_NAME', None)
    if default_theme and default_theme not in cs.LEARNER_THEME_SWITCHABLE_THEMES:
        options['grandparent'] = default_theme
    return options


def get_brand_color(visual_identity: Any) -> str | None:
    """
    Return the tenant's primary colour (`visual_identity.colors[]` with color_type `primary_color`) as a hex string,
    or None when it is missing or not a hex colour. Same reading as the theme's head-extra.

    :param visual_identity: The tenant's `theme_v2.visual_identity` value
    :type visual_identity: Any
    :return: The hex colour or None
    :rtype: str | None
    """
    colors = visual_identity.get('colors') if isinstance(visual_identity, dict) else None
    brand_color = None
    for color in colors if isinstance(colors, list) else []:
        if not isinstance(color, dict) or color.get('color_type') != BRAND_COLOR_TYPE:
            continue
        value = color.get('hex')
        if isinstance(value, str) and HEX_COLOR.match(value):
            brand_color = value
    return brand_color


def get_effective_brand_color(visual_identity: Any) -> str:
    """
    Return the brand colour of the tenant's learner pages, always a 6-digit hex: the tenant's own primary colour
    (see `get_brand_color`; `#abc` is expanded to `#aabbcc`), else the design colour
    (`LEARNER_THEME_DEFAULT_BRAND_COLOR`). A primary colour equal to a stock default of the dashboard's theme
    designer (`LEARNER_THEME_STOCK_PRIMARY_COLORS`, saved the first time the designer's colours panel is opened)
    is not a tenant choice and counts as missing.

    :param visual_identity: The tenant's `theme_v2.visual_identity` value
    :type visual_identity: Any
    :return: The hex colour
    :rtype: str
    """
    color = get_brand_color(visual_identity)
    if color and len(color) == 4:
        color = '#' + ''.join(char * 2 for char in color[1:])
    if not color or color.lower() in cs.LEARNER_THEME_STOCK_PRIMARY_COLORS:
        return cs.LEARNER_THEME_DEFAULT_BRAND_COLOR
    return color


def take_over_interactive_color(theme_options: Dict[str, Any], saved: Dict[str, Any], visual_identity: Any) -> None:
    """
    Set `THEME_OPTIONS.interactive_color` (the colour eox-nelp's MFE config sends to every MFE as
    `CUSTOM_PRIMARY_COLORS`) to the brand colour of the learner pages. The first time, the tenant's own value is
    recorded in the saved record under `THEME_OPTIONS.interactive_color` (None when it had none).

    :param theme_options: The tenant's THEME_OPTIONS, changed in place
    :type theme_options: Dict[str, Any]
    :param saved: The tenant's FX_LEARNER_THEME_SAVED record, changed in place
    :type saved: Dict[str, Any]
    :param visual_identity: The tenant's `theme_v2.visual_identity` value
    :type visual_identity: Any
    """
    if cs.LEARNER_THEME_SAVED_INTERACTIVE_COLOR_KEY not in saved:
        saved[cs.LEARNER_THEME_SAVED_INTERACTIVE_COLOR_KEY] = theme_options.get(cs.LEARNER_THEME_INTERACTIVE_COLOR_KEY)
    theme_options[cs.LEARNER_THEME_INTERACTIVE_COLOR_KEY] = get_effective_brand_color(visual_identity)


def restore_interactive_color(new_configs: Dict[str, Any], theme_options: Dict[str, Any], saved: Any) -> None:
    """
    Put `THEME_OPTIONS.interactive_color` back to the tenant's own value recorded by `take_over_interactive_color`
    (removed when it had none) and take the record out of the saved record. Nothing changes without a record.

    :param new_configs: The tenant's lms_configs, changed in place
    :type new_configs: Dict[str, Any]
    :param theme_options: The tenant's THEME_OPTIONS (an empty dict when the tenant's value is not a dict)
    :type theme_options: Dict[str, Any]
    :param saved: The tenant's FX_LEARNER_THEME_SAVED record, changed in place
    :type saved: Any
    """
    if not isinstance(saved, dict) or cs.LEARNER_THEME_SAVED_INTERACTIVE_COLOR_KEY not in saved:
        return
    own_color = saved.pop(cs.LEARNER_THEME_SAVED_INTERACTIVE_COLOR_KEY)
    if own_color is None:
        theme_options.pop(cs.LEARNER_THEME_INTERACTIVE_COLOR_KEY, None)
    else:
        theme_options[cs.LEARNER_THEME_INTERACTIVE_COLOR_KEY] = own_color
        new_configs['THEME_OPTIONS'] = theme_options
