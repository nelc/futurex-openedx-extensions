"""Helper class to manage course categories for a tenant."""
import logging
import re
from typing import Any, Dict, List

from django.conf import settings

from futurex_openedx_extensions.helpers.constants import COURSE_ID_REGX_EXACT
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.tenants import get_tenant_config_value, set_tenant_config_value

logger = logging.getLogger(__name__)


class CourseCategories:
    """Helper class to manage course categories for a tenant."""

    def __init__(self, tenant_id: int, open_as_read_only: bool = True):
        """
        Initialize the CourseCategories instance.

        :param tenant_id: ID of the tenant.
        :type tenant_id: int
        :param open_as_read_only: Whether to open the categories in read-only mode.
        :type open_as_read_only: bool
        """
        self.tenant_id = tenant_id
        self.read_only = open_as_read_only
        self.categories: Dict[str, Any] = {}
        self.sorting: List[str] = []

        self.reload()

    @staticmethod
    def validated_courses(courses: List, silent_fail: bool = False) -> List:
        """
        Validate a list of course IDs.

        :param courses: List of course IDs to validate.
        :type courses: List
        :param silent_fail: Whether to skip invalid course IDs instead of raising an exception.
        :type silent_fail: bool
        :return: List of valid course IDs.
        """
        validated_courses = []
        for course_id in courses:
            if not isinstance(course_id, str):
                error_msg = f'course_id is not a string: {course_id}'
                if not silent_fail:
                    raise FXCodedException(
                        code=FXExceptionCodes.COURSE_CATEGORY_INVALID_SETTINGS,
                        message=error_msg,
                    )
                logger.error(error_msg)
            elif re.match(COURSE_ID_REGX_EXACT, course_id) is None:
                error_msg = f'course_id is not valid: {course_id}'
                if not silent_fail:
                    raise FXCodedException(
                        code=FXExceptionCodes.COURSE_CATEGORY_INVALID_SETTINGS,
                        message=error_msg,
                    )
                logger.error(error_msg)
            else:

                validated_courses.append(course_id)
        return validated_courses

    def reformat_categories_and_sorting(self, categories: Dict[str, Any], sorting: List[str]) -> None:
        """
        Reformat categories and sorting to ensure consistency.

        :param categories: Dictionary of categories.
        :type categories: Dict[str, Any]
        :param sorting: List of category names in desired order.
        :type sorting: List[str]
        """
        sorting = [cat for cat in sorting if cat in categories]
        for cat in categories.keys():
            if cat not in sorting:
                sorting.append(cat)
        self.sorting = sorting

        for category_name, category_info in categories.items():
            courses = category_info.get('courses', [])
            if not isinstance(courses, list):
                raise FXCodedException(
                    code=FXExceptionCodes.COURSE_CATEGORY_INVALID_SETTINGS,
                    message=f'Courses for category {category_name} must be a list for tenant_id: {self.tenant_id}',
                )

            self.categories[category_name] = {
                'label': category_info['label'],
                'courses': self.validated_courses(courses, silent_fail=True),
            }

    def reload(self) -> None:
        """Reload the course categories from the tenant configuration."""
        try:
            category_config = get_tenant_config_value(self.tenant_id, settings.FX_COURSE_CATEGORY_CONFIG_KEY) or {}
        except FXCodedException as exc:
            raise FXCodedException(
                code=FXExceptionCodes.COURSE_CATEGORY_INVALID_SETTINGS,
                message=f'"CourseCategories initialization failed: {str(exc)}"'
            ) from exc

        try:
            self.reformat_categories_and_sorting(
                categories=category_config.get('categories', {}),
                sorting=category_config.get('sorting', {}),
            )

        except (ValueError, KeyError, NameError) as exc:
            raise FXCodedException(
                code=FXExceptionCodes.COURSE_CATEGORY_INVALID_SETTINGS,
                message=f'Invalid course categories configuration for tenant_id: {self.tenant_id}'
            ) from exc

    def save(self) -> None:
        """Save the current course categories to the tenant configuration."""
        if self.read_only:
            raise FXCodedException(
                code=FXExceptionCodes.COURSE_CATEGORY_READ_ONLY,
                message='Cannot save course categories in read-only mode.'
            )

        self.reformat_categories_and_sorting(self.categories, self.sorting)

        set_tenant_config_value(
            tenant_id=self.tenant_id,
            config_key=settings.FX_COURSE_CATEGORY_CONFIG_KEY,
            value={
                'categories': self.categories,
                'sorting': self.sorting,
            }
        )

    def verify_category_name_exists(self, category_name: str) -> None:
        """
        Verify that a category name exists.

        :param category_name: Name of the category to verify.
        :type category_name: str
        """
        if category_name not in self.categories:
            raise FXCodedException(
                code=FXExceptionCodes.COURSE_CATEGORY_INVALID_SETTINGS,
                message=f'Category {category_name} does not exist for tenant_id: {self.tenant_id}'
            )

    def set_courses_for_category(self, category_name: str, courses: List[str]) -> None:
        """
        Set the list of courses for a given category.

        :param category_name: Name of the category to update.
        :type category_name: str
        :param courses: List of course IDs to set for the category.
        :type courses: List[str]
        """
        self.verify_category_name_exists(category_name)

        self.categories[category_name]['courses'] = self.validated_courses(courses)

    def get_category(self, category_name: str) -> Dict[str, Any]:
        """
        Get the details of a category.

        :param category_name: Name of the category to retrieve.
        :type category_name: str
        :return: Details of the category including label and courses.
        :rtype: Dict[str, Any]
        """
        self.verify_category_name_exists(category_name)

        return self.categories[category_name]

    def get_new_category_name(self) -> str:
        """
        Generate a new unique category name.

        :return: A new unique category name.
        :rtype: str
        """
        if len(self.categories) < settings.FX_COURSE_CATEGORY_NAME_MAX_LENGTH:
            base_name = 'category'
            index = 1
            while index < settings.FX_COURSE_CATEGORY_NAME_MAX_LENGTH:
                new_name = f'{base_name}_{index}'
                if new_name not in self.categories:
                    return new_name
                index += 1
        raise FXCodedException(
            code=FXExceptionCodes.COURSE_CATEGORY_TOO_MANY_CATEGORIES,
            message='Unable to generate a new unique category name!',
        )

    def add_category(self, label: Dict[str, str], courses: List[str]) -> str:
        """
        Add a new category.

        :param label: Label for the category in different languages.
        :type label: Dict[str, str]
        :param courses: List of course IDs to include in the category.
        :type courses: List[str]
        :return: The name of the added category.
        :rtype: str
        """
        self.reformat_categories_and_sorting(categories=self.categories, sorting=self.sorting)

        self.categories[self.get_new_category_name()] = {
            'label': label,
            'courses': self.validated_courses(courses),
        }
        self.sorting.append(self.get_new_category_name())

        return self.get_new_category_name()

    def remove_category(self, category_name: str) -> None:
        """
        Remove a category.

        :param category_name: Name of the category to remove.
        :type category_name: str
        """
        self.verify_category_name_exists(category_name)

        del self.categories[category_name]
        self.reformat_categories_and_sorting(categories=self.categories, sorting=self.sorting)

    def set_categories_sorting(self, sorting: List[str]) -> None:
        """
        Set the sorting order of categories.

        :param sorting: List of category names in desired order.
        :type sorting: List[str]
        """
        self.sorting = sorting
        self.reformat_categories_and_sorting(categories=self.categories, sorting=sorting)

    def get_categories_for_course(self, course_id: str) -> Dict[str, Any]:
        """
        Get the categories that a course belongs to.
        :param course_id: ID of the course to check.
        :type course_id: str
        :return: Dictionary of categories information that include the course.
        :rtype: Dict[str, Any]
        """
        result = {}
        for category_name, category_info in self.categories.items():
            if course_id in category_info.get('courses', []):
                result[category_name] = {
                    'label': category_info['label'],
                }
        return result

    def set_categories_for_course(self, course_id: str, category_names: List[str]) -> None:
        """
        Set the categories that a course belongs to.

        :param course_id: ID of the course to update.
        :type course_id: str
        :param category_names: List of category names to assign the course to.
        :type category_names: List[str]
        """
        category_names = list(set(category_names))
        current_category_names = self.get_categories_for_course(course_id).keys()

        for category_name in category_names:
            self.verify_category_name_exists(category_name)
            if category_name not in current_category_names:
                self.categories[category_name]['courses'].append(course_id)

        to_remove = set(current_category_names) - set(category_names)
        for category_name in to_remove:
            self.categories[category_name]['courses'].remove(course_id)

