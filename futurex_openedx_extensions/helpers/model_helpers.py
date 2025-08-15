"""Model helpers for the dashboard app."""
from __future__ import annotations

from typing import Any, Dict, List

from django.conf import settings
from django.db import models
from django.db.models import Case, Q, Value, When

from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes


class NoUpdateQuerySet(models.QuerySet):
    """
    QuerySet that disallows the update method unless the caller explicitly overrides the restriction by passing
    __override_no_update_restriction=True in the update method call.

    This is to prevent accidental updates to models that needs save() method to be called for proper handling of the
    data (since `update` and `bulk_update` do not call `save` method and thus skip any custom logic there). The
    override flag will allow to bypass this restriction when absolutely necessary (when you know what you're doing!).

    Therefore, if someone used the update method in the code; a test should fail. Then the developer should review the
    code and decide if it's safe to use update or if they should use save() instead. If they decide to use update,
    they should pass the override flag to explicitly acknowledge that they are bypassing the restriction.
    """
    def __init__(self, model: Any = None, query: Any = None, using: Any = None, hints: Any = None):
        """Initialize the NoUpdateQuerySet"""
        super().__init__(model, query, using, hints)
        self._override_no_update_restriction = False

    def _clone(self) -> NoUpdateQuerySet:
        """ Override the _clone method to copy the override flag """
        result = super()._clone()
        result._override_no_update_restriction = \
            self._override_no_update_restriction  # pylint: disable=protected-access
        return result

    def allow_update(self) -> NoUpdateQuerySet:
        """
        Allow the update method to be called on this QuerySet. This is a fluent method that returns a new QuerySet
        instance with the override flag set to True.

        When used, the developer is explicitly acknowledging that they are bypassing the restriction.

        :return: A new QuerySet instance with the override flag set to True.
        :rtype: NoUpdateQuerySet
        """
        clone = self._chain()
        clone._override_no_update_restriction = True  # pylint: disable=protected-access
        return clone

    def update(self, **kwargs: Any) -> int:
        """ Override the update method to disallow it unless explicitly overridden """
        if self._override_no_update_restriction:
            return super().update(**kwargs)
        raise AttributeError(f'{self.model.__name__}.objects.update() method is not allowed. Use save() instead.')

    def bulk_update(self, objs: Any, fields: Any, batch_size: Any = None, **kwargs: Any) -> int:
        """ Override the bulk_update method to disallow it """
        if self._override_no_update_restriction:
            return super().bulk_update(objs, fields, batch_size)
        raise AttributeError(f'{self.model.__name__}.objects.bulk_update() method is not allowed. Use save() instead.')


