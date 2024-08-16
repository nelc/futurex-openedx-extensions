"""Tests for the helper functions in the helpers module."""
import pytest

from futurex_openedx_extensions.helpers.extractors import get_course_id_from_uri, get_first_not_empty_item


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
