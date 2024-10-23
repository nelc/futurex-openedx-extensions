"""Tests for management commands"""
from unittest.mock import patch

import pytest
from common.djangoapps.student.models import CourseAccessRole
from django.contrib.auth import get_user_model
from django.core.management import call_command

from futurex_openedx_extensions.helpers import constants as cs

COMMAND_PATH = 'futurex_openedx_extensions.helpers.management.commands.course_access_roles_clean_up'


@pytest.mark.django_db
@pytest.mark.parametrize('options', [
    ['--commit=yes'], ['--commit=no'], [],
])
def test_course_access_roles_clean_up_sanity_check_handler(base_data, options):  # pylint: disable=unused-argument
    """Sanity check for course_access_roles_clean_up command"""
    assert CourseAccessRole.objects.filter(user_id=55, org='org1', role='staff').count() == 0
    CourseAccessRole.objects.create(user_id=55, org='org1', role='staff')
    CourseAccessRole.objects.create(user_id=55, org='org1', role='staff', course_id='library-v1:the-lib+id')
    with patch(f'{COMMAND_PATH}.update_course_access_roles', return_value={'error_code': None}):
        call_command('course_access_roles_clean_up', *options)
    assert CourseAccessRole.objects.filter(user_id=55, org='org1', role='staff').count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize('update_result', [
    {'error_code': 4001, 'error_message': 'Some error message'},
    {'error_code': 99999, 'error_message': 'Some error message'},
])
def test_course_access_roles_clean_up_sanity_check_errors(base_data, update_result):  # pylint: disable=unused-argument
    """Sanity check for course_access_roles_clean_up command"""
    CourseAccessRole.objects.create(user_id=55, org='invalid_org')
    get_user_model().objects.filter(id=1).update(is_active=False)

    with patch(f'{COMMAND_PATH}.update_course_access_roles', return_value=update_result):
        call_command('course_access_roles_clean_up', '--commit=yes')


@pytest.mark.django_db
def test_course_access_roles_clean_up_delete_error(base_data, capfd):  # pylint: disable=unused-argument
    """Sanity check for course_access_roles_clean_up command"""
    get_user_model().objects.filter(id=1).update(is_active=False)
    with patch(f'{COMMAND_PATH}.delete_course_access_roles', side_effect=Exception('Some error for testing')):
        call_command('course_access_roles_clean_up', '--commit=yes')
    out, _ = capfd.readouterr()
    assert 'Failed to process user' in out
    assert 'Some error for testing' in out


@pytest.mark.django_db
def test_course_access_roles_clean_up_sanity_check_cleaning(base_data, capfd):  # pylint: disable=unused-argument
    """Sanity check for course_access_roles_clean_up command"""
    CourseAccessRole.objects.filter(org='').delete()
    CourseAccessRole.objects.filter(user_id__in=[1, 2]).delete()
    CourseAccessRole.objects.exclude(role__in=cs.COURSE_ACCESS_ROLES_SUPPORTED_READ).delete()

    call_command('course_access_roles_clean_up', '--commit=yes')
    out, _ = capfd.readouterr()
    assert 'users with dirty entries' in out
    assert 'No dirty entries found..' not in out

    call_command('course_access_roles_clean_up', '--commit=yes')
    out, _ = capfd.readouterr()
    assert 'users with dirty entries' not in out
    assert 'No dirty entries found..' in out
