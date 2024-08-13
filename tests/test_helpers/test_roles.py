"""Test permissions helper classes"""
from unittest.mock import Mock, patch

import pytest
from common.djangoapps.student.models import CourseAccessRole
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from opaque_keys.edx.django.models import CourseKeyField

from futurex_openedx_extensions.helpers.constants import CACHE_NAME_ALL_COURSE_ACCESS_ROLES
from futurex_openedx_extensions.helpers.models import ViewAllowedRoles
from futurex_openedx_extensions.helpers.roles import (
    FXViewRoleInfoMetaClass,
    FXViewRoleInfoMixin,
    RoleType,
    check_tenant_access,
    get_all_course_access_roles,
    get_course_access_roles_queryset,
    get_fx_view_with_roles,
    get_usernames_with_access_roles,
    is_valid_course_access_role,
    is_view_exist,
    is_view_support_write,
    optimize_access_roles_result,
)
from tests.fixture_helpers import (
    get_all_orgs,
    get_test_data_dict,
    get_test_data_dict_without_course_roles,
    get_test_data_dict_without_course_roles_org3,
)


class FXViewRoleInfoMetaClassTestView(metaclass=FXViewRoleInfoMetaClass):  # pylint: disable=too-few-public-methods
    """Mock class to use FXViewRoleInfoMetaClass."""


@pytest.fixture(autouse=True)
def reset_fx_views_with_roles():
    """Reset the _fx_views_with_roles dictionary before each test."""
    FXViewRoleInfoMetaClass._fx_views_with_roles = {'_all_view_names': {}}  # pylint: disable=protected-access


@pytest.mark.parametrize('course_access_role, error_msg', [
    ({
        'id': 99,
        'org': '',
        'course_id': '',
        'course_org': None,
    }, ('Invalid course access role (both course_id and org are empty!): id=%s', 99)),
    ({
        'id': 99,
        'org': '',
        'course_id': 'course-v1:ORG1+1+1',
        'course_org': 'ORG1',
    }, ('Invalid course access role (course_id with no org!): id=%s', 99)),
    ({
        'id': 99,
        'org': 'ORG2',
        'course_id': 'course-v1:ORG1+1+1',
        'course_org': 'ORG1',
    }, ('Invalid course access role (org mismatch!): id=%s', 99)),
])
def test_is_valid_course_access_role_invalid(course_access_role, error_msg):
    """Verify that is_valid_course_access_role returns False and logs an error if the access role record is invalid."""
    with patch('futurex_openedx_extensions.helpers.roles.logger.error') as mock_logger:
        assert is_valid_course_access_role(course_access_role) is False
        mock_logger.assert_called_with(*error_msg)
    assert is_valid_course_access_role(course_access_role) is False


def test_optimize_access_roles_result():
    """Verify that optimize_access_roles_result removes courses not in org from the access roles."""
    access_roles = {
        1: {
            'whatever1': {
                'orgs_full_access': ['ORG1'], 'course_limited_access': ['course-v1:ORG1+1+1', 'course2']
            },
            'whatever2': {
                'orgs_full_access': ['ORG3'], 'course_limited_access': ['course-v1:ORG1+1+1']
            },
            'whatever3': {
                'orgs_full_access': ['ORG1'], 'course_limited_access': ['course2', 'course-v1:ORG2+2+2']
            },
        },
        2: {
            'staff': {
                'orgs_full_access': [], 'course_limited_access': ['course-v1:ORG1+1+1']},
            'admin': {
                'orgs_full_access': ['ORG2'], 'course_limited_access': ['course-v1:ORG1+1+1', 'course2']
            },
        },
    }
    course_org = {
        'course-v1:ORG1+1+1': 'ORG1',
        'course-v1:ORG2+2+2': 'ORG2',
        'course2': 'ORG2',
    }
    optimize_access_roles_result(access_roles, course_org)
    assert access_roles == {
        1: {
            'whatever1': {
                'orgs_full_access': ['ORG1'], 'course_limited_access': ['course2'], 'orgs_of_courses': ['ORG2']
            },
            'whatever2': {
                'orgs_full_access': ['ORG3'],
                'course_limited_access': ['course-v1:ORG1+1+1'],
                'orgs_of_courses': ['ORG1'],
            },
            'whatever3': {
                'orgs_full_access': ['ORG1'],
                'course_limited_access': ['course2', 'course-v1:ORG2+2+2'],
                'orgs_of_courses': ['ORG2'],
            },
        },
        2: {
            'staff': {
                'orgs_full_access': [], 'course_limited_access': ['course-v1:ORG1+1+1'], 'orgs_of_courses': ['ORG1']
            },
            'admin': {
                'orgs_full_access': ['ORG2'],
                'course_limited_access': ['course-v1:ORG1+1+1'],
                'orgs_of_courses': ['ORG1'],
            },
        },
    }


