"""Tests for the registration fields helpers"""
from unittest.mock import Mock, patch

import pytest
from eox_tenant.models import TenantConfig

from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers import registration_fields as rf
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes

LMS_CONFIGS = {
    'extended_profile_fields': ['region', 'employer', 'old_field', 'secret', 5],
    'REGISTRATION_EXTRA_FIELDS': {
        'region': 'required', 'employer': 'optional', 'old_field': 'required', 'secret': 'hidden',
        'national_id': 'hidden', 'arabic_first_name': 'required',
    },
    'EXTRA_FIELD_OPTIONS': {'region': ['Riyadh', 'Makkah'], 'old_field': ['a'], 'sector': ['x']},
    'extended_profile_fields_translations': {
        'ar': {'region': 'المنطقة', 'employer': 'جهة العمل', 'old_field': 'قديم', 'national_id': 'الهوية'},
        'en': {'region': 'Region', 'old_field': 'Old'},
        'fr': {'region': 'Région', 'old_field': 'Ancien'},
        'bad': 'not a dict',
    },
}


def _field(name='region', **kwargs):
    """Helper to build a payload field"""
    result = {'name': name, 'label': {'ar': 'المنطقة', 'en': 'Region'}, 'required': True, 'options': None}
    result.update(kwargs)
    return result


def test_get_registration_fields():
    """Verify the fields are built from the four keys, in the stored order"""
    assert rf.get_registration_fields(LMS_CONFIGS) == [
        {
            'name': 'region', 'label': {'ar': 'المنطقة', 'en': 'Region'}, 'required': True, 'hidden': False,
            'options': ['Riyadh', 'Makkah'],
        },
        {
            'name': 'employer', 'label': {'ar': 'جهة العمل', 'en': None}, 'required': False, 'hidden': False,
            'options': None,
        },
        {
            'name': 'old_field', 'label': {'ar': 'قديم', 'en': 'Old'}, 'required': True, 'hidden': False,
            'options': ['a'],
        },
        {
            'name': 'secret', 'label': {'ar': None, 'en': None}, 'required': False, 'hidden': True,
            'options': None,
        },
    ]


@pytest.mark.parametrize('lms_configs', [
    {},
    {'extended_profile_fields': 'region'},
    {'extended_profile_fields': []},
])
def test_get_registration_fields_empty(lms_configs):
    """Verify that a tenant without custom fields has no fields"""
    assert not rf.get_registration_fields(lms_configs)


def test_get_registration_fields_bad_shapes():
    """Verify that bad shapes of the other keys are read as missing"""
    assert rf.get_registration_fields({
        'extended_profile_fields': ['region'],
        'REGISTRATION_EXTRA_FIELDS': ['region'],
        'EXTRA_FIELD_OPTIONS': {'region': 'Riyadh'},
        'extended_profile_fields_translations': {'ar': ['x']},
    }) == [{
        'name': 'region', 'label': {'ar': None, 'en': None}, 'required': False, 'hidden': True, 'options': None,
    }]


