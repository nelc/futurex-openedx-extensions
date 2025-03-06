"""Tests for tenants helpers."""
from unittest.mock import MagicMock, patch

import pytest
from common.djangoapps.third_party_auth.models import SAMLProviderConfig
from django.contrib.sites.models import Site
from django.core.cache import cache
from django.db.models import F
from django.test import override_settings
from eox_tenant.models import Route, TenantConfig

from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers import tenants
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.models import ConfigAccessControl


@pytest.fixture
def expected_exclusion():
    """Expected exclusion data."""
    return {
        4: [FXExceptionCodes.TENANT_HAS_NO_LMS_BASE.value],
        5: [FXExceptionCodes.TENANT_COURSE_ORG_FILTER_NOT_VALID.value],
        6: [FXExceptionCodes.TENANT_HAS_NO_SITE.value],
    }


@pytest.mark.django_db
def test_get_excluded_tenant_ids(
    base_data, expected_exclusion,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify get_excluded_tenant_ids function."""
    result = tenants.get_excluded_tenant_ids()
    assert result == expected_exclusion


@pytest.mark.django_db
def test_get_excluded_tenant_ids_more_than_one_tenant(
    base_data, expected_exclusion,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify get_excluded_tenant_ids function when there is more than one tenant."""
    Route.objects.create(config_id=1, domain='s1-new.sample.com')

    result = tenants.get_excluded_tenant_ids()
    expected_exclusion.update({1: [FXExceptionCodes.TENANT_HAS_MORE_THAN_ONE_SITE.value]})
    assert result == expected_exclusion


@pytest.mark.django_db
def test_get_excluded_tenant_ids_dashboard_disabled(
    base_data, expected_exclusion,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify get_excluded_tenant_ids function when the dashboard is disabled."""
    assert tenants.get_excluded_tenant_ids() == expected_exclusion
    tenant1 = TenantConfig.objects.get(id=1)

    tenant1.lms_configs['IS_FX_DASHBOARD_ENABLED'] = False
    tenant1.save()
    expected_exclusion.update({1: [FXExceptionCodes.TENANT_DASHBOARD_NOT_ENABLED.value]})
    assert tenants.get_excluded_tenant_ids() == expected_exclusion

    tenant1.lms_configs.pop('IS_FX_DASHBOARD_ENABLED')
    tenant1.save()
    expected_exclusion.pop(1)
    assert tenants.get_excluded_tenant_ids() == expected_exclusion


@pytest.mark.django_db
def test_get_excluded_tenant_ids_lms_base_mismatch(
    base_data, expected_exclusion,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify get_excluded_tenant_ids function when the LMS base is not the same as the related domain."""
    tenant1 = TenantConfig.objects.get(id=1)
    tenant1.lms_configs['LMS_BASE'] = 's1-different.sample.com'
    tenant1.save()

    result = tenants.get_excluded_tenant_ids()
    expected_exclusion.update({1: [FXExceptionCodes.TENANT_LMS_BASE_SITE_MISMATCH.value]})
    assert result == expected_exclusion


@pytest.mark.django_db
def test_get_all_tenants(base_data):  # pylint: disable=unused-argument
    """Verify get_all_tenants function."""
    result = tenants.get_all_tenants()
    assert TenantConfig.objects.count() == 8
    assert result.count() == 5
    assert result.exclude(id__in=[4, 5, 6]).count() == result.count()
    assert result.exclude(id__in=[4, 5, 6]).count() == TenantConfig.objects.exclude(id__in=[4, 5, 6]).count()


@pytest.mark.django_db
def test_get_all_tenant_ids(base_data):  # pylint: disable=unused-argument
    """Verify get_all_tenant_ids function."""
    result = tenants.get_all_tenant_ids()
    assert result == [1, 2, 3, 7, 8]


@pytest.mark.django_db
def test_get_all_course_org_filter_list(base_data):  # pylint: disable=unused-argument
    """Verify get_all_course_org_filter_list function."""
    result = tenants.get_all_course_org_filter_list()
    assert result == {
        1: ['org1', 'org2'],
        2: ['org3', 'org8'],
        3: ['org4', 'org5'],
        7: ['org3'],
        8: ['org8'],
    }


@pytest.mark.django_db
def test_get_all_course_org_filter_list_is_being_cached(cache_testing):  # pylint: disable=unused-argument
    """Verify that get_all_course_org_filter_list is being cached."""
    assert cache.get(cs.CACHE_NAME_ALL_COURSE_ORG_FILTER_LIST) is None
    result = tenants.get_all_course_org_filter_list()
    assert cache.get(cs.CACHE_NAME_ALL_COURSE_ORG_FILTER_LIST)['data'] == result
    cache.set(cs.CACHE_NAME_ALL_COURSE_ORG_FILTER_LIST, None)


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_ids, expected', [
    ([1, 2, 3, 7], {
        'course_org_filter_list': ['org1', 'org2', 'org3', 'org8', 'org4', 'org5'],
        'duplicates': {
            2: [7],
            7: [2],
        },
        'invalid': [],
    }),
    ([2, 3], {
        'course_org_filter_list': ['org3', 'org8', 'org4', 'org5'],
        'duplicates': {},
        'invalid': [],
    }),
    ([2, 3, 4], {
        'course_org_filter_list': ['org3', 'org8', 'org4', 'org5'],
        'duplicates': {},
        'invalid': [4],
    }),
    ([2, 3, 7, 8], {
        'course_org_filter_list': ['org3', 'org8', 'org4', 'org5'],
        'duplicates': {
            2: [7, 8],
            7: [2],
            8: [2],
        },
        'invalid': [],
    }),
    ([], {
        'course_org_filter_list': [],
        'duplicates': {},
        'invalid': [],
    }),
    (None, {
        'course_org_filter_list': [],
        'duplicates': {},
        'invalid': [],
    }),
])
def test_get_course_org_filter_list(base_data, tenant_ids, expected):  # pylint: disable=unused-argument
    """Verify get_course_org_filter_list function."""
    result = tenants.get_course_org_filter_list(tenant_ids, ignore_invalid_tenant_ids=True)
    assert result == expected
    if expected['invalid']:
        with pytest.raises(ValueError) as exc_info:
            tenants.get_course_org_filter_list(tenant_ids)
        assert str(exc_info.value) == f'Invalid tenant IDs: {expected["invalid"]}'


