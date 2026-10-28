"""Helpers for the tenant payments settings (Zeitlabs payments + HyperPay)"""
# pylint: disable=duplicate-code
from __future__ import annotations

import copy
import logging
from typing import Any, Dict
from urllib.parse import urlparse

from django.db import transaction
from eox_tenant.models import TenantConfig

from futurex_openedx_extensions.helpers.caching import invalidate_cache
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.tenants import cache_name_tenant_readable_lms_configs

log = logging.getLogger(__name__)

PAYMENTS_ENABLED_KEY = 'IS_ZEITLABS_PAYMENTS_ENABLED'
PAYMENTS_SETTINGS_KEY = 'ZEITLABS_PAYMENTS_SETTINGS'
HYPERPAY_SETTINGS_KEY = 'HYPERPAY_SETTINGS'
HYPERPAY_MADA_SETTINGS_KEY = 'HYPERPAY_MADA_SETTINGS'

PAYMENTS_SETTINGS_FIELDS = ['organization', 'invoice_prefix', 'valid_currency', 'customer_number']
PAYMENTS_SETTINGS_REQUIRED_FIELDS = ['organization', 'invoice_prefix', 'valid_currency']
HYPERPAY_FIELDS = ['API_URL', 'ENTITY_ID', 'TEST_MODE', 'ACCESS_TOKEN']
HYPERPAY_REQUIRED_FIELDS = ['API_URL', 'ENTITY_ID', 'ACCESS_TOKEN']
SECRET_FIELDS = {'ENTITY_ID', 'ACCESS_TOKEN'}
ALLOWED_HYPERPAY_HOSTS = {'eu-prod.oppwa.com', 'eu-test.oppwa.com'}
ALLOWED_TEST_MODES = {'', 'EXTERNAL', 'INTERNAL'}
PAYMENTS_CURRENCY = 'SAR'

PAYLOAD_SECTIONS = {
    'settings': (PAYMENTS_SETTINGS_KEY, PAYMENTS_SETTINGS_FIELDS),
    'hyperpay': (HYPERPAY_SETTINGS_KEY, HYPERPAY_FIELDS),
    'hyperpay_mada': (HYPERPAY_MADA_SETTINGS_KEY, HYPERPAY_FIELDS),
}


def _invalid(message: str) -> FXCodedException:
    """Return an invalid-input exception"""
    return FXCodedException(code=FXExceptionCodes.INVALID_INPUT, message=message)


def _get_section(lms_configs: dict, key: str) -> dict:
    """Return the settings dict stored under the given key, or an empty dict"""
    value = lms_configs.get(key)
    return value if isinstance(value, dict) else {}


def _is_complete(section: dict, required_fields: list) -> bool:
    """Check that all the required fields have a value"""
    return all(section.get(field) for field in required_fields)


def get_tenant_payment_status(lms_configs: dict) -> Dict[str, bool]:
    """
    Return the payments status of a tenant computed from its lms_configs.

    `active` is true only when the switch is on AND the invoice identity and the card settings are complete,
    which is the state in which a learner can actually pay.

    :param lms_configs: The tenant's lms_configs
    :type lms_configs: dict
    :return: Status flags
    :rtype: Dict[str, bool]
    """
    hyperpay = _get_section(lms_configs, HYPERPAY_SETTINGS_KEY)
    enabled = bool(lms_configs.get(PAYMENTS_ENABLED_KEY))
    configured = (
        _is_complete(_get_section(lms_configs, PAYMENTS_SETTINGS_KEY), PAYMENTS_SETTINGS_REQUIRED_FIELDS) and
        _is_complete(hyperpay, HYPERPAY_REQUIRED_FIELDS)
    )
    return {
        'enabled': enabled,
        'active': enabled and configured,
        'configured': configured,
        'mada_available': configured and _is_complete(
            _get_section(lms_configs, HYPERPAY_MADA_SETTINGS_KEY), HYPERPAY_REQUIRED_FIELDS,
        ),
        'test_mode': bool(hyperpay.get('TEST_MODE')),
    }


def _mask_secret(value: Any) -> Dict[str, Any]:
    """Return the masked form of a secret value"""
    if not value:
        return {'is_set': False, 'last4': None}
    return {'is_set': True, 'last4': str(value)[-4:]}


def get_masked_payment_settings(lms_configs: dict) -> Dict[str, dict]:
    """
    Return the payments settings of a tenant with the secret values masked.

    :param lms_configs: The tenant's lms_configs
    :type lms_configs: dict
    :return: Settings by payload section
    :rtype: Dict[str, dict]
    """
    result = {}
    for section, (key, fields) in PAYLOAD_SECTIONS.items():
        stored = _get_section(lms_configs, key)
        result[section] = {
            field: _mask_secret(stored.get(field)) if field in SECRET_FIELDS else stored.get(field)
            for field in fields
        }
    return result


