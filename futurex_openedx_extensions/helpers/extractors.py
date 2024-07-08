"""Helper functions for FutureX Open edX Extensions."""
from __future__ import annotations

import re
from typing import Any, List
from urllib.parse import urlparse

from futurex_openedx_extensions.helpers.constants import COURSE_ID_REGX


def get_course_id_from_uri(uri: str) -> str | None:
    """Extract the course_id from the URI."""
    path_parts = urlparse(uri).path.split('/')

    for part in path_parts:
        result = re.search(r'^' + COURSE_ID_REGX, part)
        if result:
            return result.groupdict().get('course_id')

    return None


def get_first_not_empty_item(items: List, default: Any = None) -> Any:
    """Return the first item in the list that is not empty."""
    return next((item for item in items if item), default)
