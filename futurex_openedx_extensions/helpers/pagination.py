"""Pagination helpers and classes for the API views."""
from __future__ import annotations

from typing import Any

from django.core.paginator import Paginator
from django.db.models.query import QuerySet
from django.utils.functional import cached_property
from rest_framework.exceptions import NotFound
from rest_framework.pagination import Cursor, CursorPagination, PageNumberPagination

from futurex_openedx_extensions.helpers.querysets import verify_queryset_removable_annotations


class DefaultPaginator(Paginator):
    """Default paginator settings for the API views."""
    @cached_property
    def count(self) -> int:
        """Return the total number of objects, across all pages."""
        if isinstance(self.object_list, QuerySet) and hasattr(self.object_list, 'removable_annotations'):
            verify_queryset_removable_annotations(self.object_list)

            clone = self.object_list._chain()  # pylint: disable=protected-access
            for key in self.object_list.removable_annotations:
                clone.query.annotations.pop(key, None)

            return clone.count()

        return super().count


class DefaultPagination(PageNumberPagination):
    """Default pagination settings for the API views."""
    page_size: int = 20
    page_size_query_param: str = 'page_size'
    max_page_size: int = 100

    django_paginator_class = DefaultPaginator


class IdWindowPagination(CursorPagination):
    """
    Keyset pagination for bulk sync feeds, one primary-key window per request: a page holds the rows with
    `cursor < id <= cursor + window_size` (at most page_size of them), so MySQL reads that PK range only and every page
    costs the same, however large the caller's scope is. A plain `ORDER BY id LIMIT n` over a joined scope makes MySQL
    sort the whole scope first. Pages can be short or empty: follow `next` until it is null. The queryset must be a
    values() queryset that includes `id`.
    """
    page_size: int = 1000
    page_size_query_param: str = 'page_size'
    max_page_size: int = 1000
    ordering: str = 'id'
    window_size: int = 20000
    base_url: str = ''
    next_after: int | None = None

    def paginate_queryset(self, queryset: QuerySet, request: Any, view: Any = None) -> list:
        """Return the rows of the window that starts at the cursor."""
        self.page_size = self.get_page_size(request)
        self.base_url = request.build_absolute_uri()
        cursor = self.decode_cursor(request)
        try:
            after = int(cursor.position) if cursor else 0
        except (TypeError, ValueError) as exc:
            raise NotFound(self.invalid_cursor_message) from exc

        rows = list(queryset.filter(
            id__gt=after, id__lte=after + self.window_size,
        ).order_by('id')[:self.page_size + 1])
        page = rows[:self.page_size]

        if len(rows) > self.page_size:
            self.next_after = page[-1]['id']
        else:
            max_id = queryset.model.objects.using(queryset.db).order_by('-id').values_list('id', flat=True).first()
            self.next_after = after + self.window_size if max_id and after + self.window_size < max_id else None
        return page

    def get_next_link(self) -> str | None:
        """Return the link of the next window, or None after the last one."""
        if self.next_after is None:
            return None
        return self.encode_cursor(Cursor(offset=0, reverse=False, position=str(self.next_after)))

    def get_previous_link(self) -> None:  # pylint: disable=no-self-use
        """A sync feed walks forward only."""
        return None
