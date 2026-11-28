"""eox-theming Mocks: the theme middleware"""


class EoxThemeMiddleware:  # pylint: disable=too-few-public-methods
    """Mock of eox_theming.theming.middleware.EoxThemeMiddleware"""
    def __init__(self, get_response=None):
        self.get_response = get_response
