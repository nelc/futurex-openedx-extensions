"""Test serializers for dashboard app"""
import copy
from unittest.mock import Mock, patch

import pytest
from deepdiff import DeepDiff
from rest_framework.serializers import ModelSerializer

from futurex_openedx_extensions.dashboard.custom_serializers import (
    ExcludedOptionalField,
    ModelSerializerOptionalFields,
    SerializerOptionalMethodField,
)

FIELD_FORMAT_ERROR = (
    'a tag must be at least two characters that start with an alphabetical character and contain only '
    'alphanumeric characters, underscores, and hyphens.'
)


def test_model_serializer_optional_fields_simple():
    """Verify that the ModelSerializerOptionalFields correctly sets the optional fields."""
    assert ModelSerializerOptionalFields.optional_field_tags_key == 'optional_field_tags'

    serializer = ModelSerializerOptionalFields()
    assert isinstance(serializer.optional_field_names, list)
    assert not serializer.optional_field_names


@pytest.mark.parametrize('query_params, method, expected_requested', [
    ({}, 'GET', []),
    ({'optional_field_tags': 'tag1,tag2'}, 'GET', ['tag1', 'tag2']),
    ({'optional_field_tags': 'tag1,tag2'}, 'not_GET', []),
    ({'optional_field_tags': 'tag1,tag2,tag1,Tag2,TAG3'}, 'GET', ['tag1', 'tag2', 'tag3']),
])
def test_model_serializer_optional_fields_requested(query_params, method, expected_requested):
    """Verify that the ModelSerializerOptionalFields saves requested tags correctly."""
    request = Mock(query_params=query_params, method=method)

    serializer = ModelSerializerOptionalFields(context={'request': request})
    assert not DeepDiff(
        serializer.context.get('requested_optional_field_tags', []),
        expected_requested,
        ignore_order=True
    )


@pytest.mark.parametrize('many', [False, True])
@patch('rest_framework.serializers.ModelSerializer.to_representation')
def test_model_serializer_optional_fields_to_representation(mock_super_to_representation, many):
    """Verify that the render of ModelSerializerOptionalFields works fine."""
    request = Mock(query_params={'optional_field_tags': 'tag1,tag2'}, method='GET')
    serializer = ModelSerializerOptionalFields(context={'request': request}, many=many)

    expected_result = {
        'field1': 'value1',
        'field2': ExcludedOptionalField(),
        'field3': 'value3',
        'field4': ExcludedOptionalField(),
    }
    mock_super_to_representation.return_value = copy.deepcopy(expected_result)
    result = serializer.to_representation(['data'] if many else 'data')
    assert not DeepDiff(result, [expected_result] if many else expected_result, ignore_order=True)

    serializer.optional_field_names = ['field1', 'field2']
    mock_super_to_representation.return_value = copy.deepcopy(expected_result)
    result = serializer.to_representation(['data'] if many else 'data')
    expected_result.pop('field2')
    assert not DeepDiff(result, [expected_result] if many else expected_result, ignore_order=True)


def test_serializer_optional_method_field_simple():
    """Verify that the SerializerOptionalMethodField initializes correctly."""
    field = SerializerOptionalMethodField(field_tags=['tag1', 'tag2'])
    assert not (field.field_tags ^ {'__all__', 'tag1', 'tag2'})


@pytest.mark.parametrize('field_tags, expected_err_msg', [
    ('not_list', 'field_tags must be a list of strings.'),
    (None, 'field_tags must be a list of strings.'),
    (['one_of_the_tags_is_not_str', {}], 'field_tags must be a list of strings.'),
    (['1tag'], FIELD_FORMAT_ERROR),
    (['t'], FIELD_FORMAT_ERROR),
    (['tag!'], FIELD_FORMAT_ERROR),
    (['t a g'], FIELD_FORMAT_ERROR),
])
def test_serializer_optional_method_field_invalid_field_tags(field_tags, expected_err_msg):
    """Verify that the SerializerOptionalMethodField raises an exception on invalid field tags."""
    with pytest.raises(ValueError) as exc_info:
        SerializerOptionalMethodField(field_tags=field_tags)
    assert str(exc_info.value) == f'SerializerOptionalMethodField: {expected_err_msg}'


@patch('rest_framework.serializers.SerializerMethodField.bind')
def test_serializer_optional_method_field_invalid_field_bind(mock_super_bind):
    """Verify that the SerializerOptionalMethodField.bind correctly sets the optional field names."""
    optional_fields_names = []
    parent = Mock(optional_field_names=optional_fields_names, spec=ModelSerializerOptionalFields)
    field = SerializerOptionalMethodField(field_tags=['tag1', 'tag2'])

    assert not parent.optional_field_names
    field.bind('some_field_name', parent)

    assert parent.optional_field_names == ['some_field_name']
    mock_super_bind.assert_called_once_with('some_field_name', parent)


def test_serializer_optional_method_field_invalid_field_bind_invalid():
    """
    Verify that the SerializerOptionalMethodField raises an exception when the parent
    is not a ModelSerializerOptionalFields.
    """
    optional_fields_names = []
    not_model_serializer_optional_fields = ModelSerializer
    parent = Mock(optional_field_names=optional_fields_names, spec=not_model_serializer_optional_fields)
    field = SerializerOptionalMethodField(field_tags=['tag1', 'tag2'])

    with pytest.raises(ValueError) as exc_info:
        field.bind('some_field_name', parent)
    assert str(exc_info.value) == (
        'SerializerOptionalMethodField: the parent serializer must be an instance of ModelSerializerOptionalFields.'
    )


@patch('rest_framework.serializers.SerializerMethodField.to_representation')
def test_serializer_optional_method_field_invalid_field_to_representation_default(mock_super_representation):
    """Verify that the SerializerOptionalMethodField """
    field = SerializerOptionalMethodField(field_tags=['tag1', 'tag2'])
    mock_super_representation.return_value = 'processed data'

    assert isinstance(field.to_representation('data'), ExcludedOptionalField), \
        'The field should be exclude by default'
    mock_super_representation.assert_not_called()

    field.root._context = {'requested_optional_field_tags': {'tag3'}}  # pylint: disable=protected-access
    assert isinstance(field.to_representation('data'), ExcludedOptionalField), \
        'The field should be exclude because the tag is not in the requested tags'
    mock_super_representation.assert_not_called()

    field.root._context = {'requested_optional_field_tags': {'tag1'}}  # pylint: disable=protected-access
    assert field.to_representation('data') == 'processed data'
