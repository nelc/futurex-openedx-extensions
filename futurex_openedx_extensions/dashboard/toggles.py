"""Dashboard utility functions."""
from __future__ import annotations

from edx_toggles.toggles import WaffleFlag

WAFFLE_FLAG_NAMESPACE = 'fx_dashboard'

# .. toggle_name: fx_dashboard.enable_heavy_queries
# .. toggle_implementation: WaffleFlag
# .. toggle_default: False
# .. toggle_description: Enables heavy database queries (certificate counts, completion rates).
#   Disabled by default because the underlying subqueries are expensive.
# .. toggle_use_cases: open_edx
# .. toggle_creation_date: 2026-05-17
FX_HEAVY_QUERIES_FLAG = WaffleFlag(f'{WAFFLE_FLAG_NAMESPACE}.enable_heavy_queries', __name__)


def is_heavy_queries_enabled() -> bool:
    """Return True if the heavy-query waffle flag is active."""
    return FX_HEAVY_QUERIES_FLAG.is_enabled()