@pytest.mark.parametrize('payload, expected_reason', [
    (['x'], 'The payload must be a JSON object.'),
    ({'fields': [], 'other': 1}, "Unknown keys: ['other']."),
    ({}, 'fields is required and must be a list.'),
    ({'fields': {}}, 'fields is required and must be a list.'),
    ({'fields': [_field(f'field_{i}') for i in range(21)]}, 'fields cannot have more than 20 fields.'),
    ({'fields': ['x']}, 'fields[0] must be a JSON object.'),
    ({'fields': [_field(extra=1)]}, "Unknown keys in fields[0]: ['extra']."),
    ({'fields': [_field(name=None)]}, 'fields[0].name must be snake_case'),
    ({'fields': [_field(name='Region')]}, 'fields[0].name must be snake_case'),
    ({'fields': [_field(name='r')]}, 'fields[0].name must be snake_case'),
    ({'fields': [_field(name='1region')]}, 'fields[0].name must be snake_case'),
    ({'fields': [_field(name='a' * 65)]}, 'fields[0].name must be snake_case'),
    ({'fields': [_field(name='region-x')]}, 'fields[0].name must be snake_case'),
    ({'fields': [_field(name='national_id')]}, 'fields[0].name (national_id) is a stock registration field'),
    ({'fields': [_field(), _field()]}, 'fields[1].name (region) is used by more than one field.'),
    ({'fields': [_field(required=None)]}, 'fields[0].required must be true or false.'),
    ({'fields': [_field(required='yes')]}, 'fields[0].required must be true or false.'),
    ({'fields': [_field(hidden=1)]}, 'fields[0].hidden must be true or false.'),
    ({'fields': [_field(hidden=True)]}, 'fields[0] cannot be both required and hidden.'),
    ({'fields': [_field(label=None)]}, 'fields[0].label must be an object with exactly the keys'),
    ({'fields': [_field(label={'ar': 'x'})]}, 'fields[0].label must be an object with exactly the keys'),
    ({'fields': [_field(label={'ar': 'x', 'en': 'y', 'fr': 'z'})]}, 'fields[0].label must be an object'),
    ({'fields': [_field(label={'ar': ' ', 'en': 'y'})]}, 'fields[0].label.ar must be a non-empty string.'),
    ({'fields': [_field(label={'ar': 'x', 'en': 5})]}, 'fields[0].label.en must be a non-empty string.'),
    ({'fields': [_field(options=[])]}, 'fields[0].options must be null or a non-empty list of strings.'),
    ({'fields': [_field(options='a')]}, 'fields[0].options must be null or a non-empty list of strings.'),
    ({'fields': [_field(options=[str(i) for i in range(301)])]}, 'fields[0].options cannot have more than 300'),
    ({'fields': [_field(options=['a', ''])]}, 'fields[0].options must contain non-empty strings only.'),
    ({'fields': [_field(options=['a', 1])]}, 'fields[0].options must contain non-empty strings only.'),
    ({'fields': [_field(options=['Riyadh', ' riyadh '])]}, 'fields[0].options has a duplicate value: (riyadh)'),
])
def test_validate_registration_fields_payload_invalid(payload, expected_reason):
    """Verify the payload validation"""
    with pytest.raises(FXCodedException) as exc_info:
        rf.validate_registration_fields_payload(payload)
    assert exc_info.value.code == FXExceptionCodes.INVALID_INPUT.value
    assert str(exc_info.value).startswith(expected_reason)


def test_validate_registration_fields_payload_valid():
    """Verify the cleaned fields of a valid payload"""
    assert rf.validate_registration_fields_payload({'tenant_id': 99, 'fields': [
        _field(label={'ar': ' المنطقة ', 'en': 'Region '}, options=[' Riyadh', 'Makkah']),
        _field('employer', required=False),
        _field('secret', required=False, hidden=True),
        _field('a' * 64),
    ]}) == [
        {'name': 'region', 'label': {'ar': 'المنطقة', 'en': 'Region'}, 'visibility': 'required',
         'options': ['Riyadh', 'Makkah']},
        {'name': 'employer', 'label': {'ar': 'المنطقة', 'en': 'Region'}, 'visibility': 'optional', 'options': None},
        {'name': 'secret', 'label': {'ar': 'المنطقة', 'en': 'Region'}, 'visibility': 'hidden', 'options': None},
        {'name': 'a' * 64, 'label': {'ar': 'المنطقة', 'en': 'Region'}, 'visibility': 'required', 'options': None},
    ]


def test_build_registration_fields_configs():
    """Verify the custom entries are replaced and every other entry is preserved"""
    fields = rf.validate_registration_fields_payload({'fields': [
        _field('employer', required=False, options=['NELC'], label={'ar': 'جهة', 'en': 'Employer'}),
        _field('region', options=None),
        _field('new_one', required=False, hidden=True),
    ]})
    original = {**LMS_CONFIGS, 'extended_profile_fields': [*LMS_CONFIGS['extended_profile_fields'], 'national_id']}
    result = rf.build_registration_fields_configs(fields, original)

    assert result == {
        'extended_profile_fields': ['employer', 'region', 'new_one'],
        'REGISTRATION_EXTRA_FIELDS': {
            'region': 'required', 'employer': 'optional', 'new_one': 'hidden',
            'national_id': 'hidden', 'arabic_first_name': 'required',
        },
        'EXTRA_FIELD_OPTIONS': {'employer': ['NELC'], 'sector': ['x']},
        'extended_profile_fields_translations': {
            'ar': {'region': 'المنطقة', 'employer': 'جهة', 'new_one': 'المنطقة', 'national_id': 'الهوية'},
            'en': {'region': 'Region', 'employer': 'Employer', 'new_one': 'Region'},
            'fr': {'region': 'Région'},
            'bad': 'not a dict',
        },
    }
    assert original['EXTRA_FIELD_OPTIONS']['old_field'] == ['a'], 'the input must not be changed'


