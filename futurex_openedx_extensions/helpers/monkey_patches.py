"""Monkey patches defined here."""
from __future__ import annotations

from typing import Any

from django.db.models.query import QuerySet

original_queryset_chain = QuerySet._chain  # pylint: disable=protected-access


def customized_queryset_chain(self: Any, **kwargs: Any) -> QuerySet:
    """Customized queryset chain method for the QuerySet class."""
    result = original_queryset_chain(self, **kwargs)

    if hasattr(self, 'removable_annotations'):
        result.removable_annotations = self.removable_annotations.copy()

    return result


QuerySet._chain = customized_queryset_chain  # pylint: disable=protected-access
