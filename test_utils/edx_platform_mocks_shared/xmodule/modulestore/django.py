"""Mock modulestore"""
from datetime import datetime
from unittest.mock import Mock

from opaque_keys.edx.locator import LibraryLocator


class MockLibrary:  # pylint: disable=too-few-public-methods
    """Mock Library"""

    def __init__(self, key, display_name, edited_by, edited_on):
        self.location = Mock()
        self.location.library_key = key
        self.display_name = display_name
        self._edited_by = edited_by
        self._edited_on = edited_on


class DummyModuleStore:
    """DUmmy module store class"""
    def __init__(self):
        self.ids = ['library-v1:org1+11', 'library-v1:org1+22', 'library-v1:org5+11']
        self.data = [
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

    def get_library_keys(self):
        """mock modulestore library keys method"""
        return [LibraryLocator.from_string(id) for id in self.ids]

    def get_libraries(self):
        """mock modulestore library keys method"""
        return self.data

    def create_library(self, org, library, user_id, fields):
        """Mock method to simulate creating a library"""
        # Simulate creating a new MockLibrary
        new_library = MockLibrary(
            key=LibraryLocator.from_string(f'library-v1:{org}+{library}'),
            display_name=fields.get('display_name'),
            edited_by=user_id,
            edited_on=datetime.now(),
        )
        self.data.append(new_library)
        return new_library

    def default_store(self, type):   # pylint: disable=unused-argument, redefined-builtin
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