def _remove_course_access_roles_causing_error_logs():
    """Remove bad course access roles."""
    CourseAccessRole.objects.filter(course_id=CourseKeyField.Empty, org='').delete()


@pytest.mark.django_db
@pytest.mark.parametrize('verify_attribute', ['is_staff', 'is_superuser', 'is_active'])
def test_get_all_course_access_roles_ignores_inactive_and_system_admins(
    base_data, verify_attribute
):  # pylint: disable=unused-argument
    """Verify that get_all_course_access_roles ignores inactive users and system admins."""
    _remove_course_access_roles_causing_error_logs()
    user = get_user_model().objects.filter(
        id=3,
        is_staff=False,
        is_superuser=False,
        is_active=True,
    ).first()
    expected_result = {
        'staff': {
            'orgs_full_access': ['ORG1'],
            'course_limited_access': [],
            'orgs_of_courses': []
        },
        'org_course_creator_group': {
            'orgs_full_access': [],
            'course_limited_access': ['course-v1:ORG1+3+3', 'course-v1:ORG1+4+4'],
            'orgs_of_courses': ['ORG1']
        }
    }
    assert user is not None, 'Bad test data, user 3 should be an active non-staff user'
    assert get_all_course_access_roles()[3] == expected_result

    setattr(user, verify_attribute, not getattr(user, verify_attribute))
    user.save()
    assert get_all_course_access_roles().get(3) is None

    setattr(user, verify_attribute, not getattr(user, verify_attribute))
    user.save()
    assert get_all_course_access_roles()[3] == expected_result


@pytest.mark.django_db
def test_get_all_course_access_roles(base_data):  # pylint: disable=unused-argument
    """Verify that get_all_course_access_roles returns the expected structure."""
    _remove_course_access_roles_causing_error_logs()
    expected_result = {
        'staff': {
            'orgs_full_access': ['ORG1'],
            'course_limited_access': [],
            'orgs_of_courses': []
        },
        'org_course_creator_group': {
            'orgs_full_access': [],
            'course_limited_access': ['course-v1:ORG1+3+3', 'course-v1:ORG1+4+4'],
            'orgs_of_courses': ['ORG1']
        }
    }
    assert get_all_course_access_roles()[3] == expected_result
    CourseAccessRole.objects.create(
        user_id=3,
        role='staff',
        org='ORG1',
        course_id='course-v1:ORG2+1+1',
    )
    CourseAccessRole.objects.create(
        user_id=3,
        role='staff',
        org='ORG2',
        course_id='course-v1:ORG2+2+2',
    )

    expected_result['staff']['orgs_of_courses'] = ['ORG2']
    expected_result['staff']['course_limited_access'] = ['course-v1:ORG2+2+2']
    assert get_all_course_access_roles()[3] == expected_result


@pytest.mark.django_db
@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
def test_get_all_course_access_roles_being_cached():
    """Verify that get_all_course_access_roles is being cached."""
    assert cache.get(CACHE_NAME_ALL_COURSE_ACCESS_ROLES) is None
    result = get_all_course_access_roles()
    assert cache.get(CACHE_NAME_ALL_COURSE_ACCESS_ROLES)['data'] == result
    cache.set(CACHE_NAME_ALL_COURSE_ACCESS_ROLES, None)


@pytest.mark.django_db
@pytest.mark.parametrize('user_id, ids_to_check, expected', [
    (1, '1,2,3,7', (True, {'tenant_ids': [1, 2, 3, 7]})),
    (2, '1,2,3,7', (True, {'tenant_ids': [1, 2, 3, 7]})),
    (3, '1,2,3,7', (
        False, {
            'details': {'tenant_ids': [2, 3, 7]},
            'reason': 'User does not have access to these tenants'
        }
    )),
    (1, '1,7,9', (
        False, {
            'details': {'tenant_ids': [9]},
            'reason': 'Invalid tenant IDs provided'
        }
    )),
    (1, '1,2,E,7', (
        False, {
            'details': {'error': 'invalid literal for int() with base 10: \'E\''},
            'reason': 'Invalid tenant IDs provided. It must be a comma-separated list of integers'
        }
    )),
])
def test_check_tenant_access(base_data, user_id, ids_to_check, expected):  # pylint: disable=unused-argument
    """Verify check_tenant_access function."""
    user = get_user_model().objects.get(id=user_id)
    result = check_tenant_access(user, ids_to_check)
    assert result == expected


def test_fx_view_role_metaclass__view_name_missing():
    """Verify that an error is logged if the view name is not defined."""
    with patch('futurex_openedx_extensions.helpers.roles.logger') as mock_logger:
        class TestView(FXViewRoleInfoMetaClassTestView):  # pylint: disable=too-few-public-methods, unused-variable
            fx_view_name = ''
            fx_view_description = 'A test view'
            fx_default_read_only_roles = ['role1', 'role2']

    mock_logger.error.assert_called_with('fx_view_name is not defined for view (%s)', 'TestView')


