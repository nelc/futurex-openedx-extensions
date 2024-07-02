"""Tests for the constants module."""
import re

import pytest

from futurex_openedx_extensions.helpers.constants import COURSE_ID_REGX


@pytest.mark.parametrize('match_string', [
    'course-v1:edX+DemoX+Demo_Course',
    '/course-v1:edX+DemoX+Demo_Course',
    'course-v1:edX+DemoX+Demo_Course/',
    '/course-v1:edX+DemoX+Demo_Course/',
])
def test_course_id_regx_success(match_string):
    """Test the course_id pattern."""
    assert re.search(COURSE_ID_REGX, match_string).groupdict().get('course_id') == 'course-v1:edX+DemoX+Demo_Course'


@pytest.mark.parametrize('match_string', ['course-v2:edX+DemoX+Demo_Course', 'course-v1:edX+DemoX-Demo_Course'])
def test_course_id_regx_fail(match_string):
    """Test the course_id pattern."""
    assert re.search(COURSE_ID_REGX, match_string) is None