def test_build_registration_fields_configs_new_tenant():
    """Verify that only the needed keys are created on a tenant without custom fields"""
    fields = rf.validate_registration_fields_payload({'fields': [_field()]})
    assert rf.build_registration_fields_configs(fields, {'extended_profile_fields_translations': {'ar': 'x'}}) == {
        'extended_profile_fields': ['region'],
        'REGISTRATION_EXTRA_FIELDS': {'region': 'required'},
        'extended_profile_fields_translations': {'ar': {'region': 'المنطقة'}, 'en': {'region': 'Region'}},
    }
    assert not rf.build_registration_fields_configs([], {})


def test_build_registration_fields_configs_remove_all():
    """Verify that an empty list removes the custom fields and keeps the existing keys"""
    assert rf.build_registration_fields_configs([], LMS_CONFIGS) == {
        'extended_profile_fields': [],
        'REGISTRATION_EXTRA_FIELDS': {'national_id': 'hidden', 'arabic_first_name': 'required'},
        'EXTRA_FIELD_OPTIONS': {'sector': ['x']},
        'extended_profile_fields_translations': {
            'ar': {'national_id': 'الهوية'}, 'en': {}, 'fr': {}, 'bad': 'not a dict',
        },
    }


@pytest.mark.django_db
def test_get_tenant_lms_configs(base_data):  # pylint: disable=unused-argument
    """Verify reading the lms_configs of a tenant"""
    assert rf.get_tenant_lms_configs(1)['LMS_BASE'] == 's1.sample.com'
    with pytest.raises(FXCodedException) as exc_info:
        rf.get_tenant_lms_configs(9999)
    assert exc_info.value.code == FXExceptionCodes.TENANT_NOT_FOUND.value


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.registration_fields.invalidate_cache')
def test_update_tenant_registration_fields(mock_invalidate, base_data):  # pylint: disable=unused-argument
    """Verify the four keys are saved together and the caches are cleared"""
    tenant = TenantConfig.objects.get(id=1)
    tenant.lms_configs.update(LMS_CONFIGS)
    tenant.save()

    result = rf.update_tenant_registration_fields(1, {'fields': [_field()]}, Mock(id=2))

    saved = TenantConfig.objects.get(id=1).lms_configs
    assert saved == result
    assert saved['LMS_BASE'] == 's1.sample.com'
    assert saved['extended_profile_fields'] == ['region']
    assert saved['REGISTRATION_EXTRA_FIELDS'] == {
        'region': 'required', 'national_id': 'hidden', 'arabic_first_name': 'required',
    }
    assert saved['EXTRA_FIELD_OPTIONS'] == {'sector': ['x']}
    assert mock_invalidate.call_count == 2
    mock_invalidate.assert_any_call(f'{cs.CACHE_NAME_TENANT_READABLE_LMS_CONFIG}_1')
    mock_invalidate.assert_any_call(cs.CACHE_NAME_ALL_EXTENDED_PROFILE_FIELDS)


@pytest.mark.django_db
def test_update_tenant_registration_fields_errors(base_data):  # pylint: disable=unused-argument
    """Verify that nothing is written on an invalid payload or an unknown tenant"""
    before = TenantConfig.objects.get(id=1).lms_configs
    with pytest.raises(FXCodedException) as exc_info:
        rf.update_tenant_registration_fields(1, {'fields': [_field(name='email')]}, None)
    assert exc_info.value.code == FXExceptionCodes.INVALID_INPUT.value
    assert TenantConfig.objects.get(id=1).lms_configs == before

    with pytest.raises(FXCodedException) as exc_info:
        rf.update_tenant_registration_fields(9999, {'fields': []}, None)
    assert exc_info.value.code == FXExceptionCodes.TENANT_NOT_FOUND.value
