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

    def get_library_keys(self):
        """mock modulestore library keys method"""
        return [LibraryLocator.from_string(id) for id in self.ids]

    def get_libraries(self):  # pylint: disable=no-self-use
        """mock modulestore library keys method"""
        return [
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


def modulestore():
    """mocked modulestore"""
    return DummyModuleStore()