def test_fx_view_role_metaclass_view_name_length_exceeded():
    """Verify that an error is logged if the view name length exceeds 255 characters."""
    long_name = 'x' * 256
    with patch('futurex_openedx_extensions.helpers.roles.logger') as mock_logger:
        class TestView(FXViewRoleInfoMetaClassTestView):  # pylint: disable=too-few-public-methods, unused-variable
            fx_view_name = long_name
            fx_view_description = 'A test view'
            fx_default_read_only_roles = ['role1', 'role2']

    mock_logger.error.assert_called_with(
        'fx_view_name and fx_view_description length must be below 256 characters (%s)', 'TestView')


def test_fx_view_role_metaclass_view_description_length_exceeded():
    """Verify that an error is logged if the view description length exceeds 255 characters."""
    long_description = 'x' * 256
    with patch('futurex_openedx_extensions.helpers.roles.logger') as mock_logger:
        class TestView(FXViewRoleInfoMetaClassTestView):  # pylint: disable=too-few-public-methods, unused-variable
            fx_view_name = 'TestView'
            fx_view_description = long_description
            fx_default_read_only_roles = ['role1', 'role2']

    mock_logger.error.assert_called_with(
        'fx_view_name and fx_view_description length must be below 256 characters (%s)', 'TestView',
    )


def test_fx_view_role_metaclass_view_name_duplicate():
    """Verify that an error is logged if the view name is a duplicate."""
    class FirstView(FXViewRoleInfoMetaClassTestView):  # pylint: disable=too-few-public-methods, unused-variable
        fx_view_name = 'TestView'
        fx_view_description = 'First test view'
        fx_default_read_only_roles = ['role1']

    with patch('futurex_openedx_extensions.helpers.roles.logger') as mock_logger:
        class SecondView(FXViewRoleInfoMetaClassTestView):  # pylint: disable=too-few-public-methods, unused-variable
            fx_view_name = 'TestView'
            fx_view_description = 'Second test view'
            fx_default_read_only_roles = ['role2']

    mock_logger.error.assert_called_with('fx_view_name duplicate between (%s) and another view', 'SecondView')


def test_fx_view_role_metaclass_adding_view_to_fx_views_with_roles():
    """Verify that the view is added to the _fx_views_with_roles dictionary."""
    class TestView(FXViewRoleInfoMetaClassTestView):  # pylint: disable=too-few-public-methods
        """Test view class."""
        fx_view_name = 'UniqueView'
        fx_view_description = 'A unique test view'
        fx_default_read_only_roles = ['role1', 'role2']

    assert 'TestView' in TestView._fx_views_with_roles  # pylint: disable=protected-access
    assert TestView._fx_views_with_roles['TestView'] == {  # pylint: disable=protected-access
        'name': 'UniqueView',
        'description': 'A unique test view',
        'default_read_only_roles': ['role1', 'role2'],
        'default_read_write_roles': [],
    }
    assert 'UniqueView' in TestView._fx_views_with_roles['_all_view_names']  # pylint: disable=protected-access


def test_fx_view_role_metaclass_bad_duplicate_class_definition():
    """Verify that duplicate class definitions are logged as errors, and included in get_fx_view_with_roles result."""
    class DuplicateClassDefinition(
        FXViewRoleInfoMetaClassTestView
    ):  # pylint: disable=too-few-public-methods, missing-class-docstring
        fx_view_name = 'TestView_1'
        fx_view_description = 'A test view'
        fx_default_read_only_roles = ['role1', 'role2']

    expected_result = {
        'DuplicateClassDefinition': {
            'name': 'TestView_1',
            'description': 'A test view',
            'default_read_only_roles': ['role1', 'role2'],
            'default_read_write_roles': [],
        },
        '_all_view_names': {'TestView_1': DuplicateClassDefinition},
    }

    with patch('futurex_openedx_extensions.helpers.roles.logger') as mock_logger:
        class DuplicateClassDefinition(
            FXViewRoleInfoMetaClassTestView
        ):  # pylint: disable=function-redefined, too-few-public-methods, missing-class-docstring
            fx_view_name = 'TestView_2'
            fx_view_description = 'A test view'
            fx_default_read_only_roles = ['role1', 'role5']

    assert get_fx_view_with_roles() == expected_result
    mock_logger.error.assert_called_with(
        'FXViewRoleInfoMetaClass error: Unexpected class redefinition (%s)', 'DuplicateClassDefinition'
    )


