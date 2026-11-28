"""edx-platform Mocks: ace_common template context"""


def get_base_template_context(site, user=None):  # pylint: disable=unused-argument
    """Mock of get_base_template_context"""
    return {'platform_name': 'base platform name', 'logo_url': 'https://example.com/logo.png'}
