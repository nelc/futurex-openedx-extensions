"""Custom Serializers for the dashboard APIs."""
from __future__ import annotations

import re
from typing import Any

from rest_framework import serializers

from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes


class ExcludedOptionalField:  # pylint: disable=too-few-public-methods
    """Class for excluded optional fields."""


class OptionalFieldsSerializerMixin:
    """
    Mixin to support optional fields.

    Optional fields are seamlessly integrated into the serializer like any other field!

    The optional fields are not included in the response unless they are explicitly requested via query_params. The
    request for the optional fields is made by providing a comma-separated list of tags, not field names. The same tag
    can be used for multiple fields. The tags are case-insensitive, with one shared between all fields by default
    named `__all__`.

    For an API endpoint that supports optional fields, the query_params can look like this:
    `?optional_field_tags=tag1,tag2,tag3`

    The optional fields functionality can be used with GET requests only. The logic is ignored for all other requests
    methods.

    How to use it?
    There are two ways to use this functionality. Whatever way you choose, the following steps are required, note that
        these are all normal django-rest-framework practices:
        * The optional fields must be defined as `SerializerOptionalMethodField` fields.
            * The `field_tags` parameter is mandatory and must be a list of strings, or an empty list.
        * The related method must be defined in the serializer normally. ex `def get_field_name(self, instance):`.
            * No special handling is required for the method.
        * The optional fields must be added to the serializer's `Meta.fields` list normally.

    First (recommended): use it along with the `ModelSerializerOptionalFields` serializer. Or more specifically, with
    a serializer that has `OptionalFieldsSerializerMixin` in its inheritance chain.
        * The related method of the optional field will not be processed unless explicitly requested via query_params.
        * The optional fields will not be included in the response unless explicitly requested via query_params.
        * The optional fields will not be included in the response if the `field_tags` parameter is an empty list.
        * The optional fields are requested by providing a comma-separated list of tags, not field names.

    Second: use it with any other serializer. This means that query_params will not be accessible in the context.
        Therefore, the optional fields will not be processed, unless you manually provide the
        `requested_optional_field_tags` in the context during the creation of the serializer. For example:
        ```
        serializer = AnySerializer(instance, context={'requested_optional_field_tags': ['tag1', 'tag2']})
        ```
        * The related method of the optional field will not be processed unless explicitly requested.
            * If not requested, the field's result-value will be defaulted.
        * The optional fields will always be included in the response.
        * So, without `OptionalFieldsSerializerMixin`, the optional fields will act like an optionally-processed field
            rather than an optional field.

    Here is a simple breakdown of how it's technically working:
    * `ModelSerializerOptionalFields` uses `ListSerializerOptionalFields` as the `list_serializer_class` that adds
        support for optional fields in listing mode (many=True).
    * `ModelSerializerOptionalFields` initializes the `optional_field_names` as an empty list.
    * `ModelSerializerOptionalFields` saves the requested optional field tags in the context under the key
        `requested_optional_field_tags`. The `GET request` object must be provided in the context during the serializer
        creation. Otherwise, the logic of remove-optional-fields-from-final-result will be ignored.
    * `ModelSerializerOptionalFields.to_representation` processes the super's representation which will collect the
        data from the methods and fields normally.
        * `SerializerOptionalMethodField` initializes the `field_tags` parameter as a set of tags that were provided
            during the field's definition. Plus a shared tag named `__all__`.
        * When the parent serializer calls the field's `bind` method during the render,
            `SerializerOptionalMethodField.bind` will add the field name to the `optional_field_names` list of the
            parent serializer, unless the parent serializer is not inherited from `OptionalFieldsSerializerMixin`.
        * `SerializerOptionalMethodField.to_representation` will check for `requested_optional_field_tags` in the
            context and return the value if (at least) one of the field's tags is in the requested tags. Otherwise:
            - parent is inherited from `OptionalFieldsSerializerMixin`: it will return an instance
                of `ExcludedOptionalField` to tell the parent that the field is to be removed from the final result.
            - parent is not inherited from `OptionalFieldsSerializerMixin`: it will return the default of the field
    * `ModelSerializerOptionalFields.to_representation` continues to process the representation and removes the optional
        fields from the final result if they are instances of `ExcludedOptionalField`.
    * Seamless integration of optional fields is achieved!
    """
    optional_field_tags_key = 'optional_field_tags'

    def __init__(self, *args: Any, **kwargs: Any):
        """Initialize the serializer."""
        self.optional_field_names: list = []

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

    def is_optional_field_requested(self, field_name: str) -> bool:
        """Check if the optional field is requested."""
        requested_optional_field_tags = self.context.get(  # type: ignore
            'requested_optional_field_tags', [],
        ) if self.context else []  # type: ignore

        try:
            field = self.fields[field_name]  # type: ignore
        except KeyError as exc:
            raise FXCodedException(
                code=FXExceptionCodes.SERIALIZER_FILED_NAME_DOES_NOT_EXIST,
                message=f'Field "{field_name}" does not exist in {self.__class__.__name__} serializer.',
            ) from exc

        return bool(set(requested_optional_field_tags) & field.field_tags)

    def to_representation(self, instance: Any) -> Any:
        """Return the representation of the instance."""
        representation = super().to_representation(instance)  # type: ignore

        if getattr(self, 'many', False):
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
        self._removable = False

        for field_name in field_tags:
            if not isinstance(field_name, str):
                raise ValueError('SerializerOptionalMethodField: field_tags must be a list of strings.')
            field_name = field_name.strip().lower()
            if not re.match(r'^[a-z][a-z0-9_-]+$', field_name):
                raise ValueError(
                    'SerializerOptionalMethodField: a tag must be at least two characters that start with an '
                    'alphabetical character and contain only alphanumeric characters, underscores, and hyphens.'
                )
            self._field_tags.add(field_name)

    def bind(self, field_name: str, parent: ModelSerializerOptionalFields) -> None:
        """Bind the field."""
        super().bind(field_name, parent)

        if getattr(parent, 'optional_field_names', None) is not None:
            parent.optional_field_names.append(field_name)
            self._removable = True

    @property
    def field_tags(self) -> set:
        """Return the field tags."""
        return self._field_tags

    def to_representation(self, value: Any) -> Any:
        """Return the representation of the value."""
        requested_optional_field_tags = self.context.get('requested_optional_field_tags', []) if self.context else []

        if set(requested_optional_field_tags) & self.field_tags:
            return super().to_representation(value)

        return ExcludedOptionalField() if self._removable else self.default
