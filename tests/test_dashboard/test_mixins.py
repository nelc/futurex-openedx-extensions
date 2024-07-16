"""Mixin classes for testing."""
from unittest import TestCase
from unittest.mock import patch

import pytest


class MockPatcherMixin(TestCase):
    """Mixin class to automatically start and stop a mock patcher."""
    patching_config = None

    @classmethod
    def setUpClass(cls):
        """ Set up the test class. """
        super().setUpClass()
        if cls.patching_config is None:
            raise ValueError('Fill patching_config attribute, or remove MockPatcherMixin from the inheritance chain.')

        cls.patchers = {
            name: patch(patch_config[0], **patch_config[1])
            for name, patch_config in cls.patching_config.items()
        }

    def setUp(self):
        """Set up the test."""
        super().setUp()
        self.mocks = {name: patcher.start() for name, patcher in self.patchers.items()}

    def tearDown(self):
        """Tear down the test."""
        for patcher in self.patchers.values():
            patcher.stop()
        super().tearDown()


def test_mock_patcher_mixin():
    """Test the MockPatcherMixin."""
    class TestMockPatcherMixin(MockPatcherMixin):
        """Test class for the MockPatcherMixin."""

    with pytest.raises(ValueError) as exc_info:
        TestMockPatcherMixin.setUpClass()
    assert str(exc_info.value) == \
           'Fill patching_config attribute, or remove MockPatcherMixin from the inheritance chain.'
