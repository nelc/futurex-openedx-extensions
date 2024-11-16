"""Tests for monkey patches"""
from unittest.mock import MagicMock, patch

from django.db.models.query import QuerySet

from futurex_openedx_extensions.helpers.monkey_patches import customized_queryset_chain, original_queryset_chain


def test_queryset_chain():
    """Verify that the original_queryset_chain is correctly defined."""
    assert QuerySet._chain == customized_queryset_chain  # pylint: disable=protected-access, comparison-with-callable
    assert original_queryset_chain is not customized_queryset_chain


@patch('futurex_openedx_extensions.helpers.monkey_patches.original_queryset_chain')
def test_customized_queryset_chain_has_attribute(mock_original_queryset_chain):
    """Verify that the customized_queryset_chain is correctly defined."""
    mock_original_queryset_chain.return_value = MagicMock(spec=QuerySet)
    del mock_original_queryset_chain.return_value.removable_annotations

    mock_queryset = MagicMock(spec=QuerySet)
    mock_queryset.removable_annotations = {'annotation1'}
    mock_queryset._chain.return_value = mock_queryset  # pylint: disable=protected-access

    result = customized_queryset_chain(mock_queryset)
    assert result.removable_annotations == mock_queryset.removable_annotations
    mock_original_queryset_chain.assert_called_once_with(mock_queryset)


@patch('futurex_openedx_extensions.helpers.monkey_patches.original_queryset_chain')
def test_customized_queryset_chain_no_attribute(mock_original_queryset_chain):
    """Verify that the customized_queryset_chain is correctly defined."""
    mock_original_queryset_chain.return_value = MagicMock(spec=QuerySet)
    delattr(  # pylint: disable=literal-used-as-attribute
        mock_original_queryset_chain.return_value, 'removable_annotations',
    )

    mock_queryset = MagicMock(spec=QuerySet)
    del mock_queryset.removable_annotations
    mock_queryset._chain.return_value = mock_queryset  # pylint: disable=protected-access

    result = customized_queryset_chain(mock_queryset)
    assert not hasattr(result, 'removable_annotations')
    mock_original_queryset_chain.assert_called_once_with(mock_queryset)
