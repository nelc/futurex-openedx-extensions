"""Helper functions for FutureX Open edX Extensions."""
from __future__ import annotations

from typing import List


def get_first_not_empty_item(items: List, default=None) -> any:
    """Return the first item in the list that is not empty."""
    return next((item for item in items if item), default)
