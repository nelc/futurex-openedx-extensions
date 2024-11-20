"""Tests for pagination helpers"""
from unittest.mock import MagicMock, PropertyMock, patch

from django.db.models import QuerySet
from rest_framework.pagination import PageNumberPagination

from futurex_openedx_extensions.helpers.pagination import DefaultPagination, DefaultPaginator


def test_default_pagination():
    """Verify that the DefaultPagination class is correctly defined."""
    assert issubclass(DefaultPagination, PageNumberPagination)
    assert DefaultPagination.page_size == 20
    assert DefaultPagination.page_size_query_param == 'page_size'
    assert DefaultPagination.max_page_size == 100
    assert DefaultPagination.django_paginator_class == DefaultPaginator


@patch('futurex_openedx_extensions.helpers.pagination.Paginator.count', new_callable=PropertyMock)
@patch('futurex_openedx_extensions.helpers.pagination.verify_queryset_removable_annotations')
def test_count_with_query_set_and_removable_annotations(mock_verify, mock_super_count):
    """Verify that the count property is correctly defined."""
    mock_super_count.return_value = 'should not be reached'

    mock_queryset = MagicMock(spec=QuerySet)
    mock_queryset.removable_annotations = {'annotation1'}
    mock_queryset._chain.return_value = mock_queryset  # pylint: disable=protected-access
    mock_queryset.query.annotations = {'annotation1': None, 'annotation2': None}
    mock_queryset.count.return_value = 5

    paginator = DefaultPaginator(mock_queryset, per_page=10)

    assert paginator.count == 5
    assert 'annotation1' not in mock_queryset.query.annotations
    mock_super_count.assert_not_called()
    mock_verify.assert_called_once_with(mock_queryset)


@patch('futurex_openedx_extensions.helpers.pagination.Paginator.count', new_callable=PropertyMock)
@patch('futurex_openedx_extensions.helpers.pagination.verify_queryset_removable_annotations')
def test_count_with_query_set_no_removable_annotations(mock_verify, mock_super_count):
    """Verify that the count property is correctly defined."""
    mock_super_count.return_value = 44

    mock_queryset = MagicMock(spec=QuerySet)
    del mock_queryset.removable_annotations
    mock_queryset.count.return_value = 'should not be reached'
    mock_queryset.query.annotations = {'annotation1': None, 'annotation2': None}

    paginator = DefaultPaginator(mock_queryset, per_page=10)

    assert paginator.count == mock_super_count.return_value
    assert mock_queryset.query.annotations == {'annotation1': None, 'annotation2': None}
    mock_verify.assert_not_called()


@patch('futurex_openedx_extensions.helpers.pagination.Paginator.count', new_callable=PropertyMock)
@patch('futurex_openedx_extensions.helpers.pagination.verify_queryset_removable_annotations')
def test_count_with_not_query_set(mock_verify, mock_super_count):
    """Verify that the count property is correctly defined."""
    mock_super_count.return_value = 44

    object_list = 'not a queryset'
    paginator = DefaultPaginator(object_list, per_page=10)

    assert paginator.count == mock_super_count.return_value
    mock_verify.assert_not_called()
