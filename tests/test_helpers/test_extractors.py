"""Tests for the helper functions in the helpers module."""
import pytest
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers.extractors import (
    generate_hashcode_set,
    generate_simple_hashcode,
    get_course_id_from_uri,
    get_first_not_empty_item,
    get_orgs_of_courses,
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


def test_verify_course_ids_success():
    """Verify that verify_course_ids does not raise an error for valid course IDs."""
    course_ids = ['course-v1:edX+DemoX+Demo_Course', 'course-v1:edX+DemoX+Demo_Course2']
    verify_course_ids(course_ids)


@pytest.mark.parametrize('course_ids, error_message', [
    (None, 'course_ids must be a list of course IDs, but got None'),
    (['course-v1:edX+DemoX+Demo_Course', 3], 'course_id must be a string, but got int'),
    (['course-v1:edX+DemoX+Demo_Course+extra'], 'Invalid course ID format: course-v1:edX+DemoX+Demo_Course+extra'),
])
def test_verify_course_ids_fail(course_ids, error_message):
    """Verify that verify_course_ids raises an error for invalid course IDs."""
    with pytest.raises(ValueError) as exc:
        verify_course_ids(course_ids)

    assert str(exc.value) == error_message


@pytest.mark.django_db
def test_get_orgs_of_courses(base_data):  # pylint: disable=unused-argument
    """Verify that get_orgs_of_courses returns the expected organization for each course ID."""
    course_ids = ['course-v1:Org1+1+1', 'course-v1:ORG1+2+2', 'course-v1:ORG1+3+3', 'course-v1:ORG1+99+99']
    assert CourseOverview.objects.get(id='course-v1:Org1+1+1').org == 'oRg1'
    assert get_orgs_of_courses(course_ids) == {
        'invalid_course_ids': ['course-v1:ORG1+99+99'],
        'courses': {
            'course-v1:Org1+1+1': 'org1',
            'course-v1:ORG1+2+2': 'org1',
            'course-v1:ORG1+3+3': 'org1',
        },
    }


def test_generate_simple_hashcode_simple():
    """Verify that generate_simple_hashcode returns the expected hashcode."""
    data = {'role': 'admin', 'org': 'ORG1', 'course_id': 'COURSE1'}
    result = generate_simple_hashcode(data, ['role', 'org', 'course_id'])
    assert result == 'admin,ORG1,COURSE1'


def test_generate_simple_hashcode_replace_none():
    """Verify that generate_simple_hashcode replaces None values with the specified string."""
    data = {'role': 'student', 'org': 'ORG2', 'course_id': None}
    result = generate_simple_hashcode(data, ['role', 'org', 'course_id'])
    assert result == 'student,ORG2,None'

    result = generate_simple_hashcode(data, ['role', 'org', 'course_id'], replace_none='anything_else')
    assert result == 'student,ORG2,anything_else'


def test_generate_simple_hashcode_custom_separator():
    """Verify that generate_simple_hashcode uses the specified separator between field values."""
    data = {'role': 'admin', 'org': 'ORG1', 'course_id': 'COURSE1'}
    result = generate_simple_hashcode(data, ['role', 'org', 'course_id'], separator='|')
    assert result == 'admin|ORG1|COURSE1'


def test_generate_simple_hashcode_with_non_string_fields():
    """Verify that generate_simple_hashcode returns the expected hashcode for non-string fields."""
    data = {'role': 'admin', 'org': 1, 'course_id': 101}
    result = generate_simple_hashcode(data, ['role', 'org', 'course_id'])
    assert result == 'admin,1,101'


def test_generate_hashcode_set():
    """Verify that generate_hashcode_set returns the expected hashcode strings."""
    data = [
        {'role': 'admin', 'org': 'ORG1', 'course_id': 'COURSE1'},
        {'role': 'admin', 'org': 'ORG1', 'course_id': 'COURSE1'},
        {'role': 'admin', 'org': 'ORG2', 'course_id': 'COURSE2'},
    ]
    result = generate_hashcode_set(data, ['role', 'org', 'course_id'])
    assert result == {'admin,ORG1,COURSE1', 'admin,ORG2,COURSE2'}


def test_generate_hashcode_set_empty_list():
    """Verify that generate_simple_hashcode returns an empty set for an empty list."""
    result = generate_hashcode_set([], ['role', 'org', 'course_id'])
    assert result == set()