@pytest.mark.django_db
def test_get_all_tenants_info(base_data):  # pylint: disable=unused-argument
    """Verify get_all_tenants_info function."""
    result = tenants.get_all_tenants_info()
    assert result['tenant_ids'] == [1, 2, 3, 7, 8]
    assert result['sites'] == {
        1: 's1.sample.com',
        2: 's2.sample.com',
        3: 's3.sample.com',
        7: 's7.sample.com',
        8: 's8.sample.com',
    }


@pytest.mark.django_db
@pytest.mark.parametrize('config_key, info_key, test_value, expected_result', [
    ('LMS_BASE', 'lms_root_url', 'lms.example.com', 'https://lms.example.com'),
    ('LMS_ROOT_URL', 'lms_root_url', 'https://lms.example.com', 'https://lms.example.com'),
    ('PLATFORM_NAME', 'platform_name', 'Test Platform', 'Test Platform'),
    ('platform_name', 'platform_name', 'Test Platform', 'Test Platform'),
    ('logo_image_url', 'logo_image_url', 'https://img.example.com/dummy.jpg', 'https://img.example.com/dummy.jpg'),
])
@patch('futurex_openedx_extensions.helpers.tenants.get_excluded_tenant_ids', return_value=[])
def test_get_all_tenants_info_configs(
    base_data, config_key, info_key, test_value, expected_result
):  # pylint: disable=unused-argument
    """Verify get_all_tenants_info function returning the correct logo_url."""
    tenant_config = TenantConfig.objects.create()
    assert tenant_config.lms_configs.get(config_key) is None

    result = tenants.get_all_tenants_info()
    assert result['info'][tenant_config.id][info_key] == ''

    tenant_config.lms_configs[config_key] = test_value
    tenant_config.save()
    result = tenants.get_all_tenants_info()
    assert result['info'][tenant_config.id][info_key] == expected_result


