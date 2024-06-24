"""Custom throttles for the API views."""
from rest_framework.throttling import AnonRateThrottle


class AnonymousDataRetrieveRateThrottle(AnonRateThrottle):
    """Throttle for anonymous users for data retrieval views."""
    scope = 'fx_anonymous_data_retrieve'
