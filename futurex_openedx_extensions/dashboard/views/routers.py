"""Backward-compatible import location for the read-replica DB router.

The router moved to ``futurex_openedx_extensions.helpers.routers``, but deployments
still reference this path in ``DATABASE_ROUTERS``. Re-export it here so the old
dotted path keeps resolving.
"""
from futurex_openedx_extensions.helpers.routers import FXReadReplicaRouter

__all__ = ['FXReadReplicaRouter']