@pytest.mark.django_db
@pytest.mark.parametrize('config_keys, data_prefix, call_index', [
    (['LMS_ROOT_URL', 'LMS_BASE'], 'https://', 0),
    (['PLATFORM_NAME', 'platform_name'], '', 1),
])
@patch(
    'futurex_openedx_extensions.helpers.tenants.get_excluded_tenant_ids',
    return_value=[1, 2, 3, 4, 5, 6, 7, 8]
)
@patch('futurex_openedx_extensions.helpers.tenants.get_first_not_empty_item')
@patch('futurex_openedx_extensions.helpers.tenants.fix_lms_base')
def test_get_all_tenants_info_config_priorities(
    mock_fix_lms_base, mock_get_first_not_empty_item, base_data, config_keys, data_prefix, call_index
):  # pylint: disable=unused-argument, too-many-arguments
    """Verify get_all_tenants_info is respecting the priority of the config keys."""
    assert not tenants.get_all_tenants_info()['tenant_ids']
    tenant_config = TenantConfig.objects.create()
    for config_key in config_keys:
        tenant_config.lms_configs[config_key] = f'{data_prefix}{config_key}_value'
    tenant_config.save()

    mock_fix_lms_base.side_effect = lambda x: x

    _ = tenants.get_all_tenants_info()
    assert mock_get_first_not_empty_item.call_args_list[call_index][0][0] == [
        f'{data_prefix}{config_key}_value' for config_key in config_keys
    ]


@pytest.mark.django_db
def test_get_all_tenants_info_is_being_cached(cache_testing):  # pylint: disable=unused-argument
    """Verify that get_all_tenants_info is being cached."""
    assert cache.get(cs.CACHE_NAME_ALL_TENANTS_INFO) is None
    result = tenants.get_all_tenants_info()
    assert cache.get(cs.CACHE_NAME_ALL_TENANTS_INFO)['data'] == result
    cache.set(cs.CACHE_NAME_ALL_TENANTS_INFO, None)


@pytest.mark.django_db
def test_get_sso_sites(base_data):  # pylint: disable=unused-argument
    """Verify that get_sso_sites works as expected"""
    assert not tenants.get_sso_sites(), 'bad test data'
    assert isinstance(tenants.get_sso_sites(), dict), 'bad test data'

    test_data = [
        ('testing_entity_id1', 'slug1'),
        ('testing_entity_id2', 'slug2'),
        ('other-entry-id', 'slug3'),
    ]
    site = Site.objects.get(domain='s1.sample.com')
    for entity_id, slug in test_data:
        SAMLProviderConfig.objects.create(site=site, entity_id=entity_id, slug=slug, enabled=True)
    assert tenants.get_sso_sites() == {
        's1.sample.com': [
            {'entity_id': 'testing_entity_id1', 'slug': 'slug1'},
            {'entity_id': 'testing_entity_id2', 'slug': 'slug2'},
        ]
    }

    SAMLProviderConfig.objects.create(site=site, entity_id=test_data[0][0], slug=test_data[0][1], enabled=False)
    assert tenants.get_sso_sites() == {
        's1.sample.com': [
            {'entity_id': 'testing_entity_id2', 'slug': 'slug2'},
        ]
    }


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_id, expected', [
    (1, 's1.sample.com'),
    (2, 's2.sample.com'),
    (3, 's3.sample.com'),
    (4, None),
    (5, None),
    (6, None),
    (7, 's7.sample.com'),
    (8, 's8.sample.com'),
])
def test_get_tenant_site(base_data, tenant_id, expected):  # pylint: disable=unused-argument
    """Verify get_tenant_site function."""
    assert expected == tenants.get_tenant_site(tenant_id)


