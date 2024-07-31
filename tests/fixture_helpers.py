"""Fixtures for tests."""
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser


def get_user1_fx_permission_info():
    """Get permission information for user1."""
    return {
        'user': Mock(username='dummy'),
        'is_system_staff_user': True,
        'user_roles': [],
        'permitted_tenant_ids': [1, 2, 3, 4, 7, 8],
        'view_allowed_roles': [],
        'view_allowed_full_access_orgs': get_all_orgs(),
        'view_allowed_course_access_orgs': [],
    }


def get_all_orgs():
    """Get all test valid organizations."""
    return ['ORG1', 'ORG2', 'ORG3', 'ORG8', 'ORG4', 'ORG5']


def get_tenants_orgs(tenant_id):
    """Get test valid organizations for a tenants."""
    orgs = {
        1: ['ORG1', 'ORG2'],
        2: ['ORG3', 'ORG8'],
        3: ['ORG4', 'ORG5'],
        4: [],
        5: [],
        6: [],
        7: ['ORG3'],
        8: ['ORG8'],
    }
    result = set()
    for tenant in tenant_id:
        result.update(orgs[tenant])
    return list(result)


def set_user(request, user_id=1):
    """Set user for request."""
    if user_id is None:
        request.user = None
    elif user_id == 0:
        request.user = AnonymousUser()
    else:
        request.user = get_user_model().objects.get(id=user_id)


def get_test_data_dict():
    """Get the test data dictionary."""
    return {
        'user3': {
            'ORG1': {
                'None': ['staff'],
                'course-v1:ORG1+3+3': ['staff', 'org_course_creator_group'],
                'course-v1:ORG1+4+4': ['org_course_creator_group'],
            }
        },
        'user8': {
            'ORG2': {'None': ['staff'], 'course-v1:ORG2+3+3': ['org_course_creator_group']}
        },
        'user9': {
            'ORG3': {
                'None': ['staff', 'data_researcher'],
                'course-v1:ORG3+2+2': ['data_researcher'],
                'course-v1:ORG3+3+3': ['org_course_creator_group'],
            },
            'ORG2': {'course-v1:ORG2+1+1': ['staff'], 'course-v1:ORG2+3+3': ['staff']},
        },
        'user18': {'ORG3': {'None': ['staff'], 'course-v1:ORG3+3+3': ['staff']}},
        'user10': {
            'ORG4': {'None': ['staff']},
            'ORG3': {'None': ['data_researcher']},
        },
        'user23': {
            'ORG4': {'None': ['staff', 'org_course_creator_group']},
            'ORG5': {'None': ['staff', 'org_course_creator_group']},
            'ORG8': {'None': ['org_course_creator_group']},
        },
        'user4': {
            'ORG1': {'None': ['org_course_creator_group'], 'course-v1:ORG1+4+4': ['staff']},
            'ORG2': {'None': ['org_course_creator_group']},
            'ORG3': {
                'None': ['org_course_creator_group'],
                'course-v1:ORG3+1+1': ['staff', 'org_course_creator_group'],
            },
        },
        'user11': {
            'ORG3': {
                'course-v1:ORG3+2+2': ['org_course_creator_group'],
            }
        },
        'user48': {'ORG4': {'None': ['org_course_creator_group']}},
    }


def get_test_data_dict_without_course_roles():
    """Get the test data dictionary without course roles."""
    return {
        'user3': {
            'ORG1': {
                'None': ['staff'],
            }
        },
        'user8': {
            'ORG2': {'None': ['staff']}
        },
        'user9': {
            'ORG3': {
                'None': ['staff', 'data_researcher'],
            },
        },
        'user18': {'ORG3': {'None': ['staff']}},
        'user10': {
            'ORG4': {'None': ['staff']},
            'ORG3': {'None': ['data_researcher']},
        },
        'user23': {
            'ORG4': {'None': ['staff', 'org_course_creator_group']},
            'ORG5': {'None': ['staff', 'org_course_creator_group']},
            'ORG8': {'None': ['org_course_creator_group']},
        },
        'user4': {
            'ORG1': {'None': ['org_course_creator_group']},
            'ORG2': {'None': ['org_course_creator_group']},
            'ORG3': {
                'None': ['org_course_creator_group'],
            },
        },
        'user48': {'ORG4': {'None': ['org_course_creator_group']}}
    }


def get_test_data_dict_without_course_roles_org3():
    """Get the test data dictionary without course roles filtered on org3 and 8."""
    return {
        'user9': {
            'ORG3': {
                'None': ['staff', 'data_researcher'],
            },
        },
        'user18': {'ORG3': {'None': ['staff']}},
        'user10': {
            'ORG3': {'None': ['data_researcher']},
        },
        'user23': {
            'ORG8': {'None': ['org_course_creator_group']},
        },
        'user4': {
            'ORG3': {
                'None': ['org_course_creator_group'],
            },
        },
    }
