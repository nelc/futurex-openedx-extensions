"""Mock modulestore"""
from datetime import datetime
from unittest.mock import Mock

from opaque_keys.edx.locator import CourseLocator, LibraryLocator
from xmodule.modulestore.exceptions import DuplicateCourseError


class MockLibrary:  # pylint: disable=too-few-public-methods
    """Mock Library"""

    def __init__(self, key, display_name, edited_by, edited_on):
        self.location = Mock()
        self.location.library_key = key
        self.display_name = display_name
        self._edited_by = edited_by
        self._edited_on = edited_on


class MockCourse:  # pylint: disable=too-few-public-methods
    """Mock Course object"""
    def __init__(self, org, number, run, user_id, fields=None):  # pylint: disable=unused-argument, too-many-arguments
        self.id = CourseLocator.from_string(f'course-v1:{org}+{number}+{run}')  # pylint: disable=invalid-name
        self.discussions_settings = {}
        self.published_by = user_id


class DummyModuleStore:
    """DUmmy module store class"""
    def __init__(self):
        self.libraries = [
            MockLibrary(
                key=LibraryLocator.from_string('library-v1:org1+11'),
                display_name='Mock Library One org1',
                edited_by=10,
                edited_on=datetime(2025, 1, 1, 12, 0, 0),
            ),
            MockLibrary(
                key=LibraryLocator.from_string('library-v1:org1+22'),
                display_name='Mock Library Two org1',
                edited_by=11,
                edited_on=datetime(2025, 3, 2, 7, 0, 0),
            ),
            MockLibrary(
                key=LibraryLocator.from_string('library-v1:org5+11'),
                display_name='Mock Library one org5',
                edited_by=11,
                edited_on=datetime(2025, 3, 10, 7, 0, 0),
            ),
        ]
        self.courses = [
            MockLibrary(
                key=LibraryLocator.from_string('library-v1:org1+11'),
                display_name='Mock Library One org1',
                edited_by=10,
                edited_on=datetime(2025, 1, 1, 12, 0, 0),
            ),
        ]

    def get_library_keys(self):
        """mock modulestore library keys method"""
        return [fake_lib.location.library_key for fake_lib in self.libraries]

    def get_libraries(self):
        """mock modulestore library keys method"""
        return self.libraries

    def create_library(self, org, library, user_id, fields):
        """Mock method to simulate creating a library"""
        lib_key = LibraryLocator.from_string(f'library-v1:{org}+{library}')

        if lib_key in self.get_library_keys():
            raise DuplicateCourseError('Duplicate course.')

        new_library = MockLibrary(
            key=lib_key,
            display_name=fields.get('display_name'),
            edited_by=user_id,
            edited_on=datetime.now(),
        )
        self.libraries.append(new_library)
        return new_library

    def update_item(self, item, user_id):  # pylint: disable=unused-argument, no-self-use
        """Mock"""
        return None

    def create_course(self, org, number, run, user_id, fields):  # pylint: disable=too-many-arguments, no-self-use
        """Mock method to simulate course creation"""
        return MockCourse(org, number, run, user_id, fields)

    def get_modulestore_type(self):  # pylint: disable=no-self-use
        return 'split'  # mock return value

    def default_store(self, type):   # pylint: disable=unused-argument, redefined-builtin
        """Mock context manager for store operations"""
        # Simulate the store context by returning self for now
        return self

    @property
    def default_modulestore(self):
        """Mock context manager for store operations"""
        # Simulate the store context by returning self for now
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None


def modulestore():
    """mocked modulestore"""
    return DummyModuleStore()