@pytest.mark.django_db
@pytest.mark.parametrize('org, expected', [
    ('org1', [1]),
    ('org2', [1]),
    ('org3', [2, 7]),
    ('org4', [3]),
    ('org5', [3]),
    ('org8', [2, 8]),
])
def test_get_tenants_by_org(base_data, org, expected):  # pylint: disable=unused-argument
    """Verify get_tenants_by_org function."""
    assert len(expected) == len(tenants.get_tenants_by_org(org))
    assert set(expected) == set(tenants.get_tenants_by_org(org))


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_ids, expected', [
    ([1], ['s1.sample.com']),
    ([2, 3], ['s2.sample.com', 's3.sample.com']),
    ([2, 3, 4], ['s2.sample.com', 's3.sample.com']),
    ([2, 3, 7, 8], ['s2.sample.com', 's3.sample.com', 's7.sample.com', 's8.sample.com']),
])
def test_get_tenants_sites(base_data, tenant_ids, expected):  # pylint: disable=unused-argument
    """Verify get_tenants_sites function."""
    assert expected == tenants.get_tenants_sites(tenant_ids)


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_ids', [
    [],
    None,
    [99],
])
def test_get_tenants_sites_bad_tenants(base_data, tenant_ids):  # pylint: disable=unused-argument
    """Verify get_tenants_sites function."""
    result = tenants.get_tenants_sites(tenant_ids)
    assert result is not None and len(result) == 0


@pytest.mark.parametrize('lms_root_scheme, domain_name, expected_result', [
    ('http', 'example.com', 'http://example.com'),
    ('http', 'http://example.com', 'http://example.com'),
    ('http', 'https://example.com', 'https://example.com'),
    ('https', 'example.com', 'https://example.com'),
    ('https', 'http://example.com', 'http://example.com'),
    ('https', 'https://example.com', 'https://example.com'),
])
def test_fix_lms_base_scheme(lms_root_scheme, domain_name, expected_result):
    """Verify that fix_lms_base sets the correct scheme for the result."""
    with override_settings(LMS_ROOT_URL=f'{lms_root_scheme}://lms.example.com'):
        assert expected_result == tenants.fix_lms_base(domain_name)


@pytest.mark.parametrize('lms_root_port, domain_name, expected_result', [
    (None, 'example.com', 'https://example.com'),
    (None, 'example.com:8080', 'https://example.com:8080'),
    (3030, 'example.com', 'https://example.com:3030'),
    (3030, 'example.com:8080', 'https://example.com:8080'),
])
def test_fix_lms_base_port(lms_root_port, domain_name, expected_result):
    """Verify that fix_lms_base sets the correct port for the result."""
    port = f':{lms_root_port}' if lms_root_port else ''
    with override_settings(LMS_ROOT_URL=f'https://lms.example.com{port}'):
        assert expected_result == tenants.fix_lms_base(domain_name)