def test_fx_view_role_metaclass_get_fx_view_with_roles():
    """Verify that get_fx_view_with_roles returns the expected dictionary."""
    class TestView1(FXViewRoleInfoMetaClassTestView):  # pylint: disable=too-few-public-methods
        fx_view_name = 'TestView_1'
        fx_view_description = 'A test view'
        fx_default_read_only_roles = ['role1', 'role2']

    class TestView2(FXViewRoleInfoMetaClassTestView):  # pylint: disable=too-few-public-methods
        fx_view_name = 'TestView_2'
        fx_view_description = 'A test view'
        fx_default_read_only_roles = ['role1', 'role5']

    assert get_fx_view_with_roles() == {
        'TestView1': {
            'name': 'TestView_1',
            'description': 'A test view',
            'default_read_only_roles': ['role1', 'role2'],
            'default_read_write_roles': [],
        },
        'TestView2': {
            'name': 'TestView_2',
            'description': 'A test view',
            'default_read_only_roles': ['role1', 'role5'],
            'default_read_write_roles': [],
        },
        '_all_view_names': {'TestView_1': TestView1, 'TestView_2': TestView2},
    }


def test_fx_view_role_metaclass_get_methods():
    """Verify that the get_read_methods and get_write_methods methods return the expected values."""
    assert FXViewRoleInfoMetaClass.get_read_methods() == ['GET', 'HEAD', 'OPTIONS']
    assert FXViewRoleInfoMetaClass.get_write_methods() == ['POST', 'PUT', 'PATCH', 'DELETE']


def test_fx_view_role_metaclass_check_allowed_read_methods(caplog):
    """Verify that check_allowed_read_methods returns the expected value."""
    error_message = 'fx_allowed_read_methods contains invalid methods (TestView)'

    with patch(
        'futurex_openedx_extensions.helpers.roles.FXViewRoleInfoMetaClass.get_read_methods',
        return_value=['GET']
    ):
        class TestView(FXViewRoleInfoMetaClass):
            fx_view_name = 'TestView'
            fx_view_description = 'A test view'
            fx_allowed_read_methods = ['GET']
        assert TestView.check_allowed_read_methods() is True

        assert error_message not in caplog.text
        TestView.fx_allowed_read_methods = ['POST']
        assert TestView.check_allowed_read_methods() is False
        assert error_message in caplog.text


def test_fx_view_role_metaclass_check_allowed_write_methods(caplog):
    """Verify that check_allowed_write_methods returns the expected value."""
    error_message = 'fx_allowed_write_methods contains invalid methods (TestView)'

    with patch(
        'futurex_openedx_extensions.helpers.roles.FXViewRoleInfoMetaClass.get_write_methods',
        return_value=['POST']
    ):
        class TestView(FXViewRoleInfoMetaClass):
            fx_view_name = 'TestView'
            fx_view_description = 'A test view'
            fx_allowed_write_methods = ['POST']
        assert TestView.check_allowed_write_methods() is True

        assert error_message not in caplog.text
        TestView.fx_allowed_write_methods = ['GET']
        assert TestView.check_allowed_write_methods() is False
        assert error_message in caplog.text


def test_fx_view_role_metaclass_is_write_supported():
    """Verify that is_write_supported returns the expected value."""
    class TestView(FXViewRoleInfoMetaClass):
        fx_view_name = 'TestView'
        fx_view_description = 'A test view'
    assert TestView.is_write_supported() is False

    TestView.fx_allowed_write_methods = ['ANYTHING']
    assert TestView.is_write_supported() is True


def test_is_view_exist():
    """Verify that is_view_exist returns the expected value."""
    assert is_view_exist('TestView') is False

    with patch(
        'futurex_openedx_extensions.helpers.roles.get_fx_view_with_roles',
        return_value={'_all_view_names': {'TestView': Mock()}}
    ):
        assert is_view_exist('TestView') is True


def test_is_view_support_write_nonexistent_view():
    """Verify that is_view_support_write returns the expected value for a nonexistent view."""
    assert is_view_support_write('non-existing_dummy_view') is False


@pytest.mark.parametrize('flag_value', [True, False])
def test_is_view_support_write(flag_value):
    """Verify that is_view_support_write returns the expected value."""
    class TestView(FXViewRoleInfoMetaClass):
        fx_view_name = 'TestView'
    with patch(
        'futurex_openedx_extensions.helpers.roles.get_fx_view_with_roles',
        return_value={'_all_view_names': {'TestView': TestView}}
    ):
        with patch.object(TestView, 'is_write_supported') as mock_is_write_supported:
            mock_is_write_supported.return_value = flag_value
            assert is_view_support_write('TestView') is flag_value


def _fill_default_fx_views_with_roles():
    """Fill the _fx_views_with_roles dictionary with default values."""
    FXViewRoleInfoMetaClass._fx_views_with_roles = {  # pylint: disable=protected-access
        '_all_view_names': {'View1': None, 'View2': None},
        'View1Class': {
            'name': 'View1',
            'description': 'Desc1',
            'default_read_only_roles': ['role1'],
            'default_read_write_roles': [],
        },
        'View2Class': {
            'name': 'View2',
            'description': 'Desc2',
            'default_read_only_roles': ['role1', 'role2'],
            'default_read_write_roles': [],
        }
    }


