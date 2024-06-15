"""Test integrity of base test data."""
from tests.base_test_data import _base_data


def test_certificate_must_be_enrolled():
    """Verify that certificates are issued only to enrolled users."""
    for org, courses in _base_data['certificates'].items():
        for course_id, user_ids in courses.items():
            for user_id in user_ids:
                assert user_id in _base_data['course_enrollments'].get(org, {}).get(course_id, []), (
                    f'User {user_id} is not enrolled in course {course_id} of org {org}'
                )


def test_staff_only():
    """Verify the list of users having is_staff set to True, but not is_superuser"""
    valid_list = [2]
    for user_id in _base_data["staff_users"]:
        if user_id in valid_list:
            assert user_id not in _base_data["super_users"], \
                f"User (user{user_id}) must be a staff user, but not a super user"
            valid_list.remove(user_id)
        else:
            assert user_id in _base_data["super_users"], \
                f"User (user{user_id}) must not be a staff user, or must be both a staff and a super user"

    assert not valid_list, f"These users must be staff users, but not found in the staff_users list: {valid_list}"


def test_super_only():
    """Verify the list of users having is_superuser set to True"""
    valid_list = [1]
    for user_id in _base_data["super_users"]:
        if user_id in valid_list:
            assert user_id not in _base_data["staff_users"], \
                f"User (user{user_id}) must be a super user, but not a staff user"
            valid_list.remove(user_id)
        else:
            assert user_id in _base_data["staff_users"], \
                f"User (user{user_id}) must not be a super user, or must be both a staff and a super user"

    assert not valid_list, f"These users must be super users, but not found in the super_users list: ({valid_list})"


def test_both_staff_and_super():
    """Verify the list of users having both is_staff and is_superuser set to True"""
    valid_list = [60]
    for user_id in _base_data["super_users"]:
        if user_id in valid_list:
            assert user_id in _base_data["staff_users"], \
                f"User (user{user_id}) must be both a staff and a super user"
            valid_list.remove(user_id)
        else:
            assert user_id not in _base_data["staff_users"], \
                f"User (user{user_id}) must not be both a staff and a super user"

    assert not valid_list, \
        f"These users must be both a staff and a super user, but not found in the super_users list: {valid_list}"