@pytest.mark.parametrize('domain_name', [
    None, '',
])
def test_fix_lms_base_empty_domain_name(domain_name):
    """Verify that fix_lms_base sets the correct port for the result."""
    assert tenants.fix_lms_base(domain_name) == ''


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.tenants.TenantConfig.objects.get')
def test_generate_tenant_config_success(mock_get):
    """Test generate_tenant_config replaces placeholders correctly when TenantConfig exists."""
    mock_default_config = MagicMock()
    mock_default_config.lms_configs = {
        'EDNX_USE_SIGNAL': True,
        'EOX_THEMING_DEFAULT_THEME_NAME': '{{sub_domain}}-edx-theme',
        'LMS_BASE': '{{sub_domain}}.local.overhang.io',
        'SITE_NAME': 'http://{{sub_domain}}.local.overhang.io:8000/',
        'course_org_filter': ['{{sub_domain}}_org'],
        'PLATFORM_NAME': '{{platform_name}}'
    }
    mock_get.return_value = mock_default_config
    result = tenants.generate_tenant_config('testplatform', 'Test Platform Name')
    assert result['EOX_THEMING_DEFAULT_THEME_NAME'] == 'testplatform-edx-theme'
    assert result['SITE_NAME'] == 'http://testplatform.local.overhang.io:8000/'
    assert result['course_org_filter'] == ['testplatform_org']
    assert result['PLATFORM_NAME'] == 'Test Platform Name'


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.tenants.TenantConfig.objects.get')
def test_generate_tenant_config_tenant_not_found(mock_get):
    """Test generate_tenant_config raises an exception when the default TenantConfig is missing."""
    mock_get.side_effect = TenantConfig.DoesNotExist
    with pytest.raises(FXCodedException) as excinfo:
        tenants.generate_tenant_config('testplatform', 'Test Platform Name')
    assert excinfo.value.code == FXExceptionCodes.TENANT_NOT_FOUND.value
    assert str(excinfo.value) == 'Default TenantConfig not found! default site: (default.example.com)'


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.tenants.generate_tenant_config')
@patch('futurex_openedx_extensions.helpers.tenants.TenantConfig.objects.create')
@patch('futurex_openedx_extensions.helpers.tenants.Route.objects.create')
def test_create_new_tenant_config_success(mock_route_create, mock_tenant_create, mock_generate_config):
    """Test create_new_tenant_config successfully creates a tenant and route."""
    mock_generate_config.return_value = {
        'EDNX_USE_SIGNAL': True,
        'EOX_THEMING_DEFAULT_THEME_NAME': 'testplatform-edx-theme',
        'SITE_NAME': 'http://testplatform.local.overhang.io:8000/',
        'LMS_BASE': 'testplatform.local.overhang.io',
        'course_org_filter': ['testplatform_org'],
    }
    mock_tenant = MagicMock()
    mock_tenant_create.return_value = mock_tenant
    result = tenants.create_new_tenant_config('testplatform', 'Test Platform Name')
    mock_generate_config.assert_called_once_with('testplatform', 'Test Platform Name')
    mock_tenant_create.assert_called_once_with(
        external_key='testplatform', lms_configs=mock_generate_config.return_value
    )
    mock_route_create.assert_called_once_with(domain='testplatform.local.overhang.io', config=mock_tenant)
    assert result == mock_tenant


@pytest.mark.django_db
def test_create_new_tenant_for_existing_route_and_tenant():
    """Test create_new_tenant_config raise exception if route already exist for given domain"""
    tenant_config = TenantConfig.objects.create(external_key='testplatform', lms_configs={'dummy': 'some dummy data'})
    Route.objects.create(domain='testplatform.local.overhang.io', config=tenant_config)

    with pytest.raises(FXCodedException) as excinfo:
        tenants.create_new_tenant_config('testplatform', 'Test Platform Name')
    assert excinfo.value.code == FXExceptionCodes.ROUTE_ALREADY_EXIST.value
    assert str(excinfo.value) == 'Route already exists with site domain: (testplatform.local.overhang.io).'


