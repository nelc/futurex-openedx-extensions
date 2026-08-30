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


# .. toggle_name: fx_dashboard.enable_learner_certificates
# .. toggle_implementation: WaffleFlag
# .. toggle_default: False
# .. toggle_description: Enables the per-learner certificate queries (per-learner certificate
#   counts and certificate_available). Disabled by default because these are per-user subqueries
#   that the CourseStat cache cannot serve.
# .. toggle_use_cases: open_edx
# .. toggle_creation_date: 2026-06-15
FX_LEARNER_CERTIFICATES_FLAG = WaffleFlag(f'{WAFFLE_FLAG_NAMESPACE}.enable_learner_certificates', __name__)


def is_learner_certificates_enabled() -> bool:
    """Return True if the per-learner certificate waffle flag is active."""
    return FX_LEARNER_CERTIFICATES_FLAG.is_enabled()


# .. toggle_name: fx_dashboard.legacy_filtered_counts
# .. toggle_implementation: WaffleFlag
# .. toggle_default: False
# .. toggle_description: Restores the historical filtered counting behaviour. Counts are raw by
#   default: they report every matching row, which is what Open edX's own screens report, so the two
#   systems agree. Activate this flag to go back to excluding deactivated accounts, platform staff,
#   course-team staff and hidden courses. It exists as an instant rollback: the raw counts are much
#   larger than the filtered ones (for one production course, 77,984 rather than 76,246), so if a
#   consumer cannot cope with the change this can be flipped without a redeploy.
# .. toggle_use_cases: open_edx
# .. toggle_creation_date: 2026-08-30
FX_LEGACY_FILTERED_COUNTS_FLAG = WaffleFlag(f'{WAFFLE_FLAG_NAMESPACE}.legacy_filtered_counts', __name__)


def is_legacy_filtered_counts_enabled() -> bool:
    """Return True if counts should keep the historical filtering instead of reporting raw rows."""
    return FX_LEGACY_FILTERED_COUNTS_FLAG.is_enabled()
