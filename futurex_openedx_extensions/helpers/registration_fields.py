"""Helpers for the per-tenant custom registration fields"""
# pylint: disable=duplicate-code
from __future__ import annotations

import copy
import logging
import re
from typing import Any, Dict, List

from django.db import transaction
from eox_tenant.models import TenantConfig

from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers.caching import invalidate_cache
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.tenants import cache_name_tenant_readable_lms_configs

log = logging.getLogger(__name__)

FIELD_KEYS = {'name', 'label', 'required', 'hidden', 'options'}
VISIBILITY_REQUIRED = 'required'
VISIBILITY_OPTIONAL = 'optional'
VISIBILITY_HIDDEN = 'hidden'


def _invalid(message: str) -> FXCodedException:
    """Return an invalid-input exception"""
    return FXCodedException(code=FXExceptionCodes.INVALID_INPUT, message=message)


def _get_dict(lms_configs: dict, key: str) -> dict:
    """Return the dict stored under the given key, or an empty dict"""
    value = lms_configs.get(key)
    return value if isinstance(value, dict) else {}


def _get_names(lms_configs: dict) -> List[str]:
    """Return the custom field names stored in extended_profile_fields"""
    names = lms_configs.get(cs.REG_FIELDS_NAMES_KEY)
    return [name for name in names if isinstance(name, str) and name] if isinstance(names, list) else []


def get_registration_fields(lms_configs: dict) -> List[Dict[str, Any]]:
    """
    Return the custom registration fields of a tenant, built from the four lms_configs keys. Only the names listed
    in `extended_profile_fields` are returned, in their stored order. A field is `hidden` when
    `REGISTRATION_EXTRA_FIELDS` marks it hidden or has no entry for it (the registration form does not show it).

    :param lms_configs: The tenant's lms_configs
    :type lms_configs: dict
    :return: The fields
    :rtype: List[Dict[str, Any]]
    """
    visibility = _get_dict(lms_configs, cs.REG_FIELDS_VISIBILITY_KEY)
    options = _get_dict(lms_configs, cs.REG_FIELDS_OPTIONS_KEY)
    translations = _get_dict(lms_configs, cs.REG_FIELDS_TRANSLATIONS_KEY)

    result = []
    for name in _get_names(lms_configs):
        field_visibility = visibility.get(name)
        field_options = options.get(name)
        result.append({
            'name': name,
            'label': {
                language: (
                    translations[language].get(name) if isinstance(translations.get(language), dict) else None
                ) for language in cs.REG_FIELDS_LANGUAGES
            },
            'required': field_visibility == VISIBILITY_REQUIRED,
            'hidden': field_visibility not in (VISIBILITY_REQUIRED, VISIBILITY_OPTIONAL),
            'options': list(field_options) if isinstance(field_options, list) else None,
        })
    return result


def _validate_label(prefix: str, label: Any) -> Dict[str, str]:
    """Validate the label of a field and return it with the values stripped"""
    if not isinstance(label, dict) or set(label) != set(cs.REG_FIELDS_LANGUAGES):
        raise _invalid(f'{prefix}.label must be an object with exactly the keys: {cs.REG_FIELDS_LANGUAGES}.')
    result = {}
    for language in cs.REG_FIELDS_LANGUAGES:
        value = label[language]
        if not isinstance(value, str) or not value.strip():
            raise _invalid(f'{prefix}.label.{language} must be a non-empty string.')
        result[language] = value.strip()
    return result


def _validate_options(prefix: str, options: Any) -> List[str] | None:
    """Validate the options of a field and return them stripped, or None for a free-text field"""
    if options is None:
        return None
    if not isinstance(options, list) or not options:
        raise _invalid(f'{prefix}.options must be null or a non-empty list of strings.')
    if len(options) > cs.REG_FIELDS_MAX_OPTIONS:
        raise _invalid(f'{prefix}.options cannot have more than {cs.REG_FIELDS_MAX_OPTIONS} values.')
    result = []
    seen = set()
    for option in options:
        if not isinstance(option, str) or not option.strip():
            raise _invalid(f'{prefix}.options must contain non-empty strings only.')
        option = option.strip()
        if option.lower() in seen:
            raise _invalid(f'{prefix}.options has a duplicate value: ({option}); values are compared ignoring case.')
        seen.add(option.lower())
        result.append(option)
    return result


def _validate_field(index: int, field: Any, seen_names: set) -> Dict[str, Any]:
    """Validate one field of the payload and return it cleaned"""
    prefix = f'fields[{index}]'
    if not isinstance(field, dict):
        raise _invalid(f'{prefix} must be a JSON object.')
    unknown = set(field) - FIELD_KEYS
    if unknown:
        raise _invalid(f'Unknown keys in {prefix}: {sorted(unknown)}.')

    name = field.get('name')
    if not isinstance(name, str) or not re.match(cs.REG_FIELDS_NAME_PATTERN, name):
        raise _invalid(
            f'{prefix}.name must be snake_case: a lowercase letter, then 1 to 63 lowercase letters, digits or '
            'underscores.'
        )
    if name in cs.REG_FIELDS_RESERVED_NAMES:
        raise _invalid(f'{prefix}.name ({name}) is a stock registration field and cannot be a custom field.')
    if name in seen_names:
        raise _invalid(f'{prefix}.name ({name}) is used by more than one field.')
    seen_names.add(name)

    required = field.get('required')
    hidden = field.get('hidden', False)
    if not isinstance(required, bool):
        raise _invalid(f'{prefix}.required must be true or false.')
    if not isinstance(hidden, bool):
        raise _invalid(f'{prefix}.hidden must be true or false.')
    if required and hidden:
        raise _invalid(f'{prefix} cannot be both required and hidden.')

    return {
        'name': name,
        'label': _validate_label(prefix, field.get('label')),
        'visibility': VISIBILITY_HIDDEN if hidden else VISIBILITY_REQUIRED if required else VISIBILITY_OPTIONAL,
        'options': _validate_options(prefix, field.get('options')),
    }


