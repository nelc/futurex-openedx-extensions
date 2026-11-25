"""edx-drf-extensions Mocks"""
from rest_framework.authentication import SessionAuthentication


class SessionAuthenticationAllowInactiveUser(SessionAuthentication):
    """Mock: same rule as the real class - the session's user is accepted whether or not the account is active"""

    def authenticate(self, request):
        """Mock"""
        user = getattr(request._request, 'user', None)  # pylint: disable=protected-access
        if not user or user.is_anonymous:
            return None
        self.enforce_csrf(request)
        return (user, None)
