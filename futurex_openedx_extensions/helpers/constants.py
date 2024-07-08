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

COURSE_ID_REGX = r'(?P<course_id>course-v1:(?P<org>[a-zA-Z0-9_]+)\+(?P<course>[a-zA-Z0-9_]+)\+(?P<run>[a-zA-Z0-9_]+))'


COURSE_STATUSES = {
    'active': 'active',
    'archived': 'archived',
    'upcoming': 'upcoming',
}

COURSE_STATUS_SELF_PREFIX = 'self_'

TENANT_LIMITED_ADMIN_ROLES = ['org_course_creator_group']
