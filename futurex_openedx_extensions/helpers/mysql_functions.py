
"""Functions that use db functions not supported by SQLITE."""
import json
from typing import Any

from django.db import transaction
from django.db.models import BooleanField, F, Func, JSONField, QuerySet, Value
from django.db.models.functions import Cast

from futurex_openedx_extensions.helpers.converters import path_to_json


class JsonPathExists(Func):
    """
    Custom ORM function to check if a JSON path exists in a JSON field.
    Equivalent to JSON_CONTAINS_PATH.
    """
    function = 'JSON_CONTAINS_PATH'
    arity = 3
    output_field = BooleanField()

    def __init__(self, expression: F, json_path: str, path_type: str = 'one', **extra: Any):
        super().__init__(expression, Value(path_type), Value(json_path), **extra)

    def __rand__(self, other: Any) -> None:
        return NotImplemented

    def __ror__(self, other: Any) -> None:
        return NotImplemented

    def __rxor__(self, other: Any) -> None:
        return NotImplemented


def annotate_queryset_for_update_draft_config(queryset: QuerySet, key_path: str) -> QuerySet:
    """
    For Draft tenant config update, annotates the queryset with JSON path existence and extracted values.

    :param queryset: The queryset to annotate.
    :param key_path: The key path to check in the JSON field.
    :return: Annotated queryset with JSON-related fields.
    """
    config_draft_path = f'$.config_draft.{key_path}'
    root_path = f'$.{key_path}'

    return queryset.annotate(
        config_draft_exists=JsonPathExists(F('lms_configs'), json_path=config_draft_path),
        root_key_exists=JsonPathExists(F('lms_configs'), json_path=root_path),
        config_draft_value=Func(
            F('lms_configs'), Value(config_draft_path), function='JSON_EXTRACT', output_field=JSONField()
        ),
        root_value=Func(
            F('lms_configs'), Value(root_path), function='JSON_EXTRACT', output_field=JSONField()
        ),
    )


def apply_json_merge_for_update_draft_config(existing_json: F, key_path: str, new_value: Any, reset: bool) -> Func:
    """
    For Draft tenant config update, applies JSON_MERGE_PATCH to update the JSON field with the new config value .

    :param existing_json: The existing JSON field (F object).
    :param key_path: JSON key path to update.
    :param new_value: New value to merge.
    :param reset: Whether to reset the value to None.
    :return: A Func object performing the JSON_MERGE_PATCH operation.
    """
    new_config = {'config_draft': path_to_json(key_path, None if reset else new_value)}
    return Func(
        Func(existing_json, Value('{}'), function='IFNULL'),
        Cast(Value(json.dumps(new_config)), JSONField()),
        function='JSON_MERGE_PATCH',
        output_field=JSONField()
    )


def apply_json_merge_for_publish_draft_config(queryset: QuerySet) -> int:
    """
    For Publish tenant config, applies JSON_MERGE_PATCH that will publish draft config and set draft config empty

    :param existing_json: The existing JSON field (F object).
    :param key_path: JSON key path to update.
    :param new_value: New value to merge.
    :param reset: Whether to reset the value to None.
    :return: A Func object performing the JSON_MERGE_PATCH operation.
    """
    with transaction.atomic():
        queryset.update(
            lms_configs=Func(
                F('lms_configs'),
                Cast(Value(json.dumps(queryset[0].lms_configs.get('config_draft'))), JSONField()),
                function='JSON_MERGE_PATCH'
            )
        )
        updated = queryset.update(
            lms_configs=Func(
                F('lms_configs'),
                Value('$.config_draft'),
                Value('{}'),
                function='JSON_SET'
            )
        )
        return updated
    return 0
