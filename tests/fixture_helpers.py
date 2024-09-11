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
        'permitted_tenant_ids': [1, 2, 3, 7, 8],
        'view_allowed_roles': [],
        'view_allowed_full_access_orgs': get_all_orgs(),
        'view_allowed_course_access_orgs': [],
    }


def get_all_orgs():
    """Get all test valid organizations."""
    return ['org1', 'org2', 'org3', 'org8', 'org4', 'org5']


def get_tenants_orgs(tenant_id):
    """Get test valid organizations for a tenants."""
    orgs = {
        1: ['org1', 'org2'],
        2: ['org3', 'org8'],
        3: ['org4', 'org5'],
        4: [],
        5: [],
        6: [],
        7: ['org3'],
        8: ['org8'],
    }
    result = set()
    for tenant in tenant_id:
        result.update(orgs[tenant])
    return list(result)


def get_tenants_of_org(org, base_data_tenant_config):
    """Get tenants of an organization."""
    result = set()
    for tenant_id, tenant_info in base_data_tenant_config.items():
        if isinstance(tenant_info['lms_configs']['course_org_filter'], str):
            _course_org_filter = [tenant_info['lms_configs']['course_org_filter']]
        else:
            _course_org_filter = tenant_info['lms_configs']['course_org_filter']
        for _org in _course_org_filter:
            if _org.lower() == org.lower():
                result.add(tenant_id)
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
            'org1': {
                'None': ['staff'],
                'course-v1:ORG1+3+3': ['staff', 'instructor'],
                'course-v1:ORG1+4+4': ['instructor'],
            }
        },
        'user8': {
            'org2': {'None': ['staff'], 'course-v1:ORG2+3+3': ['instructor']}
        },
        'user9': {
            'org3': {
                'None': ['staff', 'data_researcher'],
                'course-v1:ORG3+2+2': ['data_researcher'],
                'course-v1:ORG3+3+3': ['instructor'],
            },
            'org2': {'course-v1:ORG2+1+1': ['staff'], 'course-v1:ORG2+3+3': ['staff']},
        },
        'user18': {'org3': {'None': ['staff'], 'course-v1:ORG3+3+3': ['staff']}},
        'user10': {
            'org4': {'None': ['staff']},
            'org3': {'None': ['data_researcher']},
        },
        'user23': {
            'org4': {'None': ['staff', 'instructor']},
            'org5': {'None': ['staff', 'instructor']},
            'org8': {'None': ['instructor']},
        },
        'user4': {
            'org1': {'None': ['instructor'], 'course-v1:ORG1+4+4': ['staff']},
            'org2': {'None': ['instructor']},
            'org3': {
                'None': ['instructor'],
                'course-v1:ORG3+1+1': ['staff', 'instructor'],
            },
        },
        'user11': {
            'org3': {
                'course-v1:ORG3+2+2': ['instructor'],
            }
        },
        'user48': {'org4': {'None': ['instructor']}},
    }


def get_test_data_dict_without_course_roles():
    """Get the test data dictionary without course roles."""
    return {
        'user3': {
            'org1': {
                'None': ['staff'],
            }
        },
        'user8': {
            'org2': {'None': ['staff']}
        },
        'user9': {
            'org3': {
                'None': ['staff', 'data_researcher'],
            },
        },
        'user18': {'org3': {'None': ['staff']}},
        'user10': {
            'org4': {'None': ['staff']},
            'org3': {'None': ['data_researcher']},
        },
        'user23': {
            'org4': {'None': ['staff', 'instructor']},
            'org5': {'None': ['staff', 'instructor']},
            'org8': {'None': ['instructor']},
        },
        'user4': {
            'org1': {'None': ['instructor']},
            'org2': {'None': ['instructor']},
            'org3': {
                'None': ['instructor'],
            },
        },
        'user48': {'org4': {'None': ['instructor']}}
    }


def get_test_data_dict_without_course_roles_org3():
    """Get the test data dictionary without course roles filtered on org3 and 8."""
    return {
        'user9': {
            'org3': {
                'None': ['staff', 'data_researcher'],
            },
        },
        'user18': {'org3': {'None': ['staff']}},
        'user10': {
            'org3': {'None': ['data_researcher']},
        },
        'user23': {
            'org8': {'None': ['instructor']},
        },
        'user4': {
            'org3': {
                'None': ['instructor'],
            },
        },
    }