class DraftConfigUpdatePreparer:
    """A helper class to prepare draft configuration updates."""

    def __init__(self, managing_class: Any, tenant_id: int, user: Any) -> None:
        """Initialize the DraftConfigUpdatePreparer with a managing class."""
        self.managing_class = managing_class
        self.tenant_id = tenant_id
        self.user = user

    @staticmethod
    def get_to_delete(to_delete_plan: Dict[str, Any]) -> Q:
        """
        Get a Django QuerySet to delete the specified draft configurations. Returns None if there is nothing to delete.

        :param to_delete_plan: A dictionary of config paths to delete with their current revision IDs.
        :type to_delete_plan: Dict[str, Any]
        :return: A Django QuerySet to delete the specified draft configurations.
        :rtype: Q
        """
        if not to_delete_plan:
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message='get_to_delete, got nothing to delete',
            )

        to_delete = Q()
        for config_path, info in to_delete_plan.items():
            if info['current_revision_id'] >= 0:
                to_delete |= Q(config_path=config_path, revision_id=info['current_revision_id'])
            else:
                to_delete |= Q(config_path=config_path)

        return to_delete

    @staticmethod
    def get_prevent_default_config_value() -> None:
        """
        This is a protection against setting a config value to an unexpected default value. It'll simply return
        a NULL value that'll raise a data constraint error in the SQL update statement if the config_value fell back
        to the default value after skipping all case scenarios.

        The fall-back should never happen. If it does, it means we have a bug in our code.
        """
        return None

    def get_to_update(self, to_update_plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get a list of draft configurations to update for the given tenant and config paths. Returns an empty list if
        there is nothing to update.

        :param to_update_plan: A dictionary of config paths to update with their new values and revision IDs.
        :type to_update_plan: Dict[str, Any]
        :return: update rules for the specified draft configurations.
        :rtype: Dict[str, Any]
        """
        if not to_update_plan:
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message='get_to_update, got nothing to update'
            )

        for config_path, info in to_update_plan.items():
            if info['current_revision_id'] >= 0:
                info['q'] = Q(config_path=config_path, revision_id=info['current_revision_id'])
            else:
                info['q'] = Q(config_path=config_path)

        return {
            # we use Case/When to build a conditional update statement instead of using bulk_update that doesn't help
            # us with tracking the change the way we want
            'config_value': Case(
                *[
                    When(
                        info['q'],
                        then=Value(self.managing_class.get_save_ready_config_value(info['new_config_value']))
                    ) for config_path, info in to_update_plan.items()
                ],
                default=self.get_prevent_default_config_value(),
            ),
            'revision_id': Case(
                *[
                    When(
                        info['q'],
                        then=Value(info['new_revision_id'])
                    ) for config_path, info in to_update_plan.items()
                ],
                default=self.get_prevent_default_config_value(),
            ),
            'updated_by': self.user,
        }

    def get_to_create(self, to_create_plan: Dict[str, Any]) -> List[Any]:
        """
        Get a list of draft configurations to create for the given tenant and config paths. Returns an empty list if
        there is nothing to create.

        :param to_create_plan: A dictionary of config paths to create with their new values.
        :type to_create_plan: Dict[str, Any]
        :return: A list of draft configurations to bulk create.
        :rtype: List[Any]
        """
        if not to_create_plan:
            raise FXCodedException(
                code=FXExceptionCodes.INVALID_INPUT,
                message='get_to_create, got nothing to create',
            )

        new_objects = []
        for config_path, item in to_create_plan.items():
            new_objects.append(self.managing_class(
                tenant_id=self.tenant_id,
                config_path=config_path,
                config_value=self.managing_class.get_save_ready_config_value(item['new_config_value']),
                revision_id=item['new_revision_id'],
                created_by=self.user,
                updated_by=self.user,
            ))

        return new_objects

    def get_fast_access(self, tenant_id: int, config_paths: List[str]) -> Dict[str, Any]:
        """
        Get a fast access dictionary of draft configurations for the given tenant and config paths.

        :param tenant_id: The tenant ID to filter the draft configurations.
        :type tenant_id: int
        :param config_paths: A list of config paths to filter the draft configurations.
        :type config_paths: List[str]
        :return: A dictionary of draft configurations with config paths as keys.
        :rtype: Dict[str, Any]
        """
        return {
            item['config_path']: {
                'pk': item['pk'],
                'config_value': item['config_value'],
                'revision_id': item['revision_id']
            }
            for item in self.managing_class.objects.filter(
                tenant_id=tenant_id, config_path__in=config_paths,
            ).values('config_path', 'pk', 'config_value', 'revision_id')
        }

    @staticmethod
    def _get_current_revision_id(config_path: str, draft_fast_access: Any, verify_revision_ids: Any) -> int:
        """Helper method to get the current revision ID for a given config path."""
        if settings.FX_DISABLE_CONFIG_VALIDATIONS:
            return -1
        if verify_revision_ids and verify_revision_ids.get(config_path, -1) >= 0:
            return verify_revision_ids[config_path]
        if config_path in draft_fast_access:
            return draft_fast_access[config_path]['revision_id']
        return -1

    def get_update_plan(
        self,
        tenant_id: int,
        config_paths: List[str],
        src: Dict[str, Any],
        verify_revision_ids: Dict[str, int] = None,
    ) -> Dict[str, Any]:
        """
        Private helper method to prepare the update from dict operation.

        returns update plan in the following format:
        {
            'to_delete': {
                'config_path': {
                    'current_revision_id': int,
                },
            },
            'to_update': {
                'config_path': {
                    'pk': int,
                    'new_config_value': Any,
                    'current_revision_id': int,
                    'new_revision_id': int,
                },
            },
            'to_create': {
                'config_path': {
                    'new_config_value': Any,
                    'new_revision_id': int,
                },
            },
        }

        :param tenant_id: The tenant ID to filter the draft configurations.
        :type tenant_id: int
        :param config_paths: A list of config paths to filter the draft configurations.
        :type config_paths: List[str]
        :param src: The source dictionary to read the configuration values from.
        :type src: Dict[str, Any]
        :param verify_revision_ids: A dictionary of config paths to verify with their expected revision IDs.
        :type verify_revision_ids: Dict[str, int], optional
        :return: A dictionary containing the update plan.
        :rtype: Dict[str, Any]
        """
        draft_fast_access = self.get_fast_access(tenant_id, config_paths)

        result: Dict[str, Dict[str, Any]] = {
            'to_delete': {},
            'to_update': {},
            'to_create': {},
        }
        for config_path in config_paths:
            current_revision_id = self._get_current_revision_id(config_path, draft_fast_access, verify_revision_ids)

            value: Dict[str, Any] | None = src
            parts = config_path.split('.') if config_path else []
            for part in parts:
                if not isinstance(value, dict) or value.get(part) is None:
                    value = None
                    break
                value = value[part]
            if not config_path:
                raise FXCodedException(
                    code=FXExceptionCodes.INVALID_INPUT,
                    message='get_update_plan, got empty config_path',
                )

            if value is None:
                if draft_fast_access.get(config_path):
                    result['to_delete'][config_path] = {
                        'current_revision_id': current_revision_id,
                    }
            elif config_path in draft_fast_access:
                draft_config = self.managing_class.json_load_config_value(
                    draft_fast_access[config_path]['config_value']
                )
                if draft_config != value:
                    result['to_update'][config_path] = {
                        'pk': draft_fast_access[config_path]['pk'],
                        'new_config_value': value,
                        'current_revision_id': current_revision_id,
                        'new_revision_id': self.managing_class.generate_revision_id(),
                    }
            else:
                result['to_create'][config_path] = {
                    'new_config_value': value,
                    'new_revision_id': self.managing_class.generate_revision_id(),
                }

        return result
