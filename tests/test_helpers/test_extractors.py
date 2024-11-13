"""Tests for the helper functions in the helpers module."""
from unittest.mock import Mock, patch

import pytest
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers.extractors import (
    DictHashcode,
    DictHashcodeSet,
    get_course_id_from_uri,
    get_first_not_empty_item,
    get_orgs_of_courses,
    get_partial_access_course_ids,
    verify_course_ids,
)


@pytest.mark.parametrize('items, expected, error_message', [
    ([0, None, False, '', 3, 'hello'], 3, 'Test with a list containing truthy and falsy values'),
    ([0, None, False, ''], None, 'Test with a list containing only falsy values'),
    ([1, 'a', [1], {1: 1}], 1, 'Test with a list containing only truthy values'),
    ([], None, 'Test with an empty list'),
    ([0, [], {}, (), 'non-empty'], 'non-empty', 'Test with a list containing mixed types'),
    ([[], {}, (), 5], 5, 'Test with a list containing different truthy types'),
    ([None, 'test'], 'test', 'Test with None as an element'),
    ([[None, []], [], [1, 2, 3]], [None, []], 'Test with nested lists'),
    (['first', 0, None, False, '', 3, 'hello'], 'first', 'Test with first element truthy')
])
def test_get_first_not_empty_item(items, expected, error_message):
    """Verify that the get_first_not_empty_item function returns the first non-empty item in the list."""
    assert get_first_not_empty_item(items) == expected, f'Failed: {error_message}'


@pytest.mark.parametrize('uri, expected_course_id', [
    ('http://domain/path/course-v1:Org1+1+1/?page=1&page_size=%2F', 'course-v1:Org1+1+1'),
    ('http://domain/path/course-v1:ORG2+2+2/?page=2&page_size=10', 'course-v1:ORG2+2+2'),
    ('http://domain/path/course-v1:Org1+1+1', 'course-v1:Org1+1+1'),
    ('http://domain/path/course-v1:ORG3+3+3/', 'course-v1:ORG3+3+3'),
    ('http://domain/path', None),
    ('http://domain/path?course_id=course-v1:ORG2+2+2', None),
    ('http://domain/path/some-other-path', None),
    ('http://domain/path/course-v1:ORG4+4+4/morepath', 'course-v1:ORG4+4+4'),
    ('http://domain/path/bad-start-course-v1:ORG4+4+4/morepath', None),
    ('http://domain/path/bad-start-course-v1:ORG4+4/morepath', None),
])
def test_get_course_id_from_uri(uri, expected_course_id):
    """Verify that the get_course_id_from_uri function returns the course ID from the URI."""
    assert get_course_id_from_uri(uri) == expected_course_id


@pytest.mark.parametrize('course_ids', [
    (['course-v1:edX+DemoX+Demo_Course', 'course-v1:edX+DemoX+Demo_Course2']),
    (['library-v1:DemoX+11', 'library-v1:DemoX+22']),
    (['course-v1:edX+DemoX+Demo_Course', 'library-v1:DemoX+22']),
])
def test_verify_course_ids_success(course_ids):
    """Verify that verify_course_ids does not raise an error for valid course and library IDs."""
    verify_course_ids(course_ids)


@pytest.mark.parametrize('course_ids, error_message', [
    (None, 'course_ids must be a list of course IDs, but got None'),
    (['course-v1:edX+DemoX+Demo_Course', 3], 'course_id must be a string, but got int'),
    (['course-v1:edX+DemoX+Demo_Course+extra'], 'Invalid course ID format: course-v1:edX+DemoX+Demo_Course+extra'),
    (['library-v1:edX+DemoX+extra'], 'Invalid course ID format: library-v1:edX+DemoX+extra'),
    (['library-v1:invalid'], 'Invalid course ID format: library-v1:invalid'),
])
def test_verify_course_ids_fail(course_ids, error_message):
    """Verify that verify_course_ids raises an error for invalid course IDs."""
    with pytest.raises(ValueError) as exc:
        verify_course_ids(course_ids)

    assert str(exc.value) == error_message


@pytest.mark.django_db
def test_get_orgs_of_courses(base_data):  # pylint: disable=unused-argument
    """Verify that get_orgs_of_courses returns the expected organization for each course ID."""
    course_ids = ['course-v1:Org1+1+1', 'course-v1:ORG1+2+2', 'course-v1:ORG1+3+3']
    assert CourseOverview.objects.get(id='course-v1:Org1+1+1').org == 'oRg1'
    assert get_orgs_of_courses(course_ids) == {
        'courses': {
            'course-v1:Org1+1+1': 'org1',
            'course-v1:ORG1+2+2': 'org1',
            'course-v1:ORG1+3+3': 'org1',
        },
    }


