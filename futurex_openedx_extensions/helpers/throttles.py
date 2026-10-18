"""Throttles for FutureX Open edX Extensions."""
from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from rest_framework.throttling import AnonRateThrottle

logger = logging.getLogger('futurex_openedx_extensions.anonymous_lookup')


class AnonymousLookupThrottle(AnonRateThrottle):
    """
    Rate limit of the anonymous lookups (accessible/v1/info) per client address. Authenticated callers are not
    limited. The client address is DRF's (it honours NUM_PROXIES), so behind proxies that setting must be right.
    A refused request leaves one log record, so a probe of many users shows up.
    """
    scope = 'fx_anonymous_lookup'

    def get_rate(self) -> str:
        """The rate comes from FX_ANONYMOUS_LOOKUP_THROTTLE_RATE, e.g. '60/minute'."""
        return settings.FX_ANONYMOUS_LOOKUP_THROTTLE_RATE

    def allow_request(self, request: Any, view: Any) -> bool:
        """Apply the limit and log a refusal (client address and view only, never the looked-up value)."""
        allowed = super().allow_request(request, view)
        if not allowed:
            logger.warning(
                'anonymous lookup throttled: client=%s view=%s', self.get_ident(request), type(view).__name__,
            )
        return allowed