def test_fx_view_role_mixin_get_allowed_roles_no_existing_roles(db):  # pylint: disable=unused-argument
    """Verify that get_allowed_roles_all_views returns the expected dictionary and creates needed records."""
    _fill_default_fx_views_with_roles()
    assert ViewAllowedRoles.objects.count() == 0

    mixin = FXViewRoleInfoMixin()
    result = mixin.get_allowed_roles_all_views()

    assert result == {
        'View1': ['role1'],
        'View2': ['role1', 'role2'],
    }
    assert ViewAllowedRoles.objects.count() == 3
    assert ViewAllowedRoles.objects.filter(view_name='View1', allowed_role='role1').exists()
    assert ViewAllowedRoles.objects.filter(view_name='View2', allowed_role='role1').exists()
    assert ViewAllowedRoles.objects.filter(view_name='View2', allowed_role='role2').exists()


def test_fx_view_role_mixin_get_allowed_roles_with_existing_roles(db):  # pylint: disable=unused-argument
    """
    Verify that get_allowed_roles_all_views returns the expected dictionary without creating new records when
    records already exist.
    """
    _fill_default_fx_views_with_roles()
    assert ViewAllowedRoles.objects.count() == 0

    ViewAllowedRoles.objects.create(view_name='View1', view_description='Desc1', allowed_role='role1')
    ViewAllowedRoles.objects.create(view_name='View2', view_description='Desc2', allowed_role='role2')

    mixin = FXViewRoleInfoMixin()
    result = mixin.get_allowed_roles_all_views()

    assert result == {
        'View1': ['role1'],
        'View2': ['role2'],
    }
    assert ViewAllowedRoles.objects.count() == 2
    assert ViewAllowedRoles.objects.filter(view_name='View1', allowed_role='role1').exists()
    assert ViewAllowedRoles.objects.filter(view_name='View2', allowed_role='role2').exists()


def test_fx_view_role_mixin_get_allowed_roles_with_nonexistent_view(db):  # pylint: disable=unused-argument
    """
    Verify that get_allowed_roles_all_views returns the expected dictionary after removing records
    for nonexistent views.
    """
    FXViewRoleInfoMetaClass._fx_views_with_roles = {  # pylint: disable=protected-access
        '_all_view_names': {'View1': None, 'View2': None},
    }
    assert ViewAllowedRoles.objects.count() == 0

    ViewAllowedRoles.objects.create(view_name='View1', view_description='Desc1', allowed_role='role1')
    ViewAllowedRoles.objects.create(view_name='View1', view_description='Desc1', allowed_role='role4')
    ViewAllowedRoles.objects.create(view_name='View2', view_description='Desc2', allowed_role='role2')

    FXViewRoleInfoMetaClass._fx_views_with_roles['_all_view_names'] = {  # pylint: disable=protected-access
        'View1': None
    }

    mixin = FXViewRoleInfoMixin()
    result = mixin.get_allowed_roles_all_views()

    assert result == {
        'View1': ['role1', 'role4'],
    }
    assert ViewAllowedRoles.objects.count() == 2
    assert not ViewAllowedRoles.objects.filter(view_name='View2').exists()
    assert ViewAllowedRoles.objects.filter(view_name='View1', allowed_role='role1').exists()
    assert ViewAllowedRoles.objects.filter(view_name='View1', allowed_role='role4').exists()


def test_fx_view_role_mixin_fx_permission_info_not_available():
    """Verify that fx_permission_info returns the expected value."""
    def ensure_no_fx_permission_info():
        """Ensure that the request object has no fx_permission_info attribute."""
        delattr(mixin.request, 'fx_permission_info')  # pylint: disable=literal-used-as-attribute
    mixin = FXViewRoleInfoMixin()
    mixin.request = Mock()
    ensure_no_fx_permission_info()
    assert isinstance(mixin.fx_permission_info, dict)
    assert not mixin.fx_permission_info


def test_fx_view_role_mixin_fx_permission_info_available():
    """Verify that fx_permission_info returns the expected value."""
    mixin = FXViewRoleInfoMixin()
    mixin.request = Mock(fx_permission_info={'dummy': ['data']})
    assert mixin.fx_permission_info == {'dummy': ['data']}


@pytest.mark.django_db
def test_get_usernames_with_access_roles(base_data):  # pylint: disable=unused-argument
    """Verify that get_usernames_with_access_roles returns the expected value."""
    user3 = get_user_model().objects.get(username='user3')
    assert user3.is_active is True
    expected_result = ['user1', 'user2', 'user3', 'user4', 'user8', 'user9', 'user60']

    assert set(get_usernames_with_access_roles(['ORG1', 'ORG2'])) == set(expected_result)

    user3.is_active = False
    user3.save()
    expected_result.remove('user3')
    assert set(get_usernames_with_access_roles(['ORG1', 'ORG2'], active_filter=True)) == set(expected_result)
    assert get_usernames_with_access_roles(['ORG1', 'ORG2'], active_filter=False) == ['user3']


