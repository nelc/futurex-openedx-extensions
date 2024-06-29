"""Fixtures for tests."""
from unittest.mock import Mock


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
