"""Filters helpers and classes for the API views."""
from rest_framework.filters import OrderingFilter


class DefaultOrderingFilter(OrderingFilter):
    ordering_param = 'sort'
