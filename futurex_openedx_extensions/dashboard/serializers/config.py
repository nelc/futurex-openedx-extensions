"""Configuration-related serializers for the dashboard API."""
from __future__ import annotations

import os
from typing import Any, Dict

from django.utils.timezone import now
from eox_tenant.models import TenantConfig
from rest_framework import serializers

from futurex_openedx_extensions.dashboard.custom_serializers import SerializerOptionalMethodField
from futurex_openedx_extensions.helpers.constants import ALLOWED_FILE_EXTENSIONS
from futurex_openedx_extensions.helpers.models import TenantAsset
from futurex_openedx_extensions.helpers.tenants import get_all_tenants_info


class FxPermissionInfoSerializerMixin:
    """
    Mixin to add permission info to serializers.

    This mixin adds two optional fields to the serializer to show the editable status of the object.
    """
    can_edit = SerializerOptionalMethodField(field_tags=['can_edit'], help_text='Can the user edit this object?')
    can_delete = SerializerOptionalMethodField(field_tags=['can_delete'], help_text='Can the user delete this object?')

    @property
    def fx_permission_info(self) -> dict[str, Any]:
        """Get the fx_permission_info from the context."""
        return self.context.get('request').fx_permission_info  # type: ignore

    def get_can_edit(self, obj: Any) -> Any:  # pylint: disable=no-self-use, unused-argument
        """Check if the user can edit the object."""
        return True

    def get_can_delete(self, obj: Any) -> Any:  # pylint: disable=no-self-use, unused-argument
        """Check if the user can delete the object."""
        return True


class ReadOnlySerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Serializer for read-only endpoints."""

    def create(self, validated_data: Any) -> Any:
        """Not implemented: Create a new object."""
        raise ValueError('This serializer is read-only and does not support object creation.')

    def update(self, instance: Any, validated_data: Any) -> Any:
        """Not implemented: Update an existing object."""
        raise ValueError('This serializer is read-only and does not support object updates.')


class FileUploadSerializer(FxPermissionInfoSerializerMixin, ReadOnlySerializer):
    """
    Serializer for handling the file upload request. It validates and serializes the input data.
    """
    file = serializers.FileField(help_text='File to be uploaded')
    slug = serializers.SlugField(help_text='File slug. Only alphanumeric characters, and underscores are allowed.')
    tenant_id = serializers.IntegerField(help_text='Tenant ID')

    def validate_tenant_id(self, value: int) -> int:
        """
        Custom validation for tenant_id to ensure that the tenant exists.
        """
        try:
            TenantConfig.objects.get(id=value)
        except TenantConfig.DoesNotExist as exc:
            raise serializers.ValidationError(f'Tenant with ID {value} does not exist.') from exc

        if value not in self.fx_permission_info['view_allowed_tenant_ids_full_access']:
            raise serializers.ValidationError(f'User does not have have required access for tenant ({value}).')

        return value


class TenantAssetSerializer(FxPermissionInfoSerializerMixin, serializers.ModelSerializer):
    """Serializer for Data Export Task"""
    file_url = serializers.SerializerMethodField()
    file = serializers.FileField(write_only=True)
    tenant_id = serializers.PrimaryKeyRelatedField(queryset=TenantConfig.objects.all(), source='tenant')

    class Meta:
        model = TenantAsset
        fields = ['id', 'tenant_id', 'slug', 'file', 'file_url', 'updated_by', 'updated_at']
        read_only_fields = ['id', 'updated_at', 'file_url', 'updated_by']

    def __init__(self, *args: Any, **kwargs: Any):
        """Override init to dynamically change fields. This change is only for swagger docs"""
        include_write_only = kwargs.pop('include_write_only', True)
        super().__init__(*args, **kwargs)
        if include_write_only is False:
            self.fields.pop('file')

    def get_unique_together_validators(self) -> list:
        """
        Overriding this method to bypass the unique_together constraint on 'tenant' and 'slug'.
        This prevents an error from being raised before reaching the create or update logic.
        """
        return []

    def validate_file(self, file: Any) -> Any:  # pylint: disable=no-self-use
        """
        Custom validation for file to ensure file extension.
        """
        file_extension = os.path.splitext(file.name)[1]
        if file_extension.lower() not in ALLOWED_FILE_EXTENSIONS:
            raise serializers.ValidationError(f'Invalid file type. Allowed types are {ALLOWED_FILE_EXTENSIONS}.')
        return file

    def validate_tenant_id(self, tenant: TenantConfig) -> int:
        """
        Custom validation for tenant to ensure that the tenant permissions.
        """
        if tenant.id not in self.fx_permission_info['view_allowed_tenant_ids_full_access']:
            template_tenant_id = get_all_tenants_info()['template_tenant']['tenant_id']
            if self.fx_permission_info['is_system_staff_user'] and template_tenant_id == tenant.id:
                return tenant
            raise serializers.ValidationError(
                f'User does not have have required access for tenant ({tenant.id}).'
            )

        return tenant

    def validate_slug(self, slug: str) -> str:
        """
        Custom validation for the slug to ensure it doesn't start with an underscore unless the user is a system staff.
        """
        if slug.startswith('_') and not self.fx_permission_info['is_system_staff_user']:
            raise serializers.ValidationError(
                'Slug cannot start with an underscore unless the user is a system staff.'
            )
        return slug

    def get_file_url(self, obj: TenantAsset) -> Any:  # pylint: disable=no-self-use
        """Return file url."""
        return obj.file.url

    def create(self, validated_data: dict) -> TenantAsset:
        """
        Override the create method to handle scenarios where a user tries to upload a new asset with the same slug
        for the same tenant. Instead of creating a new asset, the existing asset will be updated with the new file.
        """
        request = self.context.get('request')
        asset, _ = TenantAsset.objects.update_or_create(
            tenant=validated_data['tenant'], slug=validated_data['slug'],
            defaults={
                'file': validated_data['file'],
                'updated_by': request.user,
                'updated_at': now()
            }
        )
        return asset


class TenantConfigSerializer(ReadOnlySerializer):
    """Serializer for Tenant Configurations."""
    values = serializers.DictField(default=dict)
    not_permitted = serializers.ListField(child=serializers.CharField(), default=list)
    bad_keys = serializers.ListField(child=serializers.CharField(), default=list)
    revision_ids = serializers.SerializerMethodField()

    def get_revision_ids(self, obj: Any) -> Dict[str, str]:  # pylint: disable=no-self-use
        """Return the revision IDs as strings."""
        revision_ids = obj.get('revision_ids', {})
        return {key: str(value) for key, value in revision_ids.items()}
