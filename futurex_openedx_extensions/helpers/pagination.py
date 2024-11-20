"""Pagination helpers and classes for the API views."""
from django.core.paginator import Paginator
from django.db.models.query import QuerySet
from django.utils.functional import cached_property
from rest_framework.pagination import PageNumberPagination

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
