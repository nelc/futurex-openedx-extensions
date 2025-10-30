"""Constants for the FutureX Open edX Extensions app."""
from openedx.core.lib.api.authentication import BearerAuthentication
from rest_framework.authentication import SessionAuthentication

CACHE_NAME_ALL_COURSE_ORG_FILTER_LIST = 'fx_course_org_filter_list'
CACHE_NAME_ALL_TENANTS_INFO = 'fx_tenants_info_v3'
CACHE_NAME_ALL_VIEW_ROLES = 'fx_view_roles'
CACHE_NAME_ORG_TO_TENANT_MAP = 'fx_org_to_tenant_mapping'
CACHE_NAME_USER_COURSE_ACCESS_ROLES = 'fx_user_course_access_roles'
CACHE_NAME_LIVE_STATISTICS_PER_TENANT = 'fx_live_statistics_per_tenant'
CACHE_NAME_CONFIG_ACCESS_CONTROL = 'fx_config_access_control'
CACHE_NAME_TENANT_READABLE_LMS_CONFIG = 'fx_config_tenant_lms_config'

CACHE_NAMES = {
    CACHE_NAME_ALL_COURSE_ORG_FILTER_LIST: {
        'short_description': 'Course Organization Filter',
        'long_description': 'List of all course org filter for all tenants',
    },
    CACHE_NAME_ALL_TENANTS_INFO: {
        'short_description': 'Tenants Info',
        'long_description': 'Basic information about all tenants',
    },
    CACHE_NAME_ALL_VIEW_ROLES: {
        'short_description': 'View Accessible Roles',
        'long_description': 'Information about accessible roles for all supported views',
    },
    CACHE_NAME_ORG_TO_TENANT_MAP: {
        'short_description': 'Organization to Tenant Mapping',
        'long_description': 'Mapping of organization to tenant',
    }
}

CLICKHOUSE_FX_BUILTIN_ORG_IN_TENANTS = '__orgs_of_tenants__'
CLICKHOUSE_FX_BUILTIN_CA_USERS_OF_TENANTS = '__ca_users_of_tenants__'

CLICKHOUSE_QUERY_SLUG_PATTERN = r'[a-z0-9_\-.]+'

ID_PART = r'[a-zA-Z0-9_\-]+'
ID_RUN = r'[a-zA-Z0-9_.\-]+'
COURSE_ID_REGX = \
    fr'(?P<course_id>course-v1:(?P<org>{ID_PART})\+(?P<course>{ID_PART})\+(?P<run>{ID_RUN}))'
COURSE_ID_REGX_EXACT = rf'^{COURSE_ID_REGX}$'

LIBRARY_ID_REGX = \
    fr'(?P<library_id>library-v1:(?P<org>{ID_PART})\+(?P<code>{ID_PART}))'
LIBRARY_ID_REGX_EXACT = rf'^{LIBRARY_ID_REGX}$'

COURSE_STATUSES = {
    'active': 'active',
    'archived': 'archived',
    'upcoming': 'upcoming',
}

COURSE_STATUS_SELF_PREFIX = 'self_'


COURSE_CREATOR_ROLE_TENANT = 'org_course_creator_group'
COURSE_CREATOR_ROLE_GLOBAL = 'course_creator_group'
COURSE_SUPPORT_ROLE_GLOBAL = 'support'
COURSE_FX_API_ACCESS_ROLE = 'fx_api_access'
COURSE_FX_API_ACCESS_ROLE_GLOBAL = 'fx_api_access_global'

COURSE_ACCESS_ROLES_SUPPORTED_BUT_HIDDEN = [
    COURSE_FX_API_ACCESS_ROLE,
    COURSE_FX_API_ACCESS_ROLE_GLOBAL,
]

COURSE_ACCESS_ROLES_USER_VIEW_MAPPING = [
    COURSE_FX_API_ACCESS_ROLE,
    COURSE_FX_API_ACCESS_ROLE_GLOBAL
]

COURSE_ACCESS_ROLES_COURSE_ONLY = [
    'beta_testers',
    'ccx_coach',
    'finance_admin',
]
COURSE_ACCESS_ROLES_TENANT_ONLY = [
    COURSE_CREATOR_ROLE_TENANT,
]

COURSE_ACCESS_ROLES_STAFF_EDITOR = 'staff'
COURSE_ACCESS_ROLES_LIBRARY_USER = 'library_user'

COURSE_ACCESS_ROLES_TENANT_OR_COURSE = [
    'data_researcher',
    'instructor',
    'limit-staff',
    COURSE_ACCESS_ROLES_LIBRARY_USER,
    COURSE_ACCESS_ROLES_STAFF_EDITOR,
    COURSE_FX_API_ACCESS_ROLE,
]
COURSE_ACCESS_ROLES_GLOBAL = [
    COURSE_CREATOR_ROLE_GLOBAL,
    COURSE_SUPPORT_ROLE_GLOBAL,
    COURSE_FX_API_ACCESS_ROLE_GLOBAL,
]

COURSE_ACCESS_ROLES_SUPPORTED_EDIT = list(set(
    COURSE_ACCESS_ROLES_COURSE_ONLY +
    COURSE_ACCESS_ROLES_TENANT_ONLY +
    COURSE_ACCESS_ROLES_TENANT_OR_COURSE
) - set(COURSE_ACCESS_ROLES_SUPPORTED_BUT_HIDDEN))

COURSE_ACCESS_ROLES_SUPPORTED_READ = list(
    set(COURSE_ACCESS_ROLES_SUPPORTED_EDIT + COURSE_ACCESS_ROLES_GLOBAL) |
    set(COURSE_ACCESS_ROLES_SUPPORTED_BUT_HIDDEN)
)

COURSE_ACCESS_ROLES_ACCEPT_COURSE_ID = COURSE_ACCESS_ROLES_COURSE_ONLY + COURSE_ACCESS_ROLES_TENANT_OR_COURSE

COURSE_ACCESS_ROLES_UNSUPPORTED = [
    'sales_admin',  # won't be supported, looks like a deprecated role, there is no useful code for it
]

COURSE_ACCESS_ROLES_ALL = \
    COURSE_ACCESS_ROLES_SUPPORTED_READ + \
    COURSE_ACCESS_ROLES_UNSUPPORTED

COURSE_ACCESS_ROLES_MAX_USERS_PER_OPERATION = 20

USER_KEY_TYPE_ID = 'ID'
USER_KEY_TYPE_USERNAME = 'username'
USER_KEY_TYPE_EMAIL = 'email'
USER_KEY_TYPE_NOT_ID = 'username/email'

CSV_TASK_LIMIT_PER_USER = 3

FX_VIEW_DEFAULT_AUTH_CLASSES = [SessionAuthentication, BearerAuthentication]

KEY_TYPE_MAP = {
    'string': str,
    'integer': int,
    'boolean': bool,
    'dict': dict,
    'list': list,
}

ALLOWED_FILE_EXTENSIONS = ['.png', '.jpeg', '.jpg', '.ico', '.svg', '.css']

CSV_EXPORT_UPLOAD_DIR = 'exported_files'
CONFIG_FILES_UPLOAD_DIR = 'config_files'