def test_role_types():
    """Verify that the role types are as expected."""
    assert RoleType.ORG_WIDE == RoleType('org_wide')
    assert RoleType.COURSE_SPECIFIC == RoleType('course_specific')
    assert len(RoleType) == 2, 'Unexpected number of role types, if this class is updated, then the logic of ' \
                               'get_course_access_roles_queryset should be updated as well'


@pytest.mark.parametrize('bad_role_type, expected_error_message', [
    ('bad_name', 'Invalid exclude_role_type: bad_name'),
    ('', 'Invalid exclude_role_type: EmptyString'),
    (['not string and not RoleType'], 'Invalid exclude_role_type: [\'not string and not RoleType\']'),
])
def test_get_roles_for_users_queryset_bad_exclude(bad_role_type, expected_error_message):
    """Verify that get_roles_for_users_queryset raises an error if the exclude parameter is invalid."""
    with pytest.raises(TypeError) as exc_info:
        get_course_access_roles_queryset(
            orgs_filter=['ORG1', 'ORG2'],
            remove_redundant=False,
            exclude_role_type=bad_role_type,
        )
    assert str(exc_info.value) == expected_error_message


def test_get_roles_for_users_queryset_bad_course_id():
    """Verify that get_roles_for_users_queryset raises an error if the course_id parameter is invalid."""
    with pytest.raises(ValueError) as exc_info:
        get_course_access_roles_queryset(
            orgs_filter=['ORG1', 'ORG2'],
            remove_redundant=False,
            course_ids_filter=['course-v1:ORG1+999+999', 'course-v1:ORG1+bad_course_id', 'course-v1:ORG1+99+99'],
        )
    assert str(exc_info.value) == 'Invalid course ID format: course-v1:ORG1+bad_course_id'


def roles_records_to_dict(records):
    """Convert the roles records to a dictionary."""
    result = {
        record.user.username: {} for record in records
    }
    for record in records:
        result[record.user.username][record.org] = {}
    for record in records:
        result[record.user.username][record.org][str(record.course_id or 'None')] = []
    for record in records:
        result[record.user.username][record.org][str(record.course_id or 'None')].append(record.role)

    return result


@pytest.mark.django_db
def test_assert_roles_test_data():
    """Verify that the test data is as expected."""
    records = CourseAccessRole.objects.filter(user__is_superuser=False, user__is_staff=False).exclude(org='')

    assert roles_records_to_dict(records) == get_test_data_dict()


@pytest.mark.django_db
def test_get_roles_for_users_queryset_simple(base_data):  # pylint: disable=unused-argument
    """Verify that get_roles_for_users_queryset returns the expected queryset."""
    result = get_course_access_roles_queryset(orgs_filter=get_all_orgs(), remove_redundant=False)

    assert roles_records_to_dict(result) == get_test_data_dict()


@pytest.mark.django_db
def test_get_roles_for_users_queryset_search_text(base_data):  # pylint: disable=unused-argument
    """Verify that get_roles_for_users_queryset returns the expected queryset when search_text is used."""
    test_orgs = get_all_orgs()
    result = get_course_access_roles_queryset(orgs_filter=test_orgs, remove_redundant=False, search_text='user4')

    assert roles_records_to_dict(result) == {
        'user4': get_test_data_dict()['user4'],
        'user48': get_test_data_dict()['user48'],
    }


@pytest.mark.django_db
def test_get_roles_for_users_queryset_active(base_data):  # pylint: disable=unused-argument
    """Verify that get_roles_for_users_queryset returns the expected queryset when active_filter is used."""
    test_orgs = get_all_orgs()
    expected_data = get_test_data_dict()
    result = get_course_access_roles_queryset(orgs_filter=test_orgs, remove_redundant=False)
    assert roles_records_to_dict(result) == expected_data

    user3 = get_user_model().objects.get(username='user3')
    user3.is_active = False
    user3.save()

    result = get_course_access_roles_queryset(orgs_filter=test_orgs, remove_redundant=False, active_filter=True)
    expected_data.pop('user3')
    assert roles_records_to_dict(result) == expected_data


@pytest.mark.django_db
def test_get_roles_for_users_queryset_roles_filter(base_data):  # pylint: disable=unused-argument
    """Verify that get_roles_for_users_queryset returns the expected queryset when roles_filter is used."""
    result = get_course_access_roles_queryset(
        orgs_filter=get_all_orgs(), remove_redundant=False, roles_filter=['data_researcher']
    )

    expected_data = {
        'user9': {
            'ORG3': {
                'None': ['data_researcher'],
                'course-v1:ORG3+2+2': ['data_researcher'],
            },
        },
        'user10': {
            'ORG3': {'None': ['data_researcher']},
        },

    }
    assert roles_records_to_dict(result) == expected_data

    result = get_course_access_roles_queryset(
        orgs_filter=get_all_orgs(), remove_redundant=True, roles_filter=['data_researcher']
    )
    del expected_data['user9']['ORG3']['course-v1:ORG3+2+2']
    assert roles_records_to_dict(result) == expected_data