@pytest.mark.parametrize(
    'config, path, published_only, draft_only, expected, usecase',
    [
        (
            {'LMS_BASE': 'example.com'},
            'LMS_BASE', False, False, 'example.com',
            'Retrieve from published config (default behavior)'
        ),
        (
            {'theme': {'colors': {'primary': 'blue'}}},
            'theme.colors.primary', False, False, 'blue',
            'Retrieve from nested published config'
        ),
        (
            {'LMS_BASE': 'example.com', 'config_draft': {'LMS_BASE': 'draft.example.com'}},
            'LMS_BASE', False, False, 'draft.example.com',
            'Retrieve from draft config when both published and draft exist'
        ),
        (
            {'LMS_BASE': 'example.com', 'config_draft': {'LMS_BASE': 'draft.example.com'}},
            'LMS_BASE', True, False, 'example.com',
            'Retrieve from published config when published_only=True'
        ),
        (
            {'LMS_BASE': 'example.com', 'config_draft': {'LMS_BASE': 'draft.example.com'}},
            'LMS_BASE', False, True, 'draft.example.com',
            'Retrieve from draft config when draft_only=True'
        ),
        (
            {'config_draft': {'LMS_BASE': 'draft.example.com'}},
            'UNKNOWN_KEY', False, False, None,
            'Key missing in both draft and published config'
        ),
        (
            {'LMS_BASE': 'example.com', 'config_draft': {}},
            'LMS_BASE', False, False, 'example.com',
            'Key missing in draft but present in published (fallback works)'
        ),
        (
            {'config_draft': {'LMS_BASE': 'draft.example.com'}},
            'LMS_BASE', True, False, None,
            'Key exists only in draft and published_only=True is set'
        ),
        (
            {'LMS_BASE': 'example.com'},
            'LMS_BASE', False, True, None,
            'Key exists only in published and draft_only=True is set'
        ),
        (
            None,
            'LMS_BASE', False, False, None,
            'Config is None, should return None'
        ),
        (
            {},
            'LMS_BASE', False, False, None,
            'Config is an empty dictionary, should return None'
        ),
    ]
)
def test_get_tenant_config_value(
    config, path, published_only, draft_only, expected, usecase
):  # pylint: disable=too-many-arguments
    """Test get_tenant_config_value"""
    assert tenants.get_tenant_config_value(
        config, path, published_only, draft_only
    ) == expected, f'Failed usecase: {usecase}'


@pytest.mark.django_db
@pytest.mark.parametrize(
    'usecase, config, keys, published_only, expected_values, expected_bad_keys',
    [
        (
            'Draft value should be preffered when published_only is False',
            {
                'platform_name': 'published_value',
                'theme_v2': {'pages': ['published_page']},
                'config_draft': {'platform_name': 'draft_value'},
            },
            ['platform_name', 'pages', 'not-exist'],
            False,
            {
                'platform_name': 'draft_value',
                'pages': ['published_page'],
            },
            ['not-exist'],
        ),
        (
            'Only published values should be retrieved even if it is empty or None, if published_only is True',
            {
                'platform_name': '',
                'theme_v2': {'pages': ['published_page'], 'links': {'facebook': None}},
                'config_draft': {'platform_name': 'draft_value'},
            },
            ['platform_name', 'pages', 'not-exist', 'facebook_link'],
            True,
            {
                'platform_name': '',
                'pages': ['published_page'],
                'facebook_link': None
            },
            ['not-exist'],
        ),
        (
            'Should return published values when draft does not exist',
            {
                'platform_name': 'published_value',
                'theme_v2': {'pages': ['published_page']},
                'config_draft': {}
            },
            ['platform_name', 'pages'],
            False,
            {
                'platform_name': 'published_value',
                'pages': ['published_page'],
            },
            [],
        ),
        (
            'Duplicate keys should be processed only once',
            {
                'platform_name': 'published_value',
                'theme_v2': {'pages': ['published_page']},
            },
            ['platform_name', 'platform_name', 'pages', 'not-exist', 'not-exist'],
            False,
            {
                'platform_name': 'published_value',
                'pages': ['published_page'],
            },
            ['not-exist'],
        ),
    ],
)
def test_get_tenant_config(
    usecase, config, keys, published_only, expected_values, expected_bad_keys
):  # pylint: disable=too-many-arguments
    """Test the get_tenant_config function under different scenarios."""
    ConfigAccessControl.objects.create(key_name='facebook_link', path='theme_v2.links.facebook', key_type='string')
    ConfigAccessControl.objects.create(key_name='pages', path='theme_v2.pages', key_type='list')
    ConfigAccessControl.objects.create(key_name='platform_name', path='platform_name', key_type='string')
    tenant = TenantConfig.objects.get(id=1)
    tenant.lms_configs = config
    tenant.save()

    result = tenants.get_tenant_config(1, keys, published_only)
    assert result['values'] == expected_values, \
        f'FAILED: {usecase} - Expected {expected_values}, got {result["values"]}'

    assert result['bad_keys'] == expected_bad_keys, \
        f'FAILED: {usecase} - Expected {expected_bad_keys}, got {result["bad_keys"]}'


