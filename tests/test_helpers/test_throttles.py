"""Tests for the thorttles module."""
from rest_framework.throttling import AnonRateThrottle

from futurex_openedx_extensions.helpers.throttles import AnonymousDataRetrieveRateThrottle


def test_anonymous_data_retrieve_rate_throttle():
    """Test the AnonymousDataRetrieveRateThrottle."""
    assert issubclass(AnonymousDataRetrieveRateThrottle, AnonRateThrottle)
    assert AnonymousDataRetrieveRateThrottle.scope == 'fx_anonymous_data_retrieve'