def validate_registration_fields_payload(payload: Any) -> List[Dict[str, Any]]:
    """
    Validate a registration fields payload and return the cleaned fields.

    :param payload: The request payload: {"fields": [...]}; a `tenant_id` key is accepted and ignored
    :type payload: Any
    :return: The cleaned fields, with `visibility` in place of `required` and `hidden`
    :rtype: List[Dict[str, Any]]
    """
    if not isinstance(payload, dict):
        raise _invalid('The payload must be a JSON object.')
    unknown = set(payload) - {'fields', 'tenant_id'}
    if unknown:
        raise _invalid(f'Unknown keys: {sorted(unknown)}.')
    fields = payload.get('fields')
    if not isinstance(fields, list):
        raise _invalid('fields is required and must be a list.')
    if len(fields) > cs.REG_FIELDS_MAX_FIELDS:
        raise _invalid(f'fields cannot have more than {cs.REG_FIELDS_MAX_FIELDS} fields.')

    seen_names: set = set()
    return [_validate_field(index, field, seen_names) for index, field in enumerate(fields)]


def build_registration_fields_configs(fields: List[Dict[str, Any]], lms_configs: dict) -> Dict[str, Any]:
    """
    Return the new values of the four registration keys for the given cleaned fields.

    The entries of the previous custom fields are replaced by the new ones. Every other entry (stock fields such as
    `national_id`, other languages' labels of kept fields) is preserved untouched. A key the tenant does not have
    is not created when it would be empty.

    :param fields: The cleaned fields (from validate_registration_fields_payload)
    :type fields: List[Dict[str, Any]]
    :param lms_configs: The tenant's current lms_configs
    :type lms_configs: dict
    :return: The new values of the keys to write
    :rtype: Dict[str, Any]
    """
    new_names = [field['name'] for field in fields]
    removed = set(_get_names(lms_configs)) - set(new_names) - set(cs.REG_FIELDS_RESERVED_NAMES)

    visibility = copy.deepcopy(_get_dict(lms_configs, cs.REG_FIELDS_VISIBILITY_KEY))
    options = copy.deepcopy(_get_dict(lms_configs, cs.REG_FIELDS_OPTIONS_KEY))
    translations = copy.deepcopy(_get_dict(lms_configs, cs.REG_FIELDS_TRANSLATIONS_KEY))

    for name in removed:
        visibility.pop(name, None)
        options.pop(name, None)
        for language_labels in translations.values():
            if isinstance(language_labels, dict):
                language_labels.pop(name, None)

    for field in fields:
        name = field['name']
        visibility[name] = field['visibility']
        if field['options'] is None:
            options.pop(name, None)
        else:
            options[name] = field['options']
        for language, label in field['label'].items():
            if not isinstance(translations.get(language), dict):
                translations[language] = {}
            translations[language][name] = label

    result: Dict[str, Any] = {}
    for key, value in [
        (cs.REG_FIELDS_NAMES_KEY, new_names),
        (cs.REG_FIELDS_VISIBILITY_KEY, visibility),
        (cs.REG_FIELDS_OPTIONS_KEY, options),
        (cs.REG_FIELDS_TRANSLATIONS_KEY, translations),
    ]:
        if value or key in lms_configs:
            result[key] = value
    return result


def get_tenant_lms_configs(tenant_id: int) -> dict:
    """
    Return the lms_configs of a tenant.

    :param tenant_id: The tenant ID
    :type tenant_id: int
    :return: The tenant's lms_configs
    :rtype: dict
    """
    lms_configs = TenantConfig.objects.filter(id=tenant_id).values_list('lms_configs', flat=True).first()
    if lms_configs is None:
        raise FXCodedException(
            code=FXExceptionCodes.TENANT_NOT_FOUND,
            message=f'Unable to find tenant with id: {tenant_id}',
        )
    return lms_configs


def update_tenant_registration_fields(tenant_id: int, payload: Any, user: Any) -> dict:
    """
    Validate the payload and write the four registration keys into the tenant's lms_configs in one save.

    :param tenant_id: The tenant ID
    :type tenant_id: int
    :param payload: The request payload
    :type payload: Any
    :param user: The user making the change (for the audit log)
    :type user: Any
    :return: The tenant's new lms_configs
    :rtype: dict
    """
    fields = validate_registration_fields_payload(payload)
    with transaction.atomic():
        try:
            tenant = TenantConfig.objects.select_for_update().get(id=tenant_id)
        except TenantConfig.DoesNotExist as exc:
            raise FXCodedException(
                code=FXExceptionCodes.TENANT_NOT_FOUND,
                message=f'Unable to find tenant with id: {tenant_id}',
            ) from exc

        lms_configs = copy.deepcopy(tenant.lms_configs)
        old_names = _get_names(lms_configs)
        lms_configs.update(build_registration_fields_configs(fields, lms_configs))
        tenant.lms_configs = lms_configs
        tenant.save()
        invalidate_cache(cache_name_tenant_readable_lms_configs(tenant_id))
        invalidate_cache(cs.CACHE_NAME_ALL_EXTENDED_PROFILE_FIELDS)

    log.info(
        'fx.registration_fields.changed user=%s tenant=%s old=%s new=%s',
        getattr(user, 'id', None), tenant_id, old_names, lms_configs.get(cs.REG_FIELDS_NAMES_KEY, []),
    )
    return lms_configs
