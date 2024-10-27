"""Models for the dashboard app."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from futurex_openedx_extensions.helpers import clickhouse_operations as ch
from futurex_openedx_extensions.helpers.converters import DateMethods
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes

User = get_user_model()


class ViewAllowedRoles(models.Model):
    """Allowed roles for every supported view"""
    view_name = models.CharField(max_length=255)
    view_description = models.CharField(null=True, blank=True, max_length=255)
    allowed_role = models.CharField(max_length=255)
    allow_write = models.BooleanField(default=False)

    history = HistoricalRecords()

    class Meta:
        """Metaclass for the model"""
        verbose_name = 'View Allowed Role'
        verbose_name_plural = 'View Allowed Roles'
        unique_together = ('view_name', 'allowed_role')


class ClickhouseQuery(models.Model):
    """Model for storing Clickhouse queries"""
    SCOPE_COURSE = 'course'
    SCOPE_PLATFORM = 'platform'
    SCOPE_TENANT = 'tenant'
    SCOPE_USER = 'user'

    SCOPE_CHOICES = [
        (SCOPE_COURSE, SCOPE_COURSE),
        (SCOPE_PLATFORM, SCOPE_PLATFORM),
        (SCOPE_TENANT, SCOPE_TENANT),
        (SCOPE_USER, SCOPE_USER),
    ]

    BUILTIN_PARAMS = [
        '__orgs_of_tenants__',
        '__ca_users_of_tenants__',
    ]

    PARAM_TYPE_DATE = 'date'
    PARAM_TYPE_FLOAT = 'float'
    PARAM_TYPE_INT = 'int'
    PARAM_TYPE_LIST_STR = 'list_str'
    PARAM_TYPE_STR = 'str'
    ALLOWED_PARAM_TYPES = [
        PARAM_TYPE_DATE,
        PARAM_TYPE_FLOAT,
        PARAM_TYPE_INT,
        PARAM_TYPE_LIST_STR,
        PARAM_TYPE_STR,
    ]

    scope = models.CharField(max_length=16, choices=SCOPE_CHOICES)
    slug = models.CharField(max_length=255)
    version = models.CharField(max_length=4)
    description = models.TextField(null=True, blank=True)
    query = models.TextField()
    params_config = models.JSONField(default=dict, blank=True)
    paginated = models.BooleanField(default=True)
    enabled = models.BooleanField(default=True)
    modified_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        """Metaclass for the model"""
        verbose_name = 'Clickhouse Query'
        verbose_name_plural = 'Clickhouse Queries'
        unique_together = ('scope', 'slug', 'version')

    @classmethod
    def allowed_scopes(cls) -> List[str]:
        """Get the allowed scopes"""
        return [scope[0] for scope in cls.SCOPE_CHOICES]

    def save(self, *args: list, **kwargs: dict) -> None:
        """Override the save method to apply data cleanup"""
        self.clean()
        super().save(*args, **kwargs)

    def clean(self) -> None:
        """Clean the model data"""
        super().clean()

        self.slug = (self.slug or '').lower().strip()
        if not re.match(r'^[a-z0-9-]+$', self.slug):
            raise ValidationError(
                f'Invalid slug ({self.slug}) only lowercase alphanumeric characters and hyphens are allowed'
            )
        self.query = (self.query or '').strip()
        self.scope = (self.scope or '').lower().strip()
        if self.scope not in self.allowed_scopes():
            raise ValidationError(f'Invalid scope: ({self.scope})')
        self.version = (self.version or '').lower().strip()

        if self.enabled:
            self.validate_clickhouse_query()

    @staticmethod
    def str_to_typed_data(data: str, configured_type: str) -> Any:
        """
        Convert the given string into typed data according to the configured type.

        :param data: The data to be converted.
        :type data: str
        :param configured_type: The configured type of the sample data.
        :type configured_type: str
        :return: The parsed sample data.
        :rtype: Any
        """
        if configured_type == ClickhouseQuery.PARAM_TYPE_DATE:
            result: Any = DateMethods.parse_date_method(data)
        elif configured_type == ClickhouseQuery.PARAM_TYPE_INT:
            result = int(data)
        elif configured_type == ClickhouseQuery.PARAM_TYPE_FLOAT:
            result = float(data)
        elif configured_type == ClickhouseQuery.PARAM_TYPE_STR:
            result = data
        elif configured_type == ClickhouseQuery.PARAM_TYPE_LIST_STR:
            result = data.split(',')
        else:
            raise ValueError(f'ClickhouseQuery.str_to_typed_data error: invalid param type: {configured_type}')

        return result

    def get_sample_params(self) -> Dict[str, Any]:
        """Get the sample parameters"""
        error_prefix = 'ClickhouseQuery.get_sample_params error: '
        result: Dict[str, Any] = {}
        for param_name, config in self.params_config.items():
            param_type = config.get('type')
            if param_type is None or param_type not in self.ALLOWED_PARAM_TYPES:
                param_type = param_type or 'None'
                raise ValidationError(f'{error_prefix}Invalid param type: {param_type} for param: {param_name}')

            sample_data = config.get('sample_data')
            optional = config.get('optional', False)

            if not optional and sample_data is None:
                raise ValidationError(f'{error_prefix}No sample data provided for required param: {param_name}')

            if sample_data is not None and not isinstance(sample_data, str):
                raise ValidationError(
                    f'{error_prefix}Invalid sample data: {param_name}. It must be a string regardless of the type'
                )

            if sample_data is not None:
                result[param_name] = self.str_to_typed_data(sample_data, param_type)
            else:
                result[param_name] = None

        result.update({
            '__orgs_of_tenants__': ['org1', 'org2'],
            '__ca_users_of_tenants__': ['user1', 'user2'],
        })
        return result

    def validate_clickhouse_query(self) -> None:
        """Validate the Clickhouse query"""
        if not self.query.lower().startswith('select'):
            raise ValidationError('Query must start with SELECT')

        if self.query.lower().endswith(';'):
            raise ValidationError('Query must not end with a semicolon')

        params = self.get_sample_params()
        try:
            with ch.get_client() as clickhouse_client:
                self.fix_param_types(params=params)
                ch.validate_clickhouse_query(clickhouse_client, self.query, parameters=params)
        except ch.ClickhouseBaseError as exc:
            raise ValidationError(f'Clickhouse Query Error: {exc}') from exc

    @classmethod
    def get_missing_query_ids(cls, compared_to: List[Tuple[str, str, str]]) -> List[Tuple[str, str, str]]:
        """
        Get the missing Clickhouse query IDs.

        :param compared_to: The list of tuples with the scope, slug, and version of the queries to compare to.
        :type compared_to: List[Tuple[str, str, str]]
        :return: The list of missing query IDs.
        :rtype: List[Tuple[str, str, str]]
        """
        all_queries = cls.objects.values_list('scope', 'version', 'slug')
        missing_query_ids = []

        for query_id in compared_to:
            if query_id not in all_queries:
                missing_query_ids.append(query_id)

        return missing_query_ids

    def fix_param_types(self, params: Dict[str, Any]) -> None:
        """
        Validate the parameters and fix their types.

        :param params: The parameters to format the query with.
        :type params: Dict[str, Any]
        """
        error_prefix = f'ClickhouseQuery.fix_param_types error on ({self.scope}.{self.version}.{self.slug}): '
        if not self.enabled:
            raise ValidationError(
                f'{error_prefix}Trying to use a disabled query'
            )

        for param_name, config in self.params_config.items():
            param_type = config['type']
            optional = config.get('optional', False)

            param_value = params.get(param_name)
            if not optional and param_value is None:
                raise ValidationError(f'{error_prefix}Missing required param: {param_name}')

            if param_value is not None:
                params[param_name] = self.str_to_typed_data(param_value, param_type)
            else:
                params[param_name] = None

    @classmethod
    def get_query_record(cls, scope: str, version: str, slug: str) -> ClickhouseQuery | None:
        """
        Get a Clickhouse query record.

        :param scope: The scope of the query.
        :type scope: str
        :param version: The version of the query.
        :type version: str
        :param slug: The slug of the query.
        :type slug: str
        :return: The Clickhouse query record.
        :rtype: ClickhouseQuery
        """
        return cls.objects.filter(scope=scope, version=version, slug=slug).first()

    @classmethod
    def get_default_query_ids(cls) -> List[Tuple[str, str, str]]:
        """
        Get the default Clickhouse query IDs.

        :return: The list of default query IDs.
        :rtype: List[Tuple[str, str, str]]
        """
        queries = ch.get_default_queries()
        query_ids = []
        for scope, versions in queries['default_queries'].items():
            for version, slugs in versions.items():
                for slug in slugs:
                    query_ids.append((scope, version, slug))

        return query_ids

    @classmethod
    def load_missing_queries(cls) -> None:
        """Load the missing Clickhouse queries."""
        missing_ids = cls.get_missing_query_ids(compared_to=cls.get_default_query_ids())
        queries = ch.get_default_queries()

        for scope, version, slug in missing_ids:
            item = queries['default_queries'][scope][version][slug]
            ClickhouseQuery.objects.create(
                scope=scope,
                version=version,
                slug=slug,
                description=item.get('description'),
                query=item['query'],
                params_config=item.get('params_config') or {},
            )

    @classmethod
    def get_missing_queries_count(cls) -> int:
        """Get the count of missing Clickhouse queries."""
        missing_ids = cls.get_missing_query_ids(compared_to=cls.get_default_query_ids())

        return len(missing_ids)


class DataExportTask(models.Model):
    """Model for storing FX Tasks queries"""
    STATUS_IN_QUEUE = 'in_queue'
    STATUS_PROCESSING = 'processing'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_IN_QUEUE, STATUS_IN_QUEUE),
        (STATUS_PROCESSING, STATUS_PROCESSING),
        (STATUS_COMPLETED, STATUS_COMPLETED),
        (STATUS_FAILED, STATUS_FAILED),
    ]

    filename = models.CharField(max_length=255)
    view_name = models.CharField(max_length=255)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_IN_QUEUE)
    progress = models.FloatField(default=0.0)
    notes = models.CharField(max_length=255, default='')
    tenant_id = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        """Metaclass for the model"""
        verbose_name = 'Data Export Task'
        verbose_name_plural = 'Data Export Tasks'

    @classmethod
    def set_status(cls, task_id: int, status: str, error_message: str = None) -> None:
        """
        Set the status of the task.

        :param task_id: The ID of the task.
        :type task_id: int
        :param status: The status to set.
        :type status: str
        :param error_message: The error message to be set when changing status to failed.
        :type error_message: str
        """
        if status not in [choice[0] for choice in cls.STATUS_CHOICES]:
            raise FXCodedException(
                code=FXExceptionCodes.EXPORT_CSV_TASK_CHANGE_STATUS_NOT_POSSIBLE,
                message=f'Invalid status! ({status})'
            )

        fx_task = cls.get_task(task_id)
        if (
            (fx_task.status == status) or  # pylint: disable=too-many-boolean-expressions
            (fx_task.status == cls.STATUS_IN_QUEUE and status != cls.STATUS_PROCESSING) or
            (fx_task.status == cls.STATUS_PROCESSING and status not in [cls.STATUS_COMPLETED, cls.STATUS_FAILED]) or
            (fx_task.status in [cls.STATUS_COMPLETED, cls.STATUS_FAILED])
        ):
            raise FXCodedException(
                code=FXExceptionCodes.EXPORT_CSV_TASK_CHANGE_STATUS_NOT_POSSIBLE,
                message=f'Cannot change task status from ({fx_task.status}) to ({status})'
            )

        fx_task.status = status
        if status == cls.STATUS_FAILED and error_message:
            fx_task.error_message = error_message[:255]
        if status == cls.STATUS_PROCESSING:
            fx_task.started_at = timezone.now()
        if status == cls.STATUS_COMPLETED:
            fx_task.completed_at = timezone.now()
        fx_task.save()

    @classmethod
    def get_status(cls, task_id: int) -> str:
        """
        Get the status of the task.

        :param task_id: The ID of the task.
        :type task_id: int
        :return: The status of the task.
        :rtype: str
        """
        return cls.get_task(task_id).status

    @classmethod
    def get_task(cls, task_id: int) -> DataExportTask:
        """
        Get the task.

        :param task_id: The ID of the task.
        :type task_id: int
        :return: The task.
        :rtype: DataExportTask
        """
        try:
            if not task_id or not isinstance(task_id, int):
                raise FXCodedException(
                    code=FXExceptionCodes.EXPORT_CSV_TASK_NOT_FOUND,
                    message='Invalid task ID!'
                )
            return cls.objects.get(id=task_id)
        except cls.DoesNotExist as exc:
            raise FXCodedException(
                code=FXExceptionCodes.EXPORT_CSV_TASK_NOT_FOUND,
                message='Task not found!'
            ) from exc

    @classmethod
    def set_progress(cls, task_id: int, progress: float) -> None:
        """
        Set the progress of the task.

        :param task_id: The ID of the task.
        :type task_id: int
        :param progress: The progress to set.
        :type progress: float
        """
        fx_task = cls.get_task(task_id)
        if fx_task.status != cls.STATUS_PROCESSING:
            raise FXCodedException(
                code=FXExceptionCodes.EXPORT_CSV_TASK_CANNOT_CHANGE_PROGRESS,
                message=f'Cannot set progress for a task with status ({fx_task.status}).'
            )
        if not isinstance(progress, float) or progress < 0.0 or progress > 1.0:
            raise FXCodedException(
                code=FXExceptionCodes.EXPORT_CSV_TASK_INVALID_PROGRESS_VALUE,
                message=f'Invalid progress value! ({progress}).'
            )
        fx_task.progress = progress
        fx_task.save()
