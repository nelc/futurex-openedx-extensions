"""edx-drf-extensions Mocks"""
from rest_framework.authentication import BaseAuthentication


class JwtAuthentication(BaseAuthentication):
    """Mock: no JWT in the tests, so the next authentication class decides"""
    www_authenticate_realm = 'api'

    def authenticate(self, request):
        """Mock"""
        return None

    def authenticate_header(self, request):
        """Mock"""
        return f'JWT realm="{self.www_authenticate_realm}"'
