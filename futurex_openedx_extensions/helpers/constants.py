"""Constants for the FutureX Open edX Extensions app."""
CACHE_NAME_ALL_COURSE_ORG_FILTER_LIST = 'fx_course_org_filter_list'
CACHE_NAME_ALL_TENANTS_INFO = 'fx_tenants_info'
CACHE_NAME_ALL_VIEW_ROLES = 'fx_view_roles'
CACHE_NAME_ORG_TO_TENANT_MAP = 'fx_org_to_tenant_mapping'
CACHE_NAME_USER_COURSE_ACCESS_ROLES = 'fx_user_course_access_roles'

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
}

CLICKHOUSE_FX_BUILTIN_ORG_IN_TENANTS = '__orgs_of_tenants__'
CLICKHOUSE_FX_BUILTIN_CA_USERS_OF_TENANTS = '__ca_users_of_tenants__'

CLICKHOUSE_QUERY_SLUG_PATTERN = r'[a-z0-9_\-.]+'

COURSE_ID_PART = r'[a-zA-Z0-9_-]+'
COURSE_ID_REGX = \
    fr'(?P<course_id>course-v1:(?P<org>{COURSE_ID_PART})\+(?P<course>{COURSE_ID_PART})\+(?P<run>{COURSE_ID_PART}))'
COURSE_ID_REGX_EXACT = rf'^{COURSE_ID_REGX}$'

COURSE_STATUSES = {
    'active': 'active',
    'archived': 'archived',
    'upcoming': 'upcoming',
}

COURSE_STATUS_SELF_PREFIX = 'self_'


COURSE_CREATOR_ROLE_TENANT = 'org_course_creator_group'
COURSE_CREATOR_ROLE_GLOBAL = 'course_creator_group'
COURSE_SUPPORT_ROLE_GLOBAL = 'support'

COURSE_ACCESS_ROLES_COURSE_ONLY = [
    'beta_testers',
    'ccx_coach',
    'finance_admin',
]
COURSE_ACCESS_ROLES_TENANT_ONLY = [
    COURSE_CREATOR_ROLE_TENANT,
]
COURSE_ACCESS_ROLES_TENANT_OR_COURSE = [
    'data_researcher',
    'instructor',
    'staff',
]
COURSE_ACCESS_ROLES_GLOBAL = [
    COURSE_CREATOR_ROLE_GLOBAL,
    COURSE_SUPPORT_ROLE_GLOBAL,
]

COURSE_ACCESS_ROLES_SUPPORTED_EDIT = \
    COURSE_ACCESS_ROLES_COURSE_ONLY + \
    COURSE_ACCESS_ROLES_TENANT_ONLY + \
    COURSE_ACCESS_ROLES_TENANT_OR_COURSE

COURSE_ACCESS_ROLES_SUPPORTED_READ = COURSE_ACCESS_ROLES_SUPPORTED_EDIT + COURSE_ACCESS_ROLES_GLOBAL

COURSE_ACCESS_ROLES_ACCEPT_COURSE_ID = COURSE_ACCESS_ROLES_COURSE_ONLY + COURSE_ACCESS_ROLES_TENANT_OR_COURSE

COURSE_ACCESS_ROLES_UNSUPPORTED = [
    'library_user',  # not supported yet, it requires a library ID instead of a course ID
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
