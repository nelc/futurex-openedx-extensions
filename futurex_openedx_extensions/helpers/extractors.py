"""Helper functions for FutureX Open edX Extensions."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List
from urllib.parse import urlparse

from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers import constants as cs


@dataclass
class DictHashcode:
    """Class for keeping track of a dictionary hashcode."""
    dict_item: dict
    separator: str = ','

    def __init__(self, dict_item: Dict[str, Any], separator: str = ',') -> None:
        """Accepts a dict and saves a hashcode"""
        if not isinstance(dict_item, dict):
            raise TypeError(f'DictHashcode accepts only dict type. Got: {type(dict_item).__name__}')
        self.dict_item = dict_item
        self.separator = separator

        self.hash_code = separator.join(str(item[1]) for item in sorted(dict_item.items()))

    def __hash__(self) -> int:
        """Enables the object is usable for hash based operations"""
        return hash(self.hash_code)

    def __eq__(self, other: Any) -> bool:
        """Enables the object is usable for equality based operations"""
        if isinstance(other, DictHashcode):
            return self.hash_code == other.hash_code

        return False


class DictHashcodeSet:
    """Class for keeping track of a set of dictionary hashcodes."""

    def __init__(self, dict_list: List[Dict[str, Any]], separator: str = ',') -> None:
        """Accepts a list of dicts and saves a set of hashcodes"""
        if not isinstance(dict_list, list):
            raise TypeError(f'DictHashcodeSet accepts only list type. Got: {type(dict_list).__name__}')

        self.separator = separator
        self._dict_hash_codes = set()
        for dict_item in dict_list:
            self._dict_hash_codes.add(DictHashcode(dict_item=dict_item, separator=separator))

    def __contains__(self, dict_item: Dict | DictHashcode) -> bool:
        """Check if the dict_item is in the hash_codes set."""
        if not isinstance(dict_item, (dict, DictHashcode)):
            return False

        if isinstance(dict_item, dict):
            dict_item = DictHashcode(dict_item=dict_item, separator=self.separator)

        return dict_item in self._dict_hash_codes

    def __eq__(self, other: Any) -> bool:
        """Check if the other object is equal to the hash_codes set."""
        if isinstance(other, DictHashcodeSet):
            return self._dict_hash_codes == other.dict_hash_codes

        if isinstance(other, set):
            return self._dict_hash_codes == other

        return False

    @property
    def dict_hash_codes(self) -> set:
        """Get the set of dictionary hashcodes."""
        return self._dict_hash_codes


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
        result = re.search(cs.COURSE_ID_REGX_EXACT, part)
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
        if not re.search(cs.COURSE_ID_REGX_EXACT, course_id):
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
        'courses': {str(course.id): course.org.lower() for course in courses},
    }

    invalid_course_ids = [course_id for course_id in course_ids if course_id not in result['courses']]
    if invalid_course_ids:
        raise ValueError(f'Invalid course IDs provided: {invalid_course_ids}')

    return result


def get_partial_access_course_ids(fx_permission_info: dict) -> List[str]:
    """
    Get the course IDs that the user has partial access to according to the permission information.

    Note: remember that the user can have a course-specific role on one course, but that course is already
    accessible by another tenant-wide role. Therefore, that course is not considered as a partial access course.

    :param fx_permission_info: Dictionary containing permission information.
    :type fx_permission_info: dict
    :return: List of course IDs that the user has partial access to.
    :rtype: List[str]
    """
    if fx_permission_info['is_system_staff_user']:
        return []

    role_keys = set(fx_permission_info['view_allowed_roles']) & set(fx_permission_info['user_roles'])
    if role_keys & set(cs.COURSE_ACCESS_ROLES_GLOBAL):
        return []

    course_ids_to_check = set()
    for role_key in role_keys:
        course_ids_to_check.update(fx_permission_info['user_roles'][role_key]['course_limited_access'])

    only_limited_access = CourseOverview.objects.filter(
        id__in=list(course_ids_to_check),
        org__in=fx_permission_info['view_allowed_course_access_orgs'],
    ).values_list('id', flat=True)

    return [str(course_id) for course_id in only_limited_access]
