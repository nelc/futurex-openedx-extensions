"""Tests for pagination helpers"""
from rest_framework.pagination import PageNumberPagination

from futurex_openedx_extensions.helpers.pagination import DefaultPagination


def test_default_pagination():
    """Verify that the DefaultPagination class is correctly defined."""
    assert issubclass(DefaultPagination, PageNumberPagination)
    assert DefaultPagination.page_size == 20
    assert DefaultPagination.page_size_query_param == 'page_size'
    assert DefaultPagination.max_page_size == 100
