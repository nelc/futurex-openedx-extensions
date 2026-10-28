"""Pagination helpers and classes for the API views."""
from __future__ import annotations

from typing import Any

from django.core.paginator import Paginator
from django.db.models.query import QuerySet
from django.utils.functional import cached_property
from rest_framework.exceptions import NotFound
from rest_framework.pagination import Cursor, CursorPagination, PageNumberPagination
from rest_framework.response import Response

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

    Every response also carries `page` (1 for the first call) and `count`, the total rows of the walk. The total is
    counted once, on the call without a cursor, by the view's `get_total_count()` (or `queryset.count()`), and travels
    in the cursor afterwards, so the later pages never count again. A cursor from before this field existed (a bare
    id) still works; its walk reports `page` and `count` as null.

    When the view's `is_narrow_scope()` is true (the rows of a few learners only), the walk has no id windows: every
    page holds the next page_size rows, and the total is counted live, which is cheap for so few rows.
    """
    page_size: int = 1000
    page_size_query_param: str = 'page_size'
    max_page_size: int = 1000
    ordering: str = 'id'
    window_size: int = 20000
    base_url: str = ''
    next_after: int | None = None
    page_number: int | None = None
    total_count: int | None = None

    def _read_position(self, request: Any, queryset: QuerySet, view: Any, narrow: bool) -> int:
        """Read `after`, the page number and the total from the cursor; count the total on the first call."""
        cursor = self.decode_cursor(request)
        if cursor is None:
            self.page_number = 1
            if narrow or not hasattr(view, 'get_total_count'):
                self.total_count = queryset.count()
            else:
                self.total_count = view.get_total_count()
            return 0

        parts = cursor.position.split(':') if cursor.position else []
        try:
            after = int(parts[0])
            self.page_number = int(parts[1]) if len(parts) == 3 and parts[1] else None
            self.total_count = int(parts[2]) if len(parts) == 3 and parts[2] else None
        except (IndexError, ValueError) as exc:
            raise NotFound(self.invalid_cursor_message) from exc
        if len(parts) not in (1, 3):
            raise NotFound(self.invalid_cursor_message)
        return after

    def paginate_queryset(self, queryset: QuerySet, request: Any, view: Any = None) -> list:
        """Return the rows of the window that starts at the cursor."""
        self.page_size = self.get_page_size(request)
        self.base_url = request.build_absolute_uri()
        narrow = bool(view is not None and hasattr(view, 'is_narrow_scope') and view.is_narrow_scope())
        after = self._read_position(request, queryset, view, narrow)

        window = {} if narrow else {'id__lte': after + self.window_size}
        rows = list(queryset.filter(id__gt=after, **window).order_by('id')[:self.page_size + 1])
        page = rows[:self.page_size]

        if len(rows) > self.page_size:
            self.next_after = page[-1]['id']
        elif narrow:
            self.next_after = None
        else:
            max_id = queryset.model.objects.using(queryset.db).order_by('-id').values_list('id', flat=True).first()
            self.next_after = after + self.window_size if max_id and after + self.window_size < max_id else None
        return page

    def get_next_link(self) -> str | None:
        """Return the link of the next window, or None after the last one."""
        if self.next_after is None:
            return None
        next_page = '' if self.page_number is None else str(self.page_number + 1)
        total = '' if self.total_count is None else str(self.total_count)
        return self.encode_cursor(Cursor(offset=0, reverse=False, position=f'{self.next_after}:{next_page}:{total}'))

    def get_previous_link(self) -> str | None:  # pylint: disable=no-self-use
        """A sync feed walks forward only."""
        return None

    def get_paginated_response(self, data: Any) -> Response:
        """The page, with the total of the walk and the page number."""
        return Response({
            'count': self.total_count,
            'page': self.page_number,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
        })
