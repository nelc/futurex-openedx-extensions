"""Tests for docs_utils."""
from unittest.mock import Mock, patch

import pytest

from futurex_openedx_extensions.dashboard.docs_utils import docs


@pytest.fixture
def mock_docs_src():
    """Mock the docs_src dictionary."""
    with patch(
        'futurex_openedx_extensions.dashboard.docs_utils.docs_src',
        {
            'TestClass.method': {
                'summary': 'Test summary',
                'description': 'Test description',
                'parameters': [{'name': 'param1', 'in': 'query', 'required': True}],
            }
        }
    ) as mock:
        yield mock


# Mocking schema_for
@pytest.fixture
def mock_schema_for():
    """Mock the schema_for function."""
    with patch('futurex_openedx_extensions.dashboard.docs_utils.schema_for') as mock:
        yield mock


@pytest.fixture
def mock_schema():
    """Mock the schema function."""
    with patch('futurex_openedx_extensions.dashboard.docs_utils.schema') as mock:
        yield mock


def test_docs_decorator_invalid_input(
    mock_schema_for, mock_docs_src,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Test that ValueError is raised when a non-callable is decorated."""
    decorator = docs('TestClass.method')
    with pytest.raises(ValueError, match='docs decorator must be applied to a callable function or class'):
        decorator(None)


def test_docs_decorator_function(mock_schema, mock_docs_src):  # pylint: disable=unused-argument, redefined-outer-name
    """Test docs decorator when applied to a plain function."""
    mock_schema_decorator = Mock()
    mock_schema.return_value = mock_schema_decorator

    @docs('TestClass.method')
    def my_function():
        """dummy"""

    mock_schema.assert_called_once_with(summary='Test summary', description='Test description', parameters=[
        {'name': 'param1', 'in': 'query', 'required': True}])


def test_docs_decorator_class_method(
    mock_schema_for, mock_docs_src,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Test docs decorator when applied to a class method."""
    mock_schema_for_decorator = Mock()
    mock_schema_for.return_value = mock_schema_for_decorator

    @docs('TestClass.method')
    class TestClass:  # pylint: disable=too-few-public-methods, unused-variable
        """dummy"""
        def method(self):
            """dummy"""

    mock_schema_for.assert_called_once_with(
        'method',
        docstring='Test summary\nTest description',
        parameters=[{'name': 'param1', 'in': 'query', 'required': True}]
    )


def test_docs_decorator_empty_docstring(
    mock_schema_for, mock_docs_src,
):  # pylint: disable=redefined-outer-name
    """Test docs decorator when no summary or description is provided."""
    mock_docs_src['TestClass.method'].pop('summary')
    mock_docs_src['TestClass.method'].pop('description')

    @docs('TestClass.method')
    class TestClass:  # pylint: disable=too-few-public-methods, unused-variable
        """dummy"""
        def method(self):
            """dummy"""

    mock_schema_for.assert_called_once_with('method', docstring=None, parameters=[
        {'name': 'param1', 'in': 'query', 'required': True}
    ])


def test_docs_decorator_nonexistent_class_method(
    mock_schema_for, mock_docs_src,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Test docs decorator when the class_method_name is not in docs_src."""
    with pytest.raises(ValueError) as exc:
        @docs('NonExistentClass.method')
        class TestClass:  # pylint: disable=too-few-public-methods, unused-variable
            """dummy"""
            def method(self):
                """dummy"""

    assert str(exc.value) == 'docs_utils Error: no documentation found for NonExistentClass.method'
