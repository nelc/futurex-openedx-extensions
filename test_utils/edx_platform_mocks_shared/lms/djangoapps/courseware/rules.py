"""Mocked bridgekeepr lms rules"""


class Rule:
    """Mocked Base class for rules."""
    def check(self, user, instance=None):
        """Check if a user satisfies this rule."""
        raise NotImplementedError()

    def __or__(self, other):
        return True


class HasRolesRule(Rule):  # pylint: disable=too-few-public-methods
    """Mocked HasRolesRule"""
    def __init__(self, *roles):
        self.roles = roles

    def check(self, user=None, instance=None):
        return True


class HasAccessRule(Rule):  # pylint: disable=too-few-public-methods
    """Mocked HasAccessRule"""

    def __init__(self, *roles):
        self.roles = roles

    def check(self, user=None, instance=None):
        return True
