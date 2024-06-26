"""Type conversion helpers"""
from __future__ import annotations

from typing import Any, List
from urllib.parse import urljoin


def ids_string_to_list(ids_string: str) -> List[int]:
    """Convert a comma-separated string of ids to a list of integers. Duplicate ids are not removed."""
    if not ids_string:
        return []
    return [int(id_value.strip()) for id_value in ids_string.split(",") if id_value.strip()]


def error_details_to_dictionary(reason: str, **details: Any) -> dict:
    """Constructing the dictionary for error details"""
    return {
        "reason": reason,
        "details": details,
    }


def relative_url_to_absolute_url(relative_url: str, request: Any) -> str | None:
    """Convert a relative URL to an absolute URL"""
    if request and hasattr(request, 'site') and request.site:
        return urljoin(request.site.domain, relative_url)
    return None
