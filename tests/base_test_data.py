"""Base test data for the tests. dictionary instead of json file."""

_base_data = {
    "tenant_config": {
        1: {  # Organisations are duplicated with tenant 4 and 6
            "lms_configs": {
                "LMS_BASE": "s1.sample.com",
                "SITE_NAME": "s1.sample.com",
                "course_org_filter": ["ORG1", "ORG2"],
            },
        },
        2: {  # Organisation is duplicated with tenant 7
            "lms_configs": {
                "LMS_BASE": "s2.sample.com",
                "course_org_filter": ["ORG3", "ORG8"],
            },
        },
        3: {
            "lms_configs": {
                "SITE_NAME": "s3.sample.com",
                "course_org_filter": ["ORG4", "ORG5"],
            },
        },
        4: {  # This is a tenant with no SITE_NAME nor LMS_BASE
            "lms_configs": {
                "LMS_BASE": None,
                "SITE_NAME": None,
                "course_org_filter": ["ORG1", "ORG2"],
            },
        },
        5: {  # This is a tenant with no course_org_filter
            "lms_configs": {
                "LMS_BASE":  "s5.sample.com",
                "SITE_NAME":  "s5.sample.com",
                "course_org_filter": [],
            },
        },
        6: {  # This is a tenant with no route
            "lms_configs": {
                "LMS_BASE": "s6.sample.com",
                "course_org_filter": ["ORG2"],
            },
        },
        7: {
            "lms_configs": {
                "LMS_BASE": "s7.sample.com",
                "course_org_filter": "ORG3",  # This a string, not a list, it should be fine too
            },
        },
        8: {
            "lms_configs": {
                "LMS_BASE": "s8.sample.com",
                "SITE_NAME": "s8.sample.com",
                "course_org_filter": ["ORG8"],
            },
        },
    },
    "routes": {
        1: {
            "domain": "s1.sample.com",
            "config_id": 1,
        },
        2: {
            "domain": "s2.sample.com",
            "config_id": 2,
        },
        3: {
            "domain": "s3.sample.com",
            "config_id": 3,
        },
        4: {
            "domain": "s4.sample.com",
            "config_id": 4,
        },
        5: {
            "domain": "s5.sample.com",
            "config_id": 5,
        },
        7: {
            "domain": "s7.sample.com",
            "config_id": 7,
        },
        8: {
            "domain": "s8.sample.com",
            "config_id": 8,
        },
    },
    "users_count": 55,
    "user_signup_source__users": {
        "s1.sample.com": [1, 2, 3, 4, 5],
        "s2.sample.com": [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
        "s3.sample.com": [15, 16, 17, 18, 19, 20],
        "s4.sample.com": [21, 22, 23, 24, 25, 26, 27],
        "s5.sample.com": [21, 22, 23, 24, 25, 26, 27],
        "s6.sample.com": [28, 29, 30, 31, 32, 33, 34, 35, 36, 37],
        "s7.sample.com": [15, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50],
        "s8.sample.com": [47, 48, 49, 50, 51, 52, 53, 54, 55],
        "dah.sample.com": [1, 2, 3, 4, 5],  # This is not a valid domain
    },
    "course_overviews": {  # count of courses per org
        "ORG1": 5,
        "ORG2": 7,
        "ORG3": 3,
        "ORG4": 1,
        "ORG5": 0,
        "ORG6": 1,  # This is an org with no tenant
        "ORG8": 2,
    },
    "course_enrollments": {  # org id, course id, user ids
        "ORG1": {
            1: [4, 5],
            2: [3],
            3: [],
            4: [4],
            5: [1, 2, 3, 4, 15, 21, 40],
        },
        "ORG2": {
            1: [2],
            3: [1, 2, 3],
            4: [4, 5, 21, 22, 23, 24, 25],
            5: [21, 22, 23, 24, 25],
            6: [28, 29, 30, 31, 32],
            7: [15, 38, 39, 40, 41],
        },
        "ORG3": {
            1: [10, 40, 41, 42, 43, 44],
            2: [45, 46, 47, 48, 49],
            3: [7, 8, 9, 10, 11, 12],
        },
        "ORG4": {
            1: [1, 2, 15, 16, 17, 18],
        },
        "ORG6": {
            1: [30, 31, 32, 41, 42],
        },
        "ORG8": {
            1: [47, 48, 49, 52],
            2: [23, 52, 53, 54],
        },
    },
    "super_users": [1],
    "staff_users": [2],
    "course_access_roles": {  # roles, user ids per org
        "staff": {  # at least one role that is not in TENANT_LIMITED_ADMIN_ROLES
            "ORG1": [3],
            "ORG2": [8, 9],
            "ORG3": [9, 18],
            "ORG4": [10, 23],
            "ORG5": [23],
        },
        "org_course_creator_group": {
            "ORG1": [4],
            "ORG2": [1, 2, 4, 9],
            "ORG3": [4, 10, 11],
            "ORG4": [23, 48],
            "ORG5": [23],
            "ORG8": [23],
        },
    },
    "ignored_course_access_roles": {
        "no_org": {
            "staff": [10, 30, 40, 41],
            "org_course_creator_group": [24, 40, 42],
        },
    },
    "certificates": {  # org id, course id, user ids
        "ORG1": {
            5: [2, 3, 4, 40],
        },
        "ORG2": {
            4: [4, 5, 24, 25],
            5: [21, 24, 25],
            7: [15, 40, 41],
        },
        "ORG3": {
            1: [42, 43, 44],
            2: [48, 49],
            3: [8, 9],
        },
        "ORG4": {
        },
        "ORG6": {
            1: [30, 42],
        },
        "ORG8": {
            1: [49, 52],
        },
    },
}

expected_statistics = {
    '1': {'certificates_count': 14, 'courses_count': 12, 'learners_count': 17},
    '2': {'certificates_count': 9, 'courses_count': 5, 'learners_count': 21},
    '3': {'certificates_count': 0, 'courses_count': 1, 'learners_count': 6},
    '7': {'certificates_count': 7, 'courses_count': 3, 'learners_count': 17},
    '8': {'certificates_count': 2, 'courses_count': 2, 'learners_count': 9},
    'total_certificates_count': 32,
    'total_courses_count': 23,
    'total_learners_count': 70
}
