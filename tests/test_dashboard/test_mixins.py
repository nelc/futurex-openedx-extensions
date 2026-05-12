"""Mixin classes for testing."""
from unittest import TestCase
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIRequestFactory, APITestCase

from tests.fixture_helpers import get_user1_fx_permission_info


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


class BaseTestViewMixin(APITestCase):
    """Base test view mixin"""
    VIEW_NAME = 'view name is not set!'

    def setUp(self):
        """Setup"""
        self.view_name = self.VIEW_NAME
        self.url_args = []
        self.staff_user = 2

    @property
    def url(self):
        """Get the URL"""
        return reverse(self.view_name, args=self.url_args)

    def login_user(self, user_id):
        """Helper to login user"""
        self.client.force_login(get_user_model().objects.get(id=user_id))

    def _get_request(self):
        """Helper to get the request"""
        factory = APIRequestFactory()
        request = factory.get(self.url)
        request.query_params = {}
        request.user = get_user_model().objects.get(id=self.staff_user)
        request.fx_permission_info = get_user1_fx_permission_info()
        request.fx_permission_info['user'] = request.user
        return request
