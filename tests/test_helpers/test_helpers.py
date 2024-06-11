"""Tests for the helper functions in the helpers module."""
import pytest

from futurex_openedx_extensions.helpers.helpers import get_first_not_empty_item


@pytest.mark.parametrize("items, expected, error_message", [
    ([0, None, False, "", 3, "hello"], 3, "Test with a list containing truthy and falsy values"),
    ([0, None, False, ""], None, "Test with a list containing only falsy values"),
    ([1, "a", [1], {1: 1}], 1, "Test with a list containing only truthy values"),
    ([], None, "Test with an empty list"),
    ([0, [], {}, (), "non-empty"], "non-empty", "Test with a list containing mixed types"),
    ([[], {}, (), 5], 5, "Test with a list containing different truthy types"),
    ([None, "test"], "test", "Test with None as an element"),
    ([[None, []], [], [1, 2, 3]], [None, []], "Test with nested lists"),
    (["first", 0, None, False, "", 3, "hello"], "first", "Test with first element truthy")
])
def test_get_first_not_empty_item(items, expected, error_message):
    """Verify that the get_first_not_empty_item function returns the first non-empty item in the list."""
    assert get_first_not_empty_item(items) == expected, f"Failed: {error_message}"
