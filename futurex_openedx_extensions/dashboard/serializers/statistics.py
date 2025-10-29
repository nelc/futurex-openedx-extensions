"""Statistics-related serializers for the dashboard API."""
from __future__ import annotations

from rest_framework import serializers

from futurex_openedx_extensions.helpers.converters import DEFAULT_DATETIME_FORMAT


class ReadOnlySerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Serializer for read-only endpoints."""

    def create(self, validated_data: any) -> any:
        """Not implemented: Create a new object."""
        raise ValueError('This serializer is read-only and does not support object creation.')

    def update(self, instance: any, validated_data: any) -> any:
        """Not implemented: Update an existing object."""
        raise ValueError('This serializer is read-only and does not support object updates.')


class AggregatedCountsQuerySettingsSerializer(ReadOnlySerializer):
    """Serializer for aggregated counts settings."""
    aggregate_period = serializers.CharField()
    date_from = serializers.DateTimeField(format=DEFAULT_DATETIME_FORMAT)
    date_to = serializers.DateTimeField(format=DEFAULT_DATETIME_FORMAT)


class AggregatedCountsTotalsSerializer(ReadOnlySerializer):
    enrollments_count = serializers.IntegerField(required=False, allow_null=True)


class AggregatedCountsValuesSerializer(ReadOnlySerializer):
    label = serializers.CharField()
    value = serializers.IntegerField()


class AggregatedCountsAllTenantsSerializer(ReadOnlySerializer):
    enrollments_count = AggregatedCountsValuesSerializer(required=False, allow_null=True, many=True)
    totals = AggregatedCountsTotalsSerializer()


class AggregatedCountsOneTenantSerializer(AggregatedCountsAllTenantsSerializer):
    tenant_id = serializers.IntegerField()


class AggregatedCountsSerializer(ReadOnlySerializer):
    query_settings = AggregatedCountsQuerySettingsSerializer()
    all_tenants = AggregatedCountsAllTenantsSerializer()
    by_tenant = AggregatedCountsOneTenantSerializer(many=True)
    limited_access = serializers.BooleanField()
