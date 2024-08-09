"""Helper functions for FutureX Open edX Extensions."""
from __future__ import annotations

import re
from typing import Any, Dict, List
from urllib.parse import urlparse

from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers.constants import COURSE_ID_REGX_EXACT


def get_course_id_from_uri(uri: str) -> str | None:
    """
    Extract the course_id from the URI.

    :param uri: URI to extract the course_id from.
    :type uri: str
    :return: Course ID extracted from the URI.
    :rtype: str | None
    """
    path_parts = urlparse(uri).path.split('/')
    for part in path_parts:
        result = re.search(COURSE_ID_REGX_EXACT, part)
        if result:
            return result.groupdict().get('course_id')

    return None


def get_first_not_empty_item(items: List, default: Any = None) -> Any:
    """
    Return the first item in the list that is not empty.

    :param items: List of items to check.
    :type items: List
    :param default: Default value to return if no item is found.
    :type default: Any
    :return: First item that is not empty.
    :rtype: Any
    """
    return next((item for item in items if item), default)


def verify_course_ids(course_ids: List[str]) -> None:
    """
    Verify that all course IDs in the list are in valid format. Raise an error if any course ID is invalid.

    :param course_ids: List of course IDs to verify.
    :type course_ids: List[str]
    """
    if course_ids is None:
        raise ValueError('course_ids must be a list of course IDs, but got None')

    for course_id in course_ids:
        if not isinstance(course_id, str):
            raise ValueError(f'course_id must be a string, but got {type(course_id).__name__}')
        if not re.search(COURSE_ID_REGX_EXACT, course_id):
            raise ValueError(f'Invalid course ID format: {course_id}')


def get_orgs_of_courses(course_ids: List[str]) -> Dict[str, Any]:
    """
    Get the organization of the courses with the given course IDs.

    :param course_ids: List of course IDs to get the organization of.
    :type course_ids: List[str]
    :return: Dictionary containing the organization of each course ID.
    :rtype: Dict[str, Any]
    """
    verify_course_ids(course_ids)
    courses = CourseOverview.objects.filter(id__in=course_ids)

    result: Dict[str, Any] = {
        'courses': {courses.id: courses.org.lower() for courses in courses},
    }
    result['invalid_course_ids'] = [course_id for course_id in course_ids if course_id not in result['courses']]
    return result


def generate_simple_hashcode(
    value_dict: Dict[str, Any],
    fields: List[str],
    separator: str = ',',
    replace_none: str = 'None',
) -> str:
    """
    Generate a hashcode string from the given dictionary. The dictionary must be a simple Dict[str: Any], typically
    like the result of using the values() method of a queryset.

    {role: 'admin', org: 'ORG1', course_id: 'COURSE1'} ====> 'admin,ORG1,COURSE1'

    :param value_dict: Dictionary to generate hashcode string from.
    :type value_dict: Dict[str, Any]
    :param fields: List of field names to include in the hashcode.
    :type fields: List[str]
    :param separator: Separator to use between field values.
    :type separator: str
    :param replace_none: String to replace None values with.
    :type replace_none: str
    :return: Hashcode string.
    """
    return separator.join(replace_none if value_dict[field] is None else str(value_dict[field]) for field in fields)


def generate_hashcode_set(
    values: List[Dict[str, Any]],
    fields: List[str],
    separator: str = ',',
    replace_none: str = 'None',
) -> set[str]:
    """
    Generate a set of hashcode strings from a list of dictionary. Typically like the result of using the values()
    method of a queryset.

    [
        {role: 'admin', org: 'ORG1', course_id: 'COURSE1'},
        {role: 'admin', org: 'ORG2', course_id: 'COURSE2'},
    ] ====> {'admin,ORG1,COURSE1', 'admin,ORG2,COURSE2'}

    :param values: List of dictionaries to generate hashcode strings from.
    :type values: List[Dict[str, Any]]
    :param fields: List of field names to include in the hashcode.
    :type fields: List[str]
    :param separator: Separator to use between field values.
    :type separator: str
    :param replace_none: String to replace None values with.
    :type replace_none: str
    :return: Set of hashcode strings.
    """
    return {
        generate_simple_hashcode(record, fields, separator, replace_none)
        for record in values
    }