@pytest.mark.django_db
@pytest.mark.parametrize('course_ids, expected_orgs', [
    (['course-v1:Org1+1+1', 'course-v1:ORG1+2+2'], {
        'course-v1:Org1+1+1': 'org1',
        'course-v1:ORG1+2+2': 'org1',
    }),
    (['library-v1:org1+11', 'course-v1:ORG1+5+5'], {
        'library-v1:org1+11': 'org1',
        'course-v1:ORG1+5+5': 'org1',
    }),
    (['library-v1:org1+11', 'library-v1:org1+22'], {
        'library-v1:org1+11': 'org1',
        'library-v1:org1+22': 'org1',
    }),
])
def test_get_orgs_of_courses_for_library_ids(course_ids, expected_orgs, base_data):  # pylint: disable=unused-argument
    """Verify that get_orgs_of_courses returns the expected organization for library ids."""
    result = get_orgs_of_courses(course_ids)
    assert result == {'courses': expected_orgs}


@pytest.mark.django_db
@pytest.mark.parametrize('course_ids, expected_error_message', [
    (
        ['course-v1:ORG1+2+99'],
        'Invalid course IDs provided: [\'course-v1:ORG1+2+99\']'
    ),
    (
        ['library-v1:not_exist+11'],
        'Invalid course IDs provided: [\'library-v1:not_exist+11\']'
    ),
    (
        ['course-v1:ORG1+2+99', 'library-v1:not_exist+1'],
        'Invalid course IDs provided: [\'course-v1:ORG1+2+99\', \'library-v1:not_exist+1\']'
    )
])
def test_get_orgs_of_courses_invalid_course(
    course_ids, expected_error_message, base_data
):  # pylint: disable=unused-argument
    """Verify that get_orgs_of_courses raises an error for an invalid course ID."""
    with pytest.raises(ValueError) as exc_info:
        get_orgs_of_courses(course_ids)
    assert str(exc_info.value) == expected_error_message


def test_dict_hashcode_init():
    """Verify that the DictHashcode object is initialized correctly with a dictionary."""
    sample_dict = {'key1': 'value1', 'key2': 'value2'}
    dict_hashcode = DictHashcode(sample_dict)
    expected_hash_code = 'value1,value2'
    assert dict_hashcode.hash_code == expected_hash_code


def test_dict_hashcode_init_invalid_type():
    """Verify that the DictHashcode object raises a TypeError when initialized with a non-dictionary."""
    with pytest.raises(TypeError) as exc_info:
        DictHashcode(['not', 'a', 'dict'])
    assert str(exc_info.value) == 'DictHashcode accepts only dict type. Got: list'


def test_dict_hashcode_hash():
    """Verify that the __hash__ method returns the correct hash for the dictionary."""
    sample_dict = {'key1': 'value1', 'key2': 'value2'}
    dict_hashcode = DictHashcode(sample_dict)
    assert isinstance(hash(dict_hashcode), int)


def test_dict_hashcode_eq_same():
    """Verify that two DictHashcode objects with the same dictionary are equal."""
    sample_dict = {'key1': 'value1', 'key2': 'value2'}
    dict_hashcode1 = DictHashcode(sample_dict)
    dict_hashcode2 = DictHashcode(sample_dict)
    assert dict_hashcode1 == dict_hashcode2


def test_dict_hashcode_eq_different():
    """Verify that two DictHashcode objects with different dictionaries are not equal."""
    dict_hashcode1 = DictHashcode({'key1': 'value1', 'key2': 'value2'})
    dict_hashcode2 = DictHashcode({'key1': 'value1', 'key3': 'value3'})
    assert dict_hashcode1 != dict_hashcode2


def test_dict_hashcode_eq_different_type():
    """Verify that a DictHashcode object is not equal to an object of a different type."""
    dict_hashcode = DictHashcode({'key1': 'value1', 'key2': 'value2'})
    assert dict_hashcode != 'not_a_dict_hashcode'


def test_dict_hashcodeset_init():
    """Verify that the DictHashcodeSet object is initialized correctly with a list of dictionaries."""
    dict_list = [{'key1': 'value1'}, {'key2': 'value2'}]
    hashcode_set = DictHashcodeSet(dict_list)
    assert len(hashcode_set.dict_hash_codes) == 2


def test_dict_hashcodeset_init_invalid_type():
    """Verify that the DictHashcodeSet object raises a TypeError when initialized with a non-list."""
    with pytest.raises(TypeError):
        DictHashcodeSet({'not': 'a list'})


def test_dict_hashcodeset_contains():
    """Verify that a dictionary is correctly identified as contained in the DictHashcodeSet."""
    dict_list = [{'key1': 'value1'}, {'key2': 'value2'}]
    hashcode_set = DictHashcodeSet(dict_list)
    assert {'key1': 'value1'} in hashcode_set
    assert {'key3': 'value3'} not in hashcode_set
    assert 'something' not in hashcode_set


