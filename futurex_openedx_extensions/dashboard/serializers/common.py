"""Common serializers and mixins for the dashboard API."""
# pylint: disable=too-many-lines
from __future__ import annotations

import re
from typing import Any

from rest_framework import serializers

from futurex_openedx_extensions.dashboard.custom_serializers import (
    ModelSerializerOptionalFields,
    SerializerOptionalMethodField,
)
from futurex_openedx_extensions.helpers.export_csv import get_exported_file_url
from futurex_openedx_extensions.helpers.models import DataExportTask


class DataExportTaskSerializer(ModelSerializerOptionalFields):
    """Serializer for Data Export Task"""
    download_url = SerializerOptionalMethodField(field_tags=['download_url'])

    class Meta:
        model = DataExportTask
        fields = [
            'id',
            'user_id',
            'tenant_id',
            'status',
            'progress',
            'view_name',
            'related_id',
            'filename',
            'notes',
            'created_at',
            'started_at',
            'completed_at',
            'download_url',
            'error_message',
        ]
        read_only_fields = [
            field.name for field in DataExportTask._meta.fields if field.name not in ['notes']
        ]

    def validate_notes(self: Any, value: str) -> str:  # pylint: disable=no-self-use
        """Sanitize the notes field and escape HTML tags."""
        value = re.sub(r'<', '&lt;', value)
        value = re.sub(r'>', '&gt;', value)
        return value

    def get_download_url(self, obj: DataExportTask) -> Any:  # pylint: disable=no-self-use
        """Return download url."""
        return get_exported_file_url(obj)


class ReadOnlySerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Serializer for read-only endpoints."""


class FxPermissionInfoSerializerMixin:
    """
    Mixin to add permission info to serializers.

    This mixin adds two optional fields to the serializer to show the editable status of the object.
    """
    can_edit = SerializerOptionalMethodField(field_tags=['can_edit'], help_text='Can the user edit this object?')
    can_delete = SerializerOptionalMethodField(field_tags=['can_delete'], help_text='Can the user delete this object?')

    def get_can_edit(self, obj: Any) -> Any:  # pylint: disable=no-self-use, unused-argument
        """Check if the user can edit the object."""
        return True

    def get_can_delete(self, obj: Any) -> Any:  # pylint: disable=no-self-use, unused-argument
        """Check if the user can delete the object."""
        return True
