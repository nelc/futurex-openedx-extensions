"""Mock modulestore"""
from opaque_keys.edx.locator import LibraryLocator


class DummyModuleStore:  # pylint: disable=too-few-public-methods
    """DUmmy module store class"""
    def __init__(self):
        self.ids = ['library-v1:org1+11', 'library-v1:org1+22']

    def get_library_keys(self):
        """mock modulestore library keys method"""
        return [LibraryLocator.from_string(id) for id in self.ids]


def modulestore():
    """mocked modulestore"""
    return DummyModuleStore()
