"""Tests for filters helpers"""
from rest_framework.filters import OrderingFilter

from futurex_openedx_extensions.helpers.filters import DefaultOrderingFilter


def test_default_sorting_filter():
    """Verify that the DefaultOrderingFilter class is correctly defined."""
    assert issubclass(DefaultOrderingFilter, OrderingFilter)
    assert DefaultOrderingFilter.ordering_param == 'sort'