def test_dict_hashcodeset_contains_dicthashcode():
    """Verify that a DictHashcode object is correctly identified as contained in the DictHashcodeSet."""
    dict_list = [{'key1': 'value1'}, {'key2': 'value2'}]
    hashcode_set = DictHashcodeSet(dict_list)
    dict_hashcode = DictHashcode({'key1': 'value1'})
    assert dict_hashcode in hashcode_set


def test_dict_hashcodeset_eq_same():
    """Verify that two DictHashcodeSet objects with the same dictionary list are equal."""
    item1 = {'key1': 'value1'}
    item2 = {'key2': 'value2'}
    dict_list1 = [item1, item2]
    dict_list2 = [item2, item1]
    dict_list3 = [item1, item1, item2]

    assert DictHashcodeSet(dict_list1) == DictHashcodeSet(dict_list1)
    assert DictHashcodeSet(dict_list1) == DictHashcodeSet(dict_list2)
    assert DictHashcodeSet(dict_list2) == DictHashcodeSet(dict_list3)
    assert DictHashcodeSet(dict_list1) == DictHashcodeSet(dict_list3).dict_hash_codes


def test_dict_hashcodeset_eq_different():
    """Verify that two DictHashcodeSet objects with different dictionary lists are not equal."""
    hashcode_set1 = DictHashcodeSet([{'key1': 'value1'}])
    hashcode_set2 = DictHashcodeSet([{'key2': 'value2'}])
    assert hashcode_set1 != hashcode_set2


def test_dict_hashcodeset_eq_different_type():
    """Verify that a DictHashcodeSet object is not equal to an object of a different type."""
    dict_list = [{'key1': 'value1'}, {'key2': 'value2'}]
    hashcode_set = DictHashcodeSet(dict_list)
    assert hashcode_set != 'not_a_hashcode_set'


def _get_user_roles():
    """Helper function to return a dictionary of user roles for testing."""
    return {
        cs.COURSE_ACCESS_ROLES_GLOBAL[0]: {},
        cs.COURSE_ACCESS_ROLES_COURSE_ONLY[0]: {
            'course_limited_access': ['course-v1:Org1+1+1'],
        },
        cs.COURSE_ACCESS_ROLES_TENANT_OR_COURSE[0]: {
            'course_limited_access': ['course-v1:ORG3+1+1'],
        },
    }


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.extractors.CourseOverview.objects.filter')
def test_get_partial_access_course_ids_staff(
    mock_filter, base_data, fx_permission_info,
):  # pylint: disable=unused-argument
    """Verify that get_partial_access_course_ids returns an empty list for a staff user."""
    assert fx_permission_info['is_system_staff_user'], 'bad test data'

    result = get_partial_access_course_ids(fx_permission_info)
    assert isinstance(result, list)
    assert not result
    mock_filter.assert_not_called()


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.extractors.CourseOverview.objects.filter')
def test_get_partial_access_course_ids_global_role(
    mock_filter, base_data, fx_permission_info,
):  # pylint: disable=unused-argument
    """Verify that get_partial_access_course_ids returns an empty list for a user with a global role."""
    fx_permission_info.update({
        'is_system_staff_user': False,
        'user_roles': _get_user_roles(),
        'view_allowed_roles': cs.COURSE_ACCESS_ROLES_GLOBAL,
    })

    result = get_partial_access_course_ids(fx_permission_info)
    assert isinstance(result, list)
    assert not result
    mock_filter.assert_not_called()


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.extractors.CourseOverview.objects.filter')
def test_get_partial_access_course_ids_no_roles_access(
    mock_filter, base_data, fx_permission_info,
):  # pylint: disable=unused-argument
    """Verify that get_partial_access_course_ids returns an empty list when the user has no roles access."""
    fx_permission_info.update({
        'is_system_staff_user': False,
        'user_roles': _get_user_roles(),
        'view_allowed_roles': cs.COURSE_ACCESS_ROLES_TENANT_ONLY[0],
        'view_allowed_course_access_orgs': ['org3'],
    })

    mock_filter.return_value = Mock(values_list=Mock(return_value=[]))
    result = get_partial_access_course_ids(fx_permission_info)
    assert isinstance(result, list)
    assert not result
    mock_filter.assert_called_once()
    mock_filter.assert_called_with(id__in=[], org__in=['org3'])


@pytest.mark.django_db
def test_get_partial_access_course_ids_found(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify that get_partial_access_course_ids returns the expected course IDs for a user."""
    fx_permission_info.update({
        'is_system_staff_user': False,
        'user_roles': _get_user_roles(),
        'view_allowed_roles': cs.COURSE_ACCESS_ROLES_TENANT_OR_COURSE + cs.COURSE_ACCESS_ROLES_COURSE_ONLY,
        'view_allowed_course_access_orgs': ['org3'],
    })

    result = get_partial_access_course_ids(fx_permission_info)
    assert isinstance(result, list)
    assert result == ['course-v1:ORG3+1+1']
