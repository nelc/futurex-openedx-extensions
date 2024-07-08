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
    check_tenant_access,
    get_all_course_access_roles,
    get_fx_view_with_roles,
    is_valid_course_access_role,
    is_view_exist,
    is_view_support_write,
    optimize_access_roles_result,
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
    assert user is not None, 'Bad test data, user 3 should be an active non-staff user'
    assert get_all_course_access_roles()[3] == {
        'staff': {'orgs_full_access': ['ORG1'], 'course_limited_access': [], 'orgs_of_courses': []},
    }

    setattr(user, verify_attribute, not getattr(user, verify_attribute))
    user.save()
    assert get_all_course_access_roles().get(3) is None

    setattr(user, verify_attribute, not getattr(user, verify_attribute))
    user.save()
    assert get_all_course_access_roles()[3] == {
        'staff': {'orgs_full_access': ['ORG1'], 'course_limited_access': [], 'orgs_of_courses': []},
    }


@pytest.mark.django_db
def test_get_all_course_access_roles(base_data):  # pylint: disable=unused-argument
    """Verify that get_all_course_access_roles returns the expected structure."""
    _remove_course_access_roles_causing_error_logs()
    assert get_all_course_access_roles()[3] == {
        'staff': {'orgs_full_access': ['ORG1'], 'course_limited_access': [], 'orgs_of_courses': []},
    }
    CourseAccessRole.objects.create(
        user_id=3,
        role='staff',
        org='ORG1',
        course_id='course-v1:ORG2+1+1',
    )
    CourseAccessRole.objects.create(
        user_id=3,
        role='staff',
        org='ORG1',
    )
    CourseAccessRole.objects.create(
        user_id=3,
        role='staff',
        org='ORG2',
        course_id='course-v1:ORG2+2+2',
    )
    for _ in range(2):
        CourseAccessRole.objects.create(
            user_id=4,
            role='staff',
            org='ORG2',
            course_id='course-v1:ORG2+2+2',
        )

    assert get_all_course_access_roles()[3] == {
        'staff': {
            'orgs_full_access': ['ORG1'], 'course_limited_access': ['course-v1:ORG2+2+2'], 'orgs_of_courses': ['ORG2']
        },
    }


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
@pytest.mark.django_db
def test_get_all_course_access_roles_being_cached():
    """Verify that get_all_course_access_roles is being cached."""
    assert cache.get(CACHE_NAME_ALL_COURSE_ACCESS_ROLES) is None
    result = get_all_course_access_roles()
    assert cache.get(CACHE_NAME_ALL_COURSE_ACCESS_ROLES) == result


