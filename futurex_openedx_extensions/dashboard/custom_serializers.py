"""Serializers for the dashboard details API."""
from __future__ import annotations

import re
from typing import Any

from rest_framework import serializers


class ExcludedOptionalField:  # pylint: disable=too-few-public-methods
    """Class for excluded optional fields."""


class OptionalFieldsSerializerMixin:  # pylint: disable=too-few-public-methods
    """Mixin to support optional fields."""
    optional_field_tags_key = 'optional_field_tags'

    def __init__(self, *args: Any, **kwargs: Any):
        """Initialize the serializer."""
        self.optional_field_names: list = []
        self.many_items_representation = getattr(self, 'many', False)

        if kwargs.get('context', {}).get('request') and kwargs['context']['request'].method == 'GET':
            requested_optional_field_tags = kwargs['context']['request'].query_params.get(
                self.optional_field_tags_key, '',
            ).split(',')
            kwargs['context']['requested_optional_field_tags'] = list({
                tag.strip().lower() for tag in requested_optional_field_tags if tag and tag.strip()
            })

        super().__init__(*args, **kwargs)

    def _remove_optional_fields(self, representation: dict[str, Any]) -> None:
        """Remove the optional fields."""
        for field_name in self.optional_field_names:
            if isinstance(representation.get(field_name), ExcludedOptionalField):
                representation.pop(field_name)

    def to_representation(self, instance: Any) -> Any:
        """Return the representation of the instance."""
        representation = super().to_representation(instance)  # type: ignore

        if self.many_items_representation:
            for item in representation:
                self._remove_optional_fields(item)
        else:
            self._remove_optional_fields(representation)

        return representation


class ListSerializerOptionalFields(
    OptionalFieldsSerializerMixin, serializers.ListSerializer,
):  # pylint: disable=abstract-method
    """List serializer for optional fields."""


class ModelSerializerOptionalFields(OptionalFieldsSerializerMixin, serializers.ModelSerializer):
    """Serializer for optional fields."""

    class Meta:
        list_serializer_class = ListSerializerOptionalFields


class SerializerOptionalMethodField(serializers.SerializerMethodField):  # pylint: disable=abstract-method
    """Serializer method field that is not processed unless explicitly requested via query_params."""
    def __init__(self, field_tags: list, **kwargs: Any):
        """Initialize the serializer method field."""
        super().__init__(**kwargs)

        if not isinstance(field_tags, list):
            raise ValueError('SerializerOptionalMethodField: field_tags must be a list of strings.')

        self._field_tags = {'__all__'}
        for field_name in field_tags:
            if not isinstance(field_name, str):
                raise ValueError('SerializerOptionalMethodField: field_tags must be a list of strings.')
            field_name = field_name.strip().lower()
            if not re.match(r'^[a-z_][a-z0-9_-]+$', field_name):
                raise ValueError(
                    'SerializerOptionalMethodField: a tag must be at least two characters that start with an '
                    'alphabetical character and contain only alphanumeric characters, underscores, and hyphens.'
                )
            self._field_tags.add(field_name)

    def bind(self, field_name: str, parent: ModelSerializerOptionalFields) -> None:
        """Bind the field."""
        super().bind(field_name, parent)

        if not isinstance(parent, ModelSerializerOptionalFields):
            raise ValueError(
                'SerializerOptionalMethodField: the parent serializer must be an instance '
                'of ModelSerializerOptionalFields.'
            )
        parent.optional_field_names.append(field_name)

    @property
    def field_tags(self) -> set:
        """Return the field tags."""
        return self._field_tags

    def to_representation(self, value: Any) -> Any:
        """Return the representation of the value."""
        requested_optional_field_tags = self.context.get('requested_optional_field_tags', []) if self.context else []

        if set(requested_optional_field_tags) & self.field_tags:
            return super().to_representation(value)

        return ExcludedOptionalField()