@pytest.mark.django_db
@pytest.mark.parametrize('course_ids, remove_redundant, exclude_role_type, expected_result', [
    ([], False, None, get_test_data_dict()),
    ([], True, None, {
        'user3': {
            'ORG1': {
                'None': ['staff'],
                'course-v1:ORG1+3+3': ['org_course_creator_group'],
                'course-v1:ORG1+4+4': ['org_course_creator_group'],
            }
        },
        'user8': {
            'ORG2': {'None': ['staff'], 'course-v1:ORG2+3+3': ['org_course_creator_group']}
        },
        'user9': {
            'ORG3': {
                'None': ['staff', 'data_researcher'],
                'course-v1:ORG3+3+3': ['org_course_creator_group'],
            },
            'ORG2': {'course-v1:ORG2+1+1': ['staff'], 'course-v1:ORG2+3+3': ['staff']},
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
            'ORG1': {'None': ['org_course_creator_group'], 'course-v1:ORG1+4+4': ['staff']},
            'ORG2': {'None': ['org_course_creator_group']},
            'ORG3': {
                'None': ['org_course_creator_group'],
                'course-v1:ORG3+1+1': ['staff'],
            },
        },
        'user11': {
            'ORG3': {
                'course-v1:ORG3+2+2': ['org_course_creator_group'],
            }
        },
        'user48': {'ORG4': {'None': ['org_course_creator_group']}},
    }),
    ([], False, RoleType.ORG_WIDE, {
        'user3': {
            'ORG1': {
                'course-v1:ORG1+3+3': ['staff', 'org_course_creator_group'],
                'course-v1:ORG1+4+4': ['org_course_creator_group'],
            }
        },
        'user8': {
            'ORG2': {'course-v1:ORG2+3+3': ['org_course_creator_group']}
        },
        'user9': {
            'ORG3': {
                'course-v1:ORG3+2+2': ['data_researcher'],
                'course-v1:ORG3+3+3': ['org_course_creator_group'],
            },
            'ORG2': {'course-v1:ORG2+1+1': ['staff'], 'course-v1:ORG2+3+3': ['staff']},
        },
        'user18': {'ORG3': {'course-v1:ORG3+3+3': ['staff']}},
        'user4': {
            'ORG1': {'course-v1:ORG1+4+4': ['staff']},
            'ORG3': {
                'course-v1:ORG3+1+1': ['staff', 'org_course_creator_group'],
            },
        },
        'user11': {
            'ORG3': {
                'course-v1:ORG3+2+2': ['org_course_creator_group'],
            }
        },
    }),
    ([], True, RoleType.ORG_WIDE, {
        'user3': {
            'ORG1': {
                'course-v1:ORG1+3+3': ['org_course_creator_group'],
                'course-v1:ORG1+4+4': ['org_course_creator_group'],
            }
        },
        'user8': {
            'ORG2': {'course-v1:ORG2+3+3': ['org_course_creator_group']}
        },
        'user9': {
            'ORG3': {
                'course-v1:ORG3+3+3': ['org_course_creator_group'],
            },
            'ORG2': {'course-v1:ORG2+1+1': ['staff'], 'course-v1:ORG2+3+3': ['staff']},
        },
        'user4': {
            'ORG1': {'course-v1:ORG1+4+4': ['staff']},
            'ORG3': {
                'course-v1:ORG3+1+1': ['staff'],
            },
        },
        'user11': {
            'ORG3': {
                'course-v1:ORG3+2+2': ['org_course_creator_group'],
            }
        },
    }),
    ([], False, RoleType.COURSE_SPECIFIC, get_test_data_dict_without_course_roles()),
    ([], True, RoleType.COURSE_SPECIFIC, get_test_data_dict_without_course_roles()),
    (['course-v1:ORG3+2+2'], False, None, {
        'user9': {
            'ORG3': {
                'None': ['staff', 'data_researcher'],
                'course-v1:ORG3+2+2': ['data_researcher'],
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
        'user11': {
            'ORG3': {
                'course-v1:ORG3+2+2': ['org_course_creator_group'],
            }
        },
    }),
    (['course-v1:ORG3+2+2'], True, None, {
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
        'user11': {
            'ORG3': {
                'course-v1:ORG3+2+2': ['org_course_creator_group'],
            }
        },
    }),
    (['course-v1:ORG3+2+2'], False, RoleType.ORG_WIDE, {
        'user9': {
            'ORG3': {
                'course-v1:ORG3+2+2': ['data_researcher'],
            },
        },
        'user11': {
            'ORG3': {
                'course-v1:ORG3+2+2': ['org_course_creator_group'],
            }
        },
    }),
    (['course-v1:ORG3+2+2'], True, RoleType.ORG_WIDE, {
        'user11': {
            'ORG3': {
                'course-v1:ORG3+2+2': ['org_course_creator_group'],
            }
        },
    }),
    (['course-v1:ORG3+2+2'], False, RoleType.COURSE_SPECIFIC, get_test_data_dict_without_course_roles_org3()),
    (['course-v1:ORG3+2+2'], True, RoleType.COURSE_SPECIFIC, get_test_data_dict_without_course_roles_org3()),
])
def test_get_roles_for_users_queryset(
    base_data, course_ids, remove_redundant, exclude_role_type, expected_result,
):  # pylint: disable=unused-argument
    """Verify that get_roles_for_users_queryset returns the expected queryset."""
    result = get_course_access_roles_queryset(
        orgs_filter=get_all_orgs(),
        course_ids_filter=course_ids,
        remove_redundant=remove_redundant,
        exclude_role_type=exclude_role_type,
    )
    assert roles_records_to_dict(result) == expected_result

    result = get_course_access_roles_queryset(
        orgs_filter=get_all_orgs(),
        course_ids_filter=course_ids,
        remove_redundant=remove_redundant,
        exclude_role_type=exclude_role_type,
        user_id_distinct=True,
    )
    user_ids = [record['user_id'] for record in result]
    expected_user_ids = [int(username[4:]) for username in expected_result.keys()]
    assert set(user_ids) == set(expected_user_ids)


@pytest.mark.django_db
def test_get_roles_for_users_queryset_superuser(base_data):  # pylint: disable=unused-argument
    """Verify that get_roles_for_users_queryset does not include superusers."""
    test_orgs = ['ORG1', 'ORG2']
    user = get_user_model().objects.get(username='user1')
    assert user.is_superuser is True

    users = get_user_model().objects.all()
    result = get_course_access_roles_queryset(orgs_filter=test_orgs, remove_redundant=False, users=users)

    assert CourseAccessRole.objects.filter(user_id=user.id, org__in=test_orgs).exists()
    assert not any(record.user_id == user.id for record in result)


@pytest.mark.django_db
def test_get_roles_for_users_queryset_staff(base_data):  # pylint: disable=unused-argument
    """Verify that get_roles_for_users_queryset does not include staff user."""
    test_orgs = ['ORG1', 'ORG2']
    user = get_user_model().objects.get(username='user2')
    assert user.is_superuser is False
    assert user.is_staff is True

    users = get_user_model().objects.all()
    result = get_course_access_roles_queryset(orgs_filter=test_orgs, remove_redundant=False, users=users)

    assert CourseAccessRole.objects.filter(user_id=user.id, org__in=test_orgs).exists()
    assert result.count() > 0
    assert user.id not in [record.user_id for record in result]


def assert_roles_result(result, expected):
    """Assert that the roles result is as expected."""
    expected_length = len(expected)
    assert result.count() == expected_length
    result = result.order_by('user_id', 'role', 'org', 'course_id')
    for i in result:
        print('user_id:', i.user_id, 'role:', i.role, 'org:', i.org, 'course_id:', i.course_id)
    for index in range(expected_length):
        assert result[index].user_id == expected[index]['user_id']
        assert result[index].role == expected[index]['role']
        assert result[index].org == expected[index]['org']
        assert str(result[index].course_id) == expected[index]['course_id']


@pytest.mark.django_db
def test_get_roles_for_users_queryset_remove_redundant(base_data):  # pylint: disable=unused-argument
    """
    Verify that get_roles_for_users_queryset returns the expected queryset, with or without redundant records.
    """
    test_orgs = ['ORG1', 'ORG2']
    user = get_user_model().objects.get(username='user3')
    assert CourseAccessRole.objects.filter(org__in=test_orgs, user__in=[user]).count() == 4

    result = get_course_access_roles_queryset(orgs_filter=test_orgs, remove_redundant=False, users=[user])
    assert_roles_result(result, [
        {'user_id': 3, 'role': 'org_course_creator_group', 'org': 'ORG1', 'course_id': 'course-v1:ORG1+3+3'},
        {'user_id': 3, 'role': 'org_course_creator_group', 'org': 'ORG1', 'course_id': 'course-v1:ORG1+4+4'},
        {'user_id': 3, 'role': 'staff', 'org': 'ORG1', 'course_id': 'None'},
        {'user_id': 3, 'role': 'staff', 'org': 'ORG1', 'course_id': 'course-v1:ORG1+3+3'},
    ])

    result = get_course_access_roles_queryset(orgs_filter=test_orgs, remove_redundant=True, users=[user])
    assert_roles_result(result, [
        {'user_id': 3, 'role': 'org_course_creator_group', 'org': 'ORG1', 'course_id': 'course-v1:ORG1+3+3'},
        {'user_id': 3, 'role': 'org_course_creator_group', 'org': 'ORG1', 'course_id': 'course-v1:ORG1+4+4'},
        {'user_id': 3, 'role': 'staff', 'org': 'ORG1', 'course_id': 'None'},
    ])