@pytest.mark.django_db
def test_get_tenant_config_for_non_exist_tenant():
    """Test the get_tenant_config for non exist tenant_id."""
    not_exist_tenant_id = 100000
    with pytest.raises(FXCodedException) as exc_info:
        tenants.get_tenant_config(not_exist_tenant_id, ['some_key'])
    assert str(exc_info.value) == 'Unable to find tenant with id: (100000)'


@pytest.mark.django_db
def test_get_draft_tenant_config(base_data):  # pylint: disable=unused-argument
    """Test get_draft_tenant_config"""
    ConfigAccessControl.objects.create(key_name='facebook_link', path='theme_v2.links.facebook')
    assert tenants.get_draft_tenant_config(1) == {
        'facebook_link': {
            'published_value': 'facebook.com',
            'draft_value': 'draft.facebook.com'
        }
    }
    with pytest.raises(FXCodedException) as exc_info:
        tenants.get_draft_tenant_config(10000)
    assert str(exc_info.value) == 'Unable to find tenant with id: 10000'


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.tenants.TenantConfig.objects.filter')
@patch('futurex_openedx_extensions.helpers.tenants.annotate_tenant_config_queryset')
@patch('futurex_openedx_extensions.helpers.tenants.apply_json_merge_patch')
def test_update_draft_tenant_config(mock_apply_json_merge_patch, mock_annotate_queryset, mock_filter):
    """Test the update_draft_tenant_config function for both successful and unsuccessful updates."""
    tenant_id = 1
    key_path = 'some_key_path'
    current_value = 'current_value'
    new_value = 'new_value'
    reset = False

    mock_filter.return_value.exists.return_value = True
    mock_filter.return_value = TenantConfig.objects.filter(id=tenant_id)
    mock_annotate_queryset.return_value = mock_filter.return_value
    mock_apply_json_merge_patch.return_value = MagicMock()
    tenants.update_draft_tenant_config(1, key_path, current_value, new_value, reset)
    mock_annotate_queryset.assert_called_with(mock_filter.return_value, key_path)
    mock_apply_json_merge_patch.assert_called_once_with(F('lms_configs'), key_path, new_value, reset)
    mock_filter.return_value.filter.return_value.update.assert_called_once()

    mock_filter.return_value.filter.return_value.update.return_value = 0
    with pytest.raises(FXCodedException) as exc_info:
        tenants.update_draft_tenant_config(tenant_id, key_path, current_value, new_value, reset)
    assert str(exc_info.value) == (
        'Failed to update config for tenant 1. '
        'Key path may not exist or current value mismatch.'
    )


@pytest.mark.django_db
def test_update_draft_tenant_config_for_non_exist_tenant():
    """Test update_draft_tenant_config for tenant that does not exist """
    not_exist_tenant_id = 100000
    key_access_info = ConfigAccessControl.objects.create(key_name='footer_link', path='theme_v2.footer.link')
    with pytest.raises(FXCodedException) as exc_info:
        tenants.update_draft_tenant_config(not_exist_tenant_id, key_access_info.path, 'some value', 'new value')
    assert str(exc_info.value) == 'Tenant with ID 100000 not found.'


@pytest.mark.django_db
def test_delete_draft_tenant_config():
    """Test delete_draft_tenant_config"""
    with pytest.raises(FXCodedException) as exc_info:
        tenants.delete_draft_tenant_config(10000)
    assert exc_info.value.code == FXExceptionCodes.TENANT_NOT_FOUND.value
    assert str(exc_info.value) == 'Unable to find tenant with id: 10000'

    tenant = TenantConfig.objects.get(id=1)
    assert tenant.lms_configs['config_draft'] != {}
    tenants.delete_draft_tenant_config(1)
    tenant.refresh_from_db()
    assert tenant.lms_configs['config_draft'] == {}
