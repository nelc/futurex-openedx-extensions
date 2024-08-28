"""Constants for the FutureX Open edX Extensions app."""
CACHE_NAME_ALL_COURSE_ACCESS_ROLES = 'fx_course_access_roles'
CACHE_NAME_ALL_COURSE_ORG_FILTER_LIST = 'fx_course_org_filter_list'
CACHE_NAME_ALL_TENANTS_INFO = 'fx_tenants_info'
CACHE_NAME_ALL_VIEW_ROLES = 'fx_view_roles'

CACHE_NAMES = {
    CACHE_NAME_ALL_COURSE_ACCESS_ROLES: {
        'short_description': 'Course Access Roles',
        'long_description': 'Information about all course access roles for all permitted users',
    },
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

ALLOWED_NEW_COURSE_ACCESS_ROLES = [
    'beta_testers',
    'ccx_coach',
    'course_creator_group',
    'data_researcher',
    'finance_admin',
    'instructor',
    'library_user',
    'org_course_creator_group',
    'staff',
    'support',
]

COURSE_ACCESS_ROLES_MAX_USERS_PER_OPERATION = 20

USER_KEY_TYPE_ID = 'ID'
USER_KEY_TYPE_USERNAME = 'username'
USER_KEY_TYPE_EMAIL = 'email'
USER_KEY_TYPE_NOT_ID = 'username/email'