@pytest.mark.django_db
@pytest.mark.parametrize("user_id, ids_to_check, expected", [
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
            'details': {'error': "invalid literal for int() with base 10: 'E'"},
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
            fx_view_name = ""
            fx_view_description = "A test view"
            fx_default_read_only_roles = ["role1", "role2"]

    mock_logger.error.assert_called_with('fx_view_name is not defined for view (%s)', 'TestView')


def test_fx_view_role_metaclass_view_name_length_exceeded():
    """Verify that an error is logged if the view name length exceeds 255 characters."""
    long_name = "x" * 256
    with patch('futurex_openedx_extensions.helpers.roles.logger') as mock_logger:
        class TestView(FXViewRoleInfoMetaClassTestView):  # pylint: disable=too-few-public-methods, unused-variable
            fx_view_name = long_name
            fx_view_description = "A test view"
            fx_default_read_only_roles = ["role1", "role2"]

    mock_logger.error.assert_called_with(
        'fx_view_name and fx_view_description length must be below 256 characters (%s)', 'TestView')


def test_fx_view_role_metaclass_view_description_length_exceeded():
    """Verify that an error is logged if the view description length exceeds 255 characters."""
    long_description = "x" * 256
    with patch('futurex_openedx_extensions.helpers.roles.logger') as mock_logger:
        class TestView(FXViewRoleInfoMetaClassTestView):  # pylint: disable=too-few-public-methods, unused-variable
            fx_view_name = "TestView"
            fx_view_description = long_description
            fx_default_read_only_roles = ["role1", "role2"]

    mock_logger.error.assert_called_with(
            'fx_view_name and fx_view_description length must be below 256 characters (%s)', 'TestView'
        )


def test_fx_view_role_metaclass_view_name_duplicate():
    """Verify that an error is logged if the view name is a duplicate."""
    class FirstView(FXViewRoleInfoMetaClassTestView):  # pylint: disable=too-few-public-methods, unused-variable
        fx_view_name = "TestView"
        fx_view_description = "First test view"
        fx_default_read_only_roles = ["role1"]

    with patch('futurex_openedx_extensions.helpers.roles.logger') as mock_logger:
        class SecondView(FXViewRoleInfoMetaClassTestView):  # pylint: disable=too-few-public-methods, unused-variable
            fx_view_name = "TestView"
            fx_view_description = "Second test view"
            fx_default_read_only_roles = ["role2"]

    mock_logger.error.assert_called_with('fx_view_name duplicate between (%s) and another view', 'SecondView')


def test_fx_view_role_metaclass_adding_view_to_fx_views_with_roles():
    """Verify that the view is added to the _fx_views_with_roles dictionary."""
    class TestView(FXViewRoleInfoMetaClassTestView):  # pylint: disable=too-few-public-methods
        """Test view class."""
        fx_view_name = "UniqueView"
        fx_view_description = "A unique test view"
        fx_default_read_only_roles = ["role1", "role2"]

    assert 'TestView' in TestView._fx_views_with_roles  # pylint: disable=protected-access
    assert TestView._fx_views_with_roles['TestView'] == {  # pylint: disable=protected-access
        'name': "UniqueView",
        'description': "A unique test view",
        'default_read_only_roles': ["role1", "role2"],
        'default_read_write_roles': [],
    }
    assert "UniqueView" in TestView._fx_views_with_roles['_all_view_names']  # pylint: disable=protected-access


def test_fx_view_role_metaclass_bad_duplicate_class_definition():
    """Verify that duplicate class definitions are logged as errors, and included in get_fx_view_with_roles result."""
    class DuplicateClassDefinition(
        FXViewRoleInfoMetaClassTestView
    ):  # pylint: disable=too-few-public-methods, missing-class-docstring
        fx_view_name = "TestView_1"
        fx_view_description = "A test view"
        fx_default_read_only_roles = ["role1", "role2"]

    expected_result = {
        'DuplicateClassDefinition': {
            'name': "TestView_1",
            'description': "A test view",
            'default_read_only_roles': ["role1", "role2"],
            'default_read_write_roles': [],
        },
        '_all_view_names': {"TestView_1": DuplicateClassDefinition},
    }

    with patch('futurex_openedx_extensions.helpers.roles.logger') as mock_logger:
        class DuplicateClassDefinition(
            FXViewRoleInfoMetaClassTestView
        ):  # pylint: disable=function-redefined, too-few-public-methods, missing-class-docstring
            fx_view_name = "TestView_2"
            fx_view_description = "A test view"
            fx_default_read_only_roles = ["role1", "role5"]

    assert get_fx_view_with_roles() == expected_result
    mock_logger.error.assert_called_with(
        'FXViewRoleInfoMetaClass error: Unexpected class redefinition (%s)', 'DuplicateClassDefinition'
    )


def test_fx_view_role_metaclass_get_fx_view_with_roles():
    """Verify that get_fx_view_with_roles returns the expected dictionary."""
    class TestView1(FXViewRoleInfoMetaClassTestView):  # pylint: disable=too-few-public-methods
        fx_view_name = "TestView_1"
        fx_view_description = "A test view"
        fx_default_read_only_roles = ["role1", "role2"]

    class TestView2(FXViewRoleInfoMetaClassTestView):  # pylint: disable=too-few-public-methods
        fx_view_name = "TestView_2"
        fx_view_description = "A test view"
        fx_default_read_only_roles = ["role1", "role5"]

    assert get_fx_view_with_roles() == {
        'TestView1': {
            'name': "TestView_1",
            'description': "A test view",
            'default_read_only_roles': ["role1", "role2"],
            'default_read_write_roles': [],
        },
        'TestView2': {
            'name': "TestView_2",
            'description': "A test view",
            'default_read_only_roles': ["role1", "role5"],
            'default_read_write_roles': [],
        },
        '_all_view_names': {"TestView_1": TestView1, "TestView_2": TestView2},
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
            fx_view_name = "TestView"
            fx_view_description = "A test view"
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
            fx_view_name = "TestView"
            fx_view_description = "A test view"
            fx_allowed_write_methods = ['POST']
        assert TestView.check_allowed_write_methods() is True

        assert error_message not in caplog.text
        TestView.fx_allowed_write_methods = ['GET']
        assert TestView.check_allowed_write_methods() is False
        assert error_message in caplog.text


def test_fx_view_role_metaclass_is_write_supported():
    """Verify that is_write_supported returns the expected value."""
    class TestView(FXViewRoleInfoMetaClass):
        fx_view_name = "TestView"
        fx_view_description = "A test view"
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
        fx_view_name = "TestView"
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
