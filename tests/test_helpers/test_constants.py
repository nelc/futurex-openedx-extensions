"""Tests for the constants module."""
import re

import pytest

from futurex_openedx_extensions.helpers.constants import (
    COURSE_ID_REGX,
    COURSE_ID_REGX_EXACT,
    LIBRARY_ID_REGX,
    LIBRARY_ID_REGX_EXACT,
)


@pytest.mark.parametrize('match_string', [
    'course-v1:edX+DemoX+Demo_Course.2',
    '/course-v1:edX+DemoX+Demo_Course.2',
    'course-v1:edX+DemoX+Demo_Course.2/',
    '/course-v1:edX+DemoX+Demo_Course.2/',
])
def test_course_id_regx_success(match_string):
    """Test the course_id pattern."""
    the_course_id = 'course-v1:edX+DemoX+Demo_Course.2'
    fetch = re.search(COURSE_ID_REGX, match_string).groupdict().get('course_id')
    assert fetch == the_course_id
    assert re.search(COURSE_ID_REGX_EXACT, fetch).groupdict().get('course_id') == the_course_id


@pytest.mark.parametrize('match_string', [
    'course-v2:edX+DemoX+Demo_Course',
    'course-v1:edX+DemoX-Demo_Course',
    'course-v1:edX+DemoX.2+Demo_Course.2',
])
def test_course_id_regx_fail(match_string):
    """Test the course_id pattern."""
    assert re.search(COURSE_ID_REGX_EXACT, match_string) is None


@pytest.mark.parametrize('match_string', [
    'library-v1:edX+DemoX',
    '/library-v1:edX+DemoX',
    'library-v1:edX+DemoX/',
    '/library-v1:edX+DemoX/',
])
def test_library_id_regx_success(match_string):
    """Test the library_id pattern."""
    the_library_id = 'library-v1:edX+DemoX'
    fetch = re.search(LIBRARY_ID_REGX, match_string).groupdict().get('library_id')
    assert fetch == the_library_id
    assert re.search(LIBRARY_ID_REGX_EXACT, fetch).groupdict().get('library_id') == the_library_id


@pytest.mark.parametrize('match_string', [
    'library-v1:edX+DemoX+Demo_Course',
    'library-v1:edX+DemoX.2',
])
def test_library_id_regx_fail(match_string):
    """Test the library_id pattern."""
    assert re.search(LIBRARY_ID_REGX_EXACT, match_string) is None
