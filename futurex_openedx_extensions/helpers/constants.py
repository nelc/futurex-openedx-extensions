"""Constants for the FutureX Open edX Extensions app."""
CACHE_NAME_ALL_COURSE_ACCESS_ROLES = "all_course_access_roles"
CACHE_NAME_ALL_COURSE_ORG_FILTER_LIST = "all_course_org_filter_list_v2"
CACHE_NAME_ALL_TENANTS_INFO = "all_tenants_info_v2"
CACHE_NAME_ALL_VIEW_ROLES = "all_view_roles"

COURSE_ID_REGX = r"(?P<course_id>course-v1:(?P<org>[a-zA-Z0-9_]+)\+(?P<course>[a-zA-Z0-9_]+)\+(?P<run>[a-zA-Z0-9_]+))"


COURSE_STATUSES = {
    "active": "active",
    "archived": "archived",
    "upcoming": "upcoming",
}

COURSE_STATUS_SELF_PREFIX = "self_"

TENANT_LIMITED_ADMIN_ROLES = ["org_course_creator_group"]
