"""Test integrity of base test data."""
from futurex_openedx_extensions.helpers.tenants import TENANT_LIMITED_ADMIN_ROLES
from tests.base_test_data import _base_data


def test_at_least_one_no_admin_role():
    """Verify that at least one tenant has no admin role."""
    assert len([role for role in _base_data['course_access_roles'] if role in TENANT_LIMITED_ADMIN_ROLES]) > 0, (
        'At least one tenant should have an admin role'
    )


def test_certificate_must_be_enrolled():
    """Verify that certificates are issued only to enrolled users."""
    for org, courses in _base_data['certificates'].items():
        for course_id, user_ids in courses.items():
            for user_id in user_ids:
                assert user_id in _base_data['course_enrollments'].get(org, {}).get(course_id, []), (
                    f'User {user_id} is not enrolled in course {course_id} of org {org}'
                )
