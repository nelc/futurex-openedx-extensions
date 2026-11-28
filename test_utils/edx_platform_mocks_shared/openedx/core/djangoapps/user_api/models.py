"""edx-platform Mocks: user_api models"""


class UserPreference:  # pylint: disable=too-few-public-methods
    """Mock of UserPreference"""
    @classmethod
    def get_value(cls, user, preference_key, default=None):  # pylint: disable=unused-argument
        """Mock of UserPreference.get_value"""
        return default
