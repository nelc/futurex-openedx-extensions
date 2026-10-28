"""Tests for the tenant payments settings helpers"""
from unittest.mock import Mock, patch

import pytest
from eox_tenant.models import TenantConfig

from futurex_openedx_extensions.helpers import payments
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes

COMPLETE_SETTINGS = {'organization': 'Org', 'invoice_prefix': 'ORG', 'valid_currency': 'SAR'}
COMPLETE_HYPERPAY = {'API_URL': 'https://eu-prod.oppwa.com/', 'ENTITY_ID': 'entity1234', 'ACCESS_TOKEN': 'token5678'}


def _configured(enabled=True, **extra):
    """Return lms_configs of a tenant with complete payments settings"""
    return {
        payments.PAYMENTS_ENABLED_KEY: enabled,
        payments.PAYMENTS_SETTINGS_KEY: dict(COMPLETE_SETTINGS),
        payments.HYPERPAY_SETTINGS_KEY: dict(COMPLETE_HYPERPAY),
        **extra,
    }


@pytest.mark.parametrize('lms_configs, expected', [
    ({}, {'enabled': False, 'active': False, 'configured': False, 'mada_available': False, 'test_mode': False}),
    (_configured(), {'enabled': True, 'active': True, 'configured': True, 'mada_available': False, 'test_mode': False}),
    (_configured(enabled=False), {
        'enabled': False, 'active': False, 'configured': True, 'mada_available': False, 'test_mode': False,
    }),
    ({payments.PAYMENTS_ENABLED_KEY: True, payments.HYPERPAY_SETTINGS_KEY: 'not-a-dict'}, {
        'enabled': True, 'active': False, 'configured': False, 'mada_available': False, 'test_mode': False,
    }),
    (_configured(**{
        payments.HYPERPAY_MADA_SETTINGS_KEY: dict(COMPLETE_HYPERPAY),
        payments.HYPERPAY_SETTINGS_KEY: {**COMPLETE_HYPERPAY, 'TEST_MODE': 'EXTERNAL'},
    }), {'enabled': True, 'active': True, 'configured': True, 'mada_available': True, 'test_mode': True}),
])
def test_get_tenant_payment_status(lms_configs, expected):
    """Verify the status flags"""
    assert payments.get_tenant_payment_status(lms_configs) == expected


def test_get_masked_payment_settings():
    """Verify that secrets are masked and other values returned as stored"""
    result = payments.get_masked_payment_settings(_configured())
    assert result['settings'] == {**COMPLETE_SETTINGS, 'customer_number': None}
    assert result['hyperpay'] == {
        'API_URL': 'https://eu-prod.oppwa.com/',
        'ENTITY_ID': {'is_set': True, 'last4': '1234'},
        'TEST_MODE': None,
        'ACCESS_TOKEN': {'is_set': True, 'last4': '5678'},
    }
    assert result['hyperpay_mada']['ACCESS_TOKEN'] == {'is_set': False, 'last4': None}
    assert 'token5678' not in str(result)
    assert 'entity1234' not in str(result)


@pytest.mark.parametrize('payload, error', [
    ('not a dict', 'The payload must be a JSON object.'),
    ({'other': 1}, "Unknown fields: ['other']."),
    ({'enabled': 'yes'}, 'enabled must be true or false.'),
    ({'hyperpay': 'x'}, 'hyperpay must be a JSON object.'),
    ({'hyperpay': {'OTHER': 'x'}}, "Unknown fields in hyperpay: ['OTHER']."),
    ({'hyperpay': {'ENTITY_ID': 5}}, 'hyperpay.ENTITY_ID must be a string or null.'),
    ({'hyperpay': {'API_URL': 'http://eu-prod.oppwa.com/'}}, 'hyperpay.API_URL must be an https URL'),
    ({'hyperpay_mada': {'API_URL': 'https://attacker.example.com/'}}, 'hyperpay_mada.API_URL must be an https URL'),
    ({'hyperpay': {'TEST_MODE': 'yes'}}, 'hyperpay.TEST_MODE must be one of'),
    ({'settings': {'valid_currency': 'USD'}}, 'settings.valid_currency must be SAR.'),
    ({'enabled': True}, 'Payments cannot be enabled until'),
    ({'enabled': True, 'settings': COMPLETE_SETTINGS}, 'Payments cannot be enabled until'),
])
def test_build_payment_configs_invalid(payload, error):
    """Verify that invalid payloads are refused"""
    with pytest.raises(FXCodedException) as exc_info:
        payments.build_payment_configs(payload, {})
    assert exc_info.value.code == FXExceptionCodes.INVALID_INPUT.value
    assert str(exc_info.value).startswith(error)


