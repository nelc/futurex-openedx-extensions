"""Test settings for edx-platform-palm"""
from openedx.core import release

from test_utils.test_settings_common import *

release.RELEASE_LINE = 'palm'

# eox-tenant settings
EOX_TENANT_USERS_BACKEND = 'eox_tenant.edxapp_wrapper.backends.users_l_v1'
GET_BRANDING_API = 'eox_tenant.edxapp_wrapper.backends.branding_api_l_v1'
GET_SITE_CONFIGURATION_MODULE = 'eox_tenant.edxapp_wrapper.backends.site_configuration_module_i_v1'
GET_THEMING_HELPERS = 'eox_tenant.edxapp_wrapper.backends.theming_helpers_h_v1'
