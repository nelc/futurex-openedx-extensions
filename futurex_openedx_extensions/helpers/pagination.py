"""Pagination helpers and classes for the API views."""
from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """Default pagination settings for the API views."""
    page_size: int = 20
    page_size_query_param: str = 'page_size'
    max_page_size: int = 100