def test_build_payment_configs_refuses_incomplete_while_enabled():
    """Verify that clearing a required field of an enabled tenant is refused"""
    with pytest.raises(FXCodedException):
        payments.build_payment_configs({'hyperpay': {'ACCESS_TOKEN': None}}, _configured())


def test_build_payment_configs_enable_from_nothing():
    """Verify a full payload on a tenant without payments"""
    result = payments.build_payment_configs({
        'enabled': True,
        'settings': {**COMPLETE_SETTINGS, 'organization': '  Org  '},
        'hyperpay': COMPLETE_HYPERPAY,
    }, {'other': 1})
    assert result == {
        payments.PAYMENTS_ENABLED_KEY: True,
        payments.PAYMENTS_SETTINGS_KEY: COMPLETE_SETTINGS,
        payments.HYPERPAY_SETTINGS_KEY: COMPLETE_HYPERPAY,
    }


def test_build_payment_configs_keeps_omitted_and_clears_null():
    """Verify that omitted secrets are kept and null removes a field"""
    current = _configured(**{payments.HYPERPAY_MADA_SETTINGS_KEY: {'API_URL': 'https://eu-test.oppwa.com/'}})
    result = payments.build_payment_configs(
        {'hyperpay': {'TEST_MODE': 'INTERNAL'}, 'hyperpay_mada': {'API_URL': None}}, current,
    )
    assert result[payments.HYPERPAY_SETTINGS_KEY] == {**COMPLETE_HYPERPAY, 'TEST_MODE': 'INTERNAL'}
    assert result[payments.HYPERPAY_MADA_SETTINGS_KEY] == {}
    assert result[payments.PAYMENTS_ENABLED_KEY] is True
    assert current[payments.HYPERPAY_MADA_SETTINGS_KEY] == {'API_URL': 'https://eu-test.oppwa.com/'}


def test_build_payment_configs_disable_untouched_keys_left_out():
    """Verify that disabling a tenant without payments writes only the switch"""
    assert payments.build_payment_configs({'enabled': False}, {}) == {payments.PAYMENTS_ENABLED_KEY: False}


@pytest.mark.django_db
def test_update_tenant_payment_configs_not_found():
    """Verify the error for an unknown tenant"""
    with pytest.raises(FXCodedException) as exc_info:
        payments.update_tenant_payment_configs(9999, {'enabled': False}, None)
    assert exc_info.value.code == FXExceptionCodes.TENANT_NOT_FOUND.value


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.payments.invalidate_cache')
@patch('futurex_openedx_extensions.helpers.payments.log')
def test_update_tenant_payment_configs(mock_log, mock_invalidate, base_data):  # pylint: disable=unused-argument
    """Verify the write, the cache invalidation, and the audit line without values"""
    result = payments.update_tenant_payment_configs(
        1, {'enabled': True, 'settings': COMPLETE_SETTINGS, 'hyperpay': COMPLETE_HYPERPAY}, Mock(id=2),
    )
    stored = TenantConfig.objects.get(id=1).lms_configs
    assert stored == result
    assert stored['LMS_BASE'] == 's1.sample.com'
    assert stored[payments.HYPERPAY_SETTINGS_KEY] == COMPLETE_HYPERPAY
    mock_invalidate.assert_called_once_with('fx_config_tenant_lms_config_1')
    args = mock_log.info.call_args[0]
    assert args[1:] == (
        2, 1,
        [payments.HYPERPAY_SETTINGS_KEY, payments.PAYMENTS_ENABLED_KEY, payments.PAYMENTS_SETTINGS_KEY],
        True,
    )
    assert 'token5678' not in str(mock_log.info.call_args)