def _validate_section_values(section: str, values: dict) -> None:
    """Validate the values of one settings section"""
    if values.get('API_URL'):
        parsed = urlparse(values['API_URL'])
        if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HYPERPAY_HOSTS:
            raise _invalid(
                f'{section}.API_URL must be an https URL on one of: {", ".join(sorted(ALLOWED_HYPERPAY_HOSTS))}.'
            )
    if values.get('TEST_MODE', '') not in ALLOWED_TEST_MODES:
        raise _invalid(f'{section}.TEST_MODE must be one of: {sorted(ALLOWED_TEST_MODES)}.')
    if values.get('valid_currency') not in (None, PAYMENTS_CURRENCY):
        raise _invalid(f'{section}.valid_currency must be {PAYMENTS_CURRENCY}.')


def _merge_section(section: str, fields: list, current: dict, values: Any) -> dict:
    """Return the stored values of one settings section with the payload values applied"""
    merged = copy.deepcopy(current)
    if not isinstance(values, dict):
        raise _invalid(f'{section} must be a JSON object.')
    unknown = set(values) - set(fields)
    if unknown:
        raise _invalid(f'Unknown fields in {section}: {sorted(unknown)}.')
    for field, value in values.items():
        if value is None:
            merged.pop(field, None)
        elif not isinstance(value, str):
            raise _invalid(f'{section}.{field} must be a string or null.')
        else:
            merged[field] = value.strip()
    _validate_section_values(section, merged)
    return merged


def build_payment_configs(payload: Any, lms_configs: dict) -> Dict[str, Any]:
    """
    Validate a settings payload and return the four payments keys merged over the current values.

    A field omitted from the payload keeps its stored value, and a field sent as null is removed. Keys the
    tenant does not have and the payload does not touch are left out, so they are not written as empty values.

    :param payload: The request payload
    :type payload: Any
    :param lms_configs: The tenant's current lms_configs
    :type lms_configs: dict
    :return: The new values of the payments keys to write
    :rtype: Dict[str, Any]
    """
    if not isinstance(payload, dict):
        raise _invalid('The payload must be a JSON object.')

    unknown = set(payload) - {'enabled', *PAYLOAD_SECTIONS}
    if unknown:
        raise _invalid(f'Unknown fields: {sorted(unknown)}.')

    result: Dict[str, Any] = {}
    if PAYMENTS_ENABLED_KEY in lms_configs:
        result[PAYMENTS_ENABLED_KEY] = bool(lms_configs[PAYMENTS_ENABLED_KEY])
    if 'enabled' in payload:
        if not isinstance(payload['enabled'], bool):
            raise _invalid('enabled must be true or false.')
        result[PAYMENTS_ENABLED_KEY] = payload['enabled']

    for section, (key, fields) in PAYLOAD_SECTIONS.items():
        values = payload.get(section)
        if values is not None:
            result[key] = _merge_section(section, fields, _get_section(lms_configs, key), values)
        elif key in lms_configs:
            result[key] = copy.deepcopy(_get_section(lms_configs, key))

    status = get_tenant_payment_status({**lms_configs, **result})
    if status['enabled'] and not status['configured']:
        raise _invalid(
            'Payments cannot be enabled until settings (organization, invoice_prefix, valid_currency) and '
            'hyperpay (API_URL, ENTITY_ID, ACCESS_TOKEN) are complete.'
        )

    return result


def update_tenant_payment_configs(tenant_id: int, payload: Any, user: Any) -> dict:
    """
    Validate the payload and write the payments keys into the tenant's lms_configs.

    :param tenant_id: The tenant ID
    :type tenant_id: int
    :param payload: The request payload
    :type payload: Any
    :param user: The user making the change (for the audit log)
    :type user: Any
    :return: The tenant's new lms_configs
    :rtype: dict
    """
    with transaction.atomic():
        try:
            tenant = TenantConfig.objects.select_for_update().get(id=tenant_id)
        except TenantConfig.DoesNotExist as exc:
            raise FXCodedException(
                code=FXExceptionCodes.TENANT_NOT_FOUND,
                message=f'Unable to find tenant with id: {tenant_id}',
            ) from exc

        lms_configs = copy.deepcopy(tenant.lms_configs)
        new_values = build_payment_configs(payload, lms_configs)
        changed_keys = sorted(key for key, value in new_values.items() if lms_configs.get(key) != value)
        lms_configs.update(new_values)
        tenant.lms_configs = lms_configs
        tenant.save()
        invalidate_cache(cache_name_tenant_readable_lms_configs(tenant_id))

    log.info(
        'fx.payments.settings_changed user=%s tenant=%s keys=%s enabled=%s',
        getattr(user, 'id', None), tenant_id, changed_keys, bool(lms_configs.get(PAYMENTS_ENABLED_KEY)),
    )
    return lms_configs
