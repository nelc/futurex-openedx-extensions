"""Filters helpers and classes for the API views."""
from rest_framework.filters import OrderingFilter, SearchFilter


class DefaultOrderingFilter(OrderingFilter):
    ordering_param = 'sort'


class DefaultSearchFilter(SearchFilter):
    search_param = 'search_text'
