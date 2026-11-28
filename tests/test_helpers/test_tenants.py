"""Tests for tenants helpers."""
# pylint: disable=too-many-lines
import copy
from collections import OrderedDict
from unittest.mock import ANY, MagicMock, Mock, patch

import pytest
from common.djangoapps.third_party_auth.models import SAMLProviderConfig
from deepdiff import DeepDiff
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.cache import cache
from django.test import override_settings
from eox_tenant.models import Route, TenantConfig

from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers import tenants
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.models import ConfigAccessControl, DraftConfig, TenantAsset


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
def test_get_excluded_tenant_ids_port_number(
    base_data, expected_exclusion,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify get_excluded_tenant_ids function works correctly when the site-domain has a port number."""
    for tenant_config in TenantConfig.objects.all():
        lms_base = tenant_config.lms_configs.get('LMS_BASE')
        if lms_base:
            tenant_config.lms_configs['LMS_BASE'] = f'{lms_base}:1234'
            tenant_config.save()

    assert tenants.get_excluded_tenant_ids() == expected_exclusion


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
    # ('LMS_BASE', 'lms_root_url', 'lms.example.com', 'https://lms.example.com'),
    ('LMS_ROOT_URL', 'lms_root_url', 'https://lms.example.com', 'https://lms.example.com'),
    ('PLATFORM_NAME', 'platform_name', 'Test Platform', 'Test Platform'),
    ('platform_name', 'platform_name', 'Test Platform', 'Test Platform'),
    ('logo_image_url', 'logo_image_url', 'https://img.example.com/dummy.jpg', 'https://img.example.com/dummy.jpg'),
])
@patch('futurex_openedx_extensions.helpers.tenants.get_excluded_tenant_ids', return_value=[4])
def test_get_all_tenants_info_configs(
    base_data, config_key, info_key, test_value, expected_result
):  # pylint: disable=unused-argument
    """Verify get_all_tenants_info function returning the correct logo_url."""
    tenant_config = TenantConfig.objects.create()
    tenant_config.lms_configs['LMS_BASE'] = 'lmsX.example.com'
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
    tenant_config.lms_configs['LMS_BASE'] = 'lmsX.example.com'
    tenant_config.save()
    for config_key in config_keys:
        tenant_config.lms_configs[config_key] = f'{data_prefix}{config_key}_value'
    tenant_config.save()

    mock_fix_lms_base.side_effect = lambda x: x

    _ = tenants.get_all_tenants_info()
    assert mock_get_first_not_empty_item.call_args_list[call_index][0][0] == [
        f'{data_prefix}{config_key}_value' for config_key in config_keys
    ]


@pytest.mark.django_db
def test_get_all_tenants_info_template_tenant_not_found(base_data, caplog):  # pylint: disable=unused-argument
    """Verify that get_all_tenants_info will log an error if the template tenant is not found."""
    assert settings.FX_TEMPLATE_TENANT_SITE, 'FX_TEMPLATE_TENANT_SITE setting is not set'
    assert TenantConfig.objects.filter(external_key=settings.FX_TEMPLATE_TENANT_SITE).count() == 0
    result = tenants.get_all_tenants_info()
    assert f'CONFIGURATION ERROR: Template tenant not found! ({settings.FX_TEMPLATE_TENANT_SITE})' in caplog.text
    assert isinstance(result['template_tenant'], dict)
    assert result['template_tenant'] == {
        'tenant_id': None,
        'tenant_site': None,
        'assets': None,
    }


@pytest.mark.django_db
def test_get_all_tenants_info_template_tenant(base_data, template_tenant):  # pylint: disable=unused-argument
    """Verify that get_all_tenants_info will return the template tenant ID correctly."""
    assert template_tenant.id != 1, 'bad test data'

    assets = []
    for tenant_id in (1, template_tenant.id):
        assets.append(TenantAsset.objects.create(
            slug=f'_template_asset_{tenant_id}',
            tenant_id=tenant_id,
            file=f'http://example.com/template_asset_{tenant_id}.png',
            updated_by_id=1,
        ))

    result = tenants.get_all_tenants_info()
    assert template_tenant.id not in result['tenant_ids'], 'Template tenant should not be in tenant_ids'
    assert result['template_tenant'] == {
        'tenant_id': template_tenant.id,
        'tenant_site': template_tenant.external_key,
        'assets': {
            f'_template_asset_{template_tenant.id}': assets[1].file.url,
        },
    }
    assert template_tenant.external_key == settings.FX_TEMPLATE_TENANT_SITE


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
@patch('futurex_openedx_extensions.helpers.tenants.Site.objects.create')
def test_create_new_tenant_config_success(
    mock_site_create, mock_route_create, mock_tenant_create, mock_generate_config
):
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
    mock_site_create.assert_called_once_with(
        domain='testplatform.local.overhang.io', name='testplatform.local.overhang.io'
    )
    assert result == mock_tenant


@pytest.mark.django_db
@pytest.mark.parametrize(
    'test_usecase, expected_error_value',
    [
        ('Site', FXExceptionCodes.SITE_ALREADY_EXIST.value),
        ('Route', FXExceptionCodes.ROUTE_ALREADY_EXIST.value),
    ]
)
def test_create_new_tenant_for_existing_route_and_tenant(test_usecase, expected_error_value):
    """Test create_new_tenant_config raises exception if route/site already exists for the given domain."""
    tenant_config = TenantConfig.objects.create(
        external_key='testplatform',
        lms_configs={'dummy': 'some dummy data'}
    )

    domain = 'testplatform.local.overhang.io'

    if test_usecase == 'Route':
        Route.objects.create(domain=domain, config=tenant_config)
    if test_usecase == 'Site':
        Site.objects.create(domain=domain, name=domain)

    with pytest.raises(FXCodedException) as excinfo:
        tenants.create_new_tenant_config('testplatform', 'Test Platform Name')

    assert excinfo.value.code == expected_error_value
    assert str(excinfo.value) == f'{test_usecase} already exists with domain: ({domain}).'


@pytest.mark.django_db
@pytest.mark.parametrize(
    'usecase, config, keys, published_only, expected_values, expected_bad_keys',
    [
        (
            'Draft value should be preferred when published_only is False',
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
    base_data, usecase, config, keys, published_only, expected_values, expected_bad_keys,
):  # pylint: disable=too-many-arguments, unused-argument
    """Test the get_tenant_config function under different scenarios."""
    draft_configs = config.get('config_draft', {})
    assert DraftConfig.objects.count() == 0, 'bad test data, DraftConfig should be empty before the test'
    for key, value in draft_configs.items():
        DraftConfig.objects.create(
            tenant_id=1, config_path=key, config_value=value,
            created_by_id=1, updated_by_id=1,
        )

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
    DraftConfig.objects.create(
        tenant_id=1, config_path='theme_v2.links.facebook', config_value='draft.facebook.com',
        created_by_id=1, updated_by_id=1,
    )
    assert tenants.get_draft_tenant_config(tenant_id=1) == {
        'facebook_link': {
            'published_value': 'facebook.com',
            'draft_value': 'draft.facebook.com'
        }
    }


@pytest.mark.django_db
def test_update_draft_config_success(base_data, support_user):  # pylint: disable=unused-argument
    """Verify update_draft_tenant_config updates value when revision_id matches"""
    draft = DraftConfig.objects.create(
        tenant_id=1,
        config_path='theme_v2.header.logo',
        config_value={'log_url': '/old-logo.png', 'width': 100, 'height': 50},
        revision_id=111,
        created_by=support_user,
        updated_by=support_user,
    )

    tenants.update_draft_tenant_config(
        tenant_id=1,
        config_path='theme_v2.header.logo',
        current_revision_id=111,
        new_value='/new-logo.png',
        user=support_user,
    )

    draft.refresh_from_db()
    assert draft.get_config_value()['config_value'] == '/new-logo.png'


@pytest.mark.django_db
def test_update_draft_config_reset_to_none(base_data, support_user):  # pylint: disable=unused-argument
    """Verify reset=True sets config_value to None"""
    draft = DraftConfig.objects.create(
        tenant_id=1,
        config_path='theme_v2.footer.color',
        config_value='blue',
        revision_id=222,
        created_by=support_user,
        updated_by=support_user,
    )

    tenants.update_draft_tenant_config(
        tenant_id=1,
        config_path='theme_v2.footer.color',
        current_revision_id=222,
        new_value='should-be-cleared',
        user=support_user,
        reset=True,
    )

    assert DraftConfig.objects.filter(pk=draft.pk).count() == 0


@pytest.mark.django_db
def test_update_draft_config_creates_new_if_not_exists(base_data, support_user):  # pylint: disable=unused-argument
    """Verify a new DraftConfig is created if not previously existing"""
    assert not DraftConfig.objects.filter(tenant_id=1, config_path='theme_v2.footer.new_field').exists()

    tenants.update_draft_tenant_config(
        tenant_id=1,
        config_path='theme_v2.footer.new_field',
        current_revision_id=0,
        new_value='new-data',
        user=support_user,
    )

    draft = DraftConfig.objects.get(tenant_id=1, config_path='theme_v2.footer.new_field')
    assert draft.get_config_value()['config_value'] == 'new-data'


@pytest.mark.django_db
def test_delete_draft_tenant_config():
    """Test delete_draft_tenant_config"""
    DraftConfig.objects.create(
        tenant_id=1, config_path='theme_v2.links.facebook', config_value='draft.facebook.com',
        created_by_id=1, updated_by_id=1,
    )
    DraftConfig.objects.create(
        tenant_id=2, config_path='theme_v2.links.facebook', config_value='draft.facebook.com',
        created_by_id=1, updated_by_id=1,
    )
    assert DraftConfig.objects.count() == 2
    tenants.delete_draft_tenant_config(tenant_id=1)
    assert DraftConfig.objects.filter(tenant_id=1).count() == 0
    assert DraftConfig.objects.exclude(tenant_id=1).count() == 1


@pytest.mark.django_db
def test_publish_tenant_config_calls_loads_into_correctly(base_data):  # pylint: disable=unused-argument
    """Verify publish_tenant_config calls DraftConfig.loads_into with correct args"""
    tenant = TenantConfig.objects.get(id=1)
    DraftConfig.objects.create(
        tenant=tenant, config_path='theme_v2.footer.color', config_value='blue', created_by_id=1, updated_by_id=1,
    )
    assert DraftConfig.objects.count() == 1, 'bad test data, DraftConfig should be empty before the test'

    with patch.object(DraftConfig, 'loads_into') as mock_loads:
        tenants.publish_tenant_config(tenant_id=tenant.id)

    expected_dest = tenant.lms_configs
    mock_loads.assert_called_once_with(
        tenant_id=tenant.id,
        config_paths=['theme_v2.footer.color'],
        dest=expected_dest,
    )
    assert DraftConfig.objects.count() == 0, ''


@pytest.mark.django_db
def test_publish_tenant_config_merges_lms_configs(base_data):
    """Verify lms_configs is updated after calling loads_into"""
    tenant = TenantConfig.objects.get(id=1)
    test_value = {'footer': {'color': 'blue'}}
    ConfigAccessControl.objects.create(key_name='footer_color', path='footer.color')
    DraftConfig.objects.create(
        tenant=tenant, config_path='footer.color', config_value=test_value, created_by_id=1, updated_by_id=1,
    )
    assert tenant.lms_configs['theme_v2'] != {'footer': {'color': 'red'}}, 'Initial test setup is incorrect'

    def mutate_config(tenant_id, config_paths, dest):  # pylint: disable=unused-argument
        """Mock function to simulate DraftConfig.loads_into behavior."""
        dest['theme_v2'] = test_value

    with patch.object(DraftConfig, 'loads_into', side_effect=mutate_config):
        tenants.publish_tenant_config(tenant_id=tenant.id)

    tenant.refresh_from_db()
    expected_lms_config = base_data['tenant_config'][1]['lms_configs'].copy()
    expected_lms_config['theme_v2'] = test_value
    assert tenant.lms_configs == expected_lms_config


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.tenants.apply_learner_theme')
@patch('futurex_openedx_extensions.helpers.tenants.ConfigMirror.sync_tenant')
def test_publish_tenant_config_no_draft(mock_sync, mock_apply, base_data):  # pylint: disable=unused-argument
    """Verify that publish_tenant_config only applies the learner theme switch and syncs mirrors if no draft exists."""
    tenant_id = 1
    assert DraftConfig.objects.count() == 0, 'bad test data, DraftConfig should be empty before the test'

    with patch.object(DraftConfig, 'loads_into') as mock_loads:
        tenants.publish_tenant_config(tenant_id=tenant_id)

    mock_loads.assert_not_called()
    mock_apply.assert_called_once_with(ANY, save=False)
    assert mock_apply.call_args.args[0].id == tenant_id
    mock_sync.assert_called_once_with(tenant=ANY)
    assert mock_sync.call_args[1]['tenant'].id == tenant_id


@pytest.mark.django_db
def test_publish_tenant_config_tenant_not_found(base_data):  # pylint: disable=unused-argument
    """Verify that publish_tenant_config raises TENANT_NOT_FOUND for an unknown tenant."""
    with pytest.raises(FXCodedException) as exc_info:
        tenants.publish_tenant_config(tenant_id=9999)
    assert exc_info.value.code == FXExceptionCodes.TENANT_NOT_FOUND.value


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.tenants.ConfigMirror.sync_tenant')
def test_publish_tenant_config_calls_sync_tenant(mock_sync, base_data):  # pylint: disable=unused-argument
    """Verify that publish_tenant_config calls ConfigMirror.sync_tenant."""
    tenant_id = 1
    DraftConfig.objects.create(
        tenant_id=tenant_id, config_path='theme_v2.links.facebook', config_value='draft.facebook.com',
        created_by_id=1, updated_by_id=1,
    )
    tenants.publish_tenant_config(tenant_id=tenant_id)
    mock_sync.assert_called_once_with(tenant=ANY)
    assert mock_sync.call_args[1]['tenant'].id == tenant_id


@pytest.mark.django_db
@pytest.mark.parametrize('get_current_request_result, expected_warning', [
    (None, 'get_config_current_request called without a request object!'),
    (Mock(spec=[]), 'get_config_current_request called without a site object!'),
    (
        Mock(site=Mock(domain='unavailable.com')),
        'get_config_current_request could not find a tenant for site: unavailable.com'
    ),
])
def test_get_config_current_request_none(
    get_current_request_result, expected_warning, base_data, caplog,
):  # pylint: disable=unused-argument
    """Verify get_config_current_request function when request is None."""
    with patch('futurex_openedx_extensions.helpers.tenants.get_current_request') as mock_get_current_request:
        mock_get_current_request.return_value = get_current_request_result
        result = tenants.get_config_current_request(keys=['dose not matter in this test case'])
    assert result is None
    assert expected_warning in caplog.text


@pytest.mark.parametrize('cookie, user, expected', [
    ('yes', Mock(is_authenticated=True), True),
    ('YeS', Mock(is_authenticated=True), True),
    ('yes', Mock(is_authenticated=False), False),
    ('yes', None, False),
    ('no', Mock(is_authenticated=True), False),
    (None, Mock(is_authenticated=True), False),
])
def test_is_theme_preview_request(cookie, user, expected):
    """Verify the preview applies only to a signed-in request carrying the cookie (anonymous pages are cached)."""
    request = Mock(spec=['COOKIES', 'user'] if user else ['COOKIES'], COOKIES={'theme-preview': cookie})
    if user:
        request.user = user
    assert tenants.is_theme_preview_request(request) is expected


def test_is_theme_preview_request_no_request():
    """Verify no request means no preview."""
    assert tenants.is_theme_preview_request(None) is False


@pytest.mark.django_db
@pytest.mark.parametrize('cookie_name, cookie_value, expected_published_only, test_case', [
    ('theme-preview', None, True, 'cookie value is None or missing should not enable preview'),
    ('theme-preview', 'no', True, 'cookie value is `no` should not enable preview'),
    ('theme-preview', 'not-yes', True, 'cookie value is not `yes` should not enable preview'),
    ('theme-preview', 'yes', False, 'cookie value is `yes` should enable preview'),
    ('theme-preview', 'yEs', False, 'cookie value is `yes` case insensitive should enable preview'),
    ('any-other-name', 'yes', True, 'cookie name is not `theme-preview` should not enable preview'),
])
def test_get_config_current_request(
    cookie_name, cookie_value, expected_published_only, test_case, base_data,
):  # pylint: disable=unused-argument
    """Verify get_config_current_request function in happy scenarios."""
    with patch(
        'futurex_openedx_extensions.helpers.tenants.get_current_request',
        return_value=Mock(site=Mock(domain='s1.sample.com')),
    ) as mocked_get_current_request:
        mocked_get_current_request.return_value.COOKIES = {cookie_name: cookie_value}
        mocked_get_current_request.return_value.user = Mock(is_authenticated=True)
        with patch('futurex_openedx_extensions.helpers.tenants.get_tenant_config') as mock_get_tenant_config:
            tenants.get_config_current_request(keys=['testing_key'])

    mock_get_tenant_config.assert_called_once_with(
        tenant_id=1,
        keys=['testing_key'],
        published_only=expected_published_only,
    )


@pytest.mark.django_db
@pytest.mark.parametrize('user', [Mock(is_authenticated=False), None])
def test_get_config_current_request_anonymous_cookie_gets_published(user, base_data):  # pylint: disable=W0613
    """Verify an anonymous request with the preview cookie gets the PUBLISHED config."""
    request = Mock(site=Mock(domain='s1.sample.com'), COOKIES={'theme-preview': 'yes'})
    request.user = user
    with patch('futurex_openedx_extensions.helpers.tenants.get_current_request', return_value=request):
        with patch('futurex_openedx_extensions.helpers.tenants.get_tenant_config') as mock_get_tenant_config:
            tenants.get_config_current_request(keys=['testing_key'])

    mock_get_tenant_config.assert_called_once_with(tenant_id=1, keys=['testing_key'], published_only=True)


@pytest.mark.django_db
@pytest.mark.parametrize('writable_fields_filter, expected_keys', [
    (None, ['key1_writable', 'key1_read_only', 'key2_writable', 'key2_read_only']),
    (True, ['key1_writable', 'key2_writable']),
    (False, ['key1_read_only', 'key2_read_only']),
])
def test_get_accessible_config_keys(
    writable_fields_filter, expected_keys, base_data,
):  # pylint: disable=unused-argument
    """Verify get_accessible_config_keys returns all keys when writable_fields_filter is None"""
    with patch('futurex_openedx_extensions.helpers.tenants.get_config_access_control') as mock_get_config_access:
        mock_get_config_access.return_value = {
            'key1_writable': {'writable': True, 'path': 'a.key1_writable'},
            'key1_read_only': {'writable': False, 'path': 'a.key1_read_only'},
            'key2_writable': {'writable': True, 'path': 'a.key2_writable'},
            'key2_read_only': {'writable': False, 'path': 'a.key2_read_only'},
        }
        result = tenants.get_accessible_config_keys(
            user_id=1, tenant_id=1, writable_fields_filter=writable_fields_filter,
        )
    assert result == expected_keys


STAFF_ONLY_ACCESS_CONTROL = {
    'theme': {'writable': True, 'path': 'theme_v2', 'staff_only': False},
    'learner_theme': {'writable': True, 'path': 'theme_v2.learner_theme', 'staff_only': False},
    'allowed': {'writable': True, 'path': 'theme_v2.learner_theme.allowed', 'staff_only': True},
    'allowed_child': {'writable': True, 'path': 'theme_v2.learner_theme.allowed.note', 'staff_only': False},
    'enabled': {'writable': True, 'path': 'theme_v2.learner_theme.enabled', 'staff_only': False},
    'allowed_lookalike': {'writable': True, 'path': 'theme_v2.learner_theme.allowed_x', 'staff_only': False},
    'footer': {'writable': True, 'path': 'theme_v2.footer'},
}


STAFF_ONLY_PROTECTED_KEYS = ['theme', 'learner_theme', 'allowed', 'allowed_child']
STAFF_ONLY_FREE_KEYS = ['enabled', 'allowed_lookalike', 'footer']


@pytest.mark.django_db
@pytest.mark.parametrize('user_id, writable_fields_filter, expected_keys', [
    (1, None, list(STAFF_ONLY_ACCESS_CONTROL)),
    (2, True, list(STAFF_ONLY_ACCESS_CONTROL)),
    (2, False, []),
    (3, None, list(STAFF_ONLY_ACCESS_CONTROL)),
    (3, True, STAFF_ONLY_FREE_KEYS),
    (3, False, STAFF_ONLY_PROTECTED_KEYS),
    (61, True, STAFF_ONLY_FREE_KEYS),
    (9999, None, list(STAFF_ONLY_ACCESS_CONTROL)),
    (9999, False, STAFF_ONLY_PROTECTED_KEYS),
])
def test_get_accessible_config_keys_staff_only(
    user_id, writable_fields_filter, expected_keys, base_data,
):  # pylint: disable=unused-argument
    """
    Verify staff_only keys, and keys whose path overlaps them, are readable by everyone but writable by system staff
    only: for other users they are listed as read-only
    """
    with patch(
        'futurex_openedx_extensions.helpers.tenants.get_config_access_control',
        return_value=STAFF_ONLY_ACCESS_CONTROL,
    ):
        assert tenants.get_accessible_config_keys(
            user_id=user_id, tenant_id=1, writable_fields_filter=writable_fields_filter,
        ) == expected_keys


@pytest.mark.parametrize('key, expected_result', [
    ('allowed', True),
    ('theme', True),
    ('learner_theme', True),
    ('allowed_child', True),
    ('enabled', False),
    ('allowed_lookalike', False),
    ('footer', False),
    ('unknown', False),
])
def test_is_config_key_staff_only(key, expected_result):
    """Verify is_config_key_staff_only protects the staff_only key and every key whose path overlaps it"""
    with patch(
        'futurex_openedx_extensions.helpers.tenants.get_config_access_control',
        return_value=STAFF_ONLY_ACCESS_CONTROL,
    ):
        assert tenants.is_config_key_staff_only(key) is expected_result


@patch('futurex_openedx_extensions.helpers.tenants.get_config_access_control')
@pytest.mark.django_db
def test_get_tenant_readable_lms_config_success(mock_access_control):
    """Verify readable keys are returned correctly and draft keys are excluded"""
    tenant = TenantConfig.objects.get(id=1)
    tenant.lms_configs = {
        'theme_v2': {
            'header': {
                'logo': '/logo.png',
                'title': 'Hello World'
            },
            'footer': {
                'color': 'black'
            }
        },
        'analytics': {
            'tracking_id': 'UA-999'
        },
        'config_draft': {
            'should_not': 'appear'
        }
    }
    tenant.save()

    mock_access_control.return_value = {
        'logo': {'path': 'theme_v2.header.logo', 'writable': True},
        'title': {'path': 'theme_v2.header.title', 'writable': True},
        'tracking': {'path': 'analytics.tracking_id', 'writable': False},
    }

    result = tenants.get_tenant_readable_lms_config(tenant.id)

    assert result == {
        'theme_v2': {
            'header': {
                'logo': '/logo.png',
                'title': 'Hello World',
            },
        },
        'analytics': {
            'tracking_id': 'UA-999'
        }
    }


@patch('futurex_openedx_extensions.helpers.tenants.get_config_access_control', return_value={})
@pytest.mark.django_db
def test_get_tenant_readable_lms_config_missing_tenant(_):
    """Verify exception is raised if tenant does not exist"""
    with pytest.raises(FXCodedException) as exc:
        tenants.get_tenant_readable_lms_config(tenant_id=9999)

    assert exc.value.code == FXExceptionCodes.TENANT_NOT_FOUND.value
    assert str(exc.value) == 'Unable to find tenant with id: (9999)'


@patch('futurex_openedx_extensions.helpers.tenants.get_config_access_control')
@pytest.mark.django_db
def test_get_tenant_readable_lms_config_deduplicates_nested_keys(mock_access_control):
    """Verify child paths are excluded if a parent path is already included"""
    tenant = TenantConfig.objects.get(id=1)
    tenant.lms_configs = {
        'parent': {
            'child1': 'val1',
            'child2': 'val2',
        }
    }
    tenant.save()

    mock_access_control.return_value = {
        'child1': {'path': 'parent.child1', 'writable': True},
        'parent': {'path': 'parent', 'writable': True},
    }

    result = tenants.get_tenant_readable_lms_config(tenant.id)

    assert result == {
        'parent': {
            'child1': 'val1',
            'child2': 'val2',
        }
    }


@pytest.mark.parametrize('config_value, call_info, _', [
    (None, False, 'get_all_tenants_info should not be called when config_value is None'),
    ({'values': {}}, False, 'get_all_tenants_info should not be called when fx_css_override_asset_slug is missing'),
    (
        {'values': {'fx_css_override_asset_slug': 'test-slug'}},
        True,
        'get_all_tenants_info should be called when fx_css_override_asset_slug is defined',
    ),
])
@patch('futurex_openedx_extensions.helpers.tenants.get_config_current_request')
@patch('futurex_openedx_extensions.helpers.tenants.get_all_tenants_info')
def test_get_fx_theme_css_override_calls(mock_info, mock_get_config, config_value, call_info, _):
    """Verify get_fx_theme_css_override calls get_config_current_request and get_all_tenants_info correctly."""
    mock_get_config.return_value = config_value
    tenants.get_fx_theme_css_override()

    mock_get_config.assert_called_once_with(keys=['fx_css_override_asset_slug', 'fx_dev_css_enabled'])
    if call_info:
        mock_info.assert_called_once()
    else:
        mock_info.assert_not_called()


@pytest.mark.parametrize('config_value, assets, expected_result_values, test_usecase', [
    (
        {'values': {'fx_dev_css_enabled': False}},
        {'_': 'assets are ignored in this test because override slug is not defined'},
        ('', False),
        'dev css returned as defined',
    ),
    (
        {'values': {'fx_dev_css_enabled': True}},
        {'_': 'assets are ignored in this test because override slug is not defined'},
        ('', True),
        'dev css returned as defined',
    ),
    (
        {'values': {}},
        {'_': 'assets are ignored in this test because override slug is not defined'},
        ('', False),
        'dev css returned as False if not defined',
    ),
    (
        {'values': {'fx_css_override_asset_slug': 'slug1'}},
        {'slug1': 'https://example.com/asset.css'},
        ('https://example.com/asset.css', False),
        'override asset returned as defined',
    ),
    (
        {'values': {'fx_css_override_asset_slug': 'slug-not-defined'}},
        {'slug1': 'https://example.com/asset.css'},
        ('', False),
        'override asset returned as empty when not found',
    ),
])
@patch('futurex_openedx_extensions.helpers.tenants.get_config_current_request')
@patch('futurex_openedx_extensions.helpers.tenants.get_all_tenants_info')
def test_get_fx_theme_css_override_success(
    mock_info, mock_get_config, config_value, assets, expected_result_values, test_usecase,
):  # pylint: disable=too-many-arguments
    """Verify get_fx_theme_css_override returns the correct result."""
    mock_get_config.return_value = config_value
    mock_info.return_value = {
        'template_tenant': {
            'assets': assets,
        }
    }

    expected_result = {
        'css_override_file': expected_result_values[0],
        'dev_css_enabled': expected_result_values[1],
    }
    result = tenants.get_fx_theme_css_override()
    assert result == expected_result, test_usecase


@pytest.mark.django_db
@pytest.mark.parametrize(
    'the_request, org, tenants_by_org, tenants_sites, expected_site_called, test_case',
    [
        (None, 'org1', [1], ['s1.sample.com'], False, 'request is None, should not call Site.objects.get'),
        (Mock(spec=[]), 'org1', [1], ['s1.sample.com'], False, 'request has no site, should not call Site.objects.get'),
        (Mock(site=Mock()), '', [1], ['s1.sample.com'], False, 'org is empty, should not call Site.objects.get'),
        (Mock(site=Mock()), 'orgX', [], [], False, 'no tenants for org, should not call Site.objects.get'),
        (Mock(site=Mock()), 'org1', [], [], False, 'tenants_by_org returns empty, should not call Site.objects.get'),
        (Mock(site=Mock()), 'org1', [1], [], False, 'tenants_sites returns empty, should not call Site.objects.get'),
        (Mock(site=Mock()), 'org1', [1], ['s1.sample.com'], True, 'happy path, should call Site.objects.get'),
    ],
)
def test_set_request_domain_by_org(
    the_request, org, tenants_by_org, tenants_sites, expected_site_called, test_case,
):  # pylint: disable=too-many-arguments, unused-argument
    """Verify set_request_domain_by_org covers all branches"""
    with patch('futurex_openedx_extensions.helpers.tenants.get_tenants_by_org', return_value=tenants_by_org), \
         patch('futurex_openedx_extensions.helpers.tenants.get_tenants_sites', return_value=tenants_sites), \
         patch('futurex_openedx_extensions.helpers.tenants.Site.objects.get') as mock_site_get:

        if expected_site_called:
            mock_site_get.return_value = Mock(domain=tenants_sites[0])
        tenants.set_request_domain_by_org(the_request, org)

        if expected_site_called:
            mock_site_get.assert_called_once_with(domain=tenants_sites[0])
            assert hasattr(the_request, 'site')
            assert the_request.site.domain == tenants_sites[0]
        else:
            mock_site_get.assert_not_called()


@pytest.mark.django_db
def test_set_request_domain_by_org_sets_first_site():
    """Verify set_request_domain_by_org sets request.site to the first site from tenants_sites"""
    the_request = Mock(site=Mock())
    org = 'org1'

    with patch(
        'futurex_openedx_extensions.helpers.tenants.Site.objects.get',
        return_value=Mock(domain='s1.sample.com')
    ) as mock_site_get:
        tenants.set_request_domain_by_org(the_request, org)
        mock_site_get.assert_called_once_with(domain='s1.sample.com')
        assert the_request.site.domain == 's1.sample.com'


@patch('futurex_openedx_extensions.helpers.tenants.get_tenant_config')
def test_get_tenant_config_value_success(mock_get_tenant_config):
    """Verify get_tenant_config_value returns the correct value when key exists."""
    mock_get_tenant_config.return_value = {
        'values': {
            'desired_key': 'expected_value',
            'other_key': 'other_value',
        },
        'bad_keys': [],
        'not_permitted': [],
    }

    result = tenants.get_tenant_config_value(tenant_id=1, config_key='desired_key')
    assert result == 'expected_value'
    mock_get_tenant_config.assert_called_once_with(tenant_id=1, keys=['desired_key'], published_only=True)


@patch('futurex_openedx_extensions.helpers.tenants.get_tenant_config')
def test_get_tenant_config_value_key_not_found(mock_get_tenant_config):
    """Verify get_tenant_config_value raises exception when key does not exist."""
    mock_get_tenant_config.return_value = {
        'values': {
            'other_key': 'other_value',
        },
        'bad_keys': ['desired_key'],
        'not_permitted': [],
    }

    with pytest.raises(FXCodedException) as exc_info:
        tenants.get_tenant_config_value(tenant_id=1, config_key='desired_key')

    assert exc_info.value.code == FXExceptionCodes.CONFIG_KEY_NOT_FOUND.value
    assert str(exc_info.value) == 'Config key (desired_key) not found for tenant id: 1'
    mock_get_tenant_config.assert_called_once_with(tenant_id=1, keys=['desired_key'], published_only=True)


@patch('futurex_openedx_extensions.helpers.tenants.get_tenant_config')
def test_get_tenant_config_value_not_permitted(mock_get_tenant_config):
    """Verify get_tenant_config_value raises exception when key is not permitted."""
    mock_get_tenant_config.return_value = {
        'values': {},
        'bad_keys': [],
        'not_permitted': ['restricted_key'],
    }

    with pytest.raises(FXCodedException) as exc_info:
        tenants.get_tenant_config_value(tenant_id=1, config_key='restricted_key')

    assert exc_info.value.code == FXExceptionCodes.CONFIG_KEY_NOT_PERMITTED.value
    assert str(exc_info.value) == 'Config key (restricted_key) not permitted for tenant id: 1'
    mock_get_tenant_config.assert_called_once_with(tenant_id=1, keys=['restricted_key'], published_only=True)


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.tenants.get_config_access_control')
def test_set_tenant_config_value_success(mock_access, base_data):  # pylint: disable=unused-argument
    """Verify set_tenant_config_value works correctly as expected."""
    config_key = 'test_key'
    mock_access.return_value = {
        config_key: {'path': 'test_path.test_path2'},
    }
    tenant = TenantConfig.objects.get(id=1)
    tenant.lms_configs = {
        'some_key': 'something',
        'test_path': 'not a dictionary. should be forced to dictionary when setting the value.',
    }
    tenant.save()

    new_value = {
        'sub_key1': 'value1',
        'sub_key2': 2,
    }
    tenants.set_tenant_config_value(tenant_id=1, config_key=config_key, value=new_value)

    tenant.refresh_from_db()
    assert not DeepDiff(
        tenant.lms_configs,
        {'some_key': 'something', 'test_path': {'test_path2': new_value}},
        ignore_type_in_groups=[(dict, OrderedDict)],
    )


@pytest.mark.django_db
def test_set_tenant_config_value_tenant_not_found(base_data):  # pylint: disable=unused-argument
    """Verify set_tenant_config_value raises exception when tenant is not found."""
    with pytest.raises(FXCodedException) as exc_info:
        tenants.set_tenant_config_value(tenant_id=999, config_key='dummy', value='dummy')

    assert exc_info.value.code == FXExceptionCodes.TENANT_NOT_FOUND.value
    assert str(exc_info.value) == 'Unable to find tenant with id: 999'


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.tenants.get_config_access_control')
def test_set_tenant_config_value_key_not_found(mock_access, base_data):  # pylint: disable=unused-argument
    """Verify set_tenant_config_value raises exception when key is not found."""
    config_key = 'non_existent_key'
    mock_access.return_value = {
        'some_other_key': {'path': 'some.path'},
    }

    with pytest.raises(FXCodedException) as exc_info:
        tenants.set_tenant_config_value(tenant_id=1, config_key=config_key, value='new_value')

    assert exc_info.value.code == FXExceptionCodes.CONFIG_KEY_NOT_FOUND.value
    assert str(exc_info.value) == f'Config key ({config_key}) not found for tenant id: 1'


LEARNER_URLS = {
    'LEARNER_HOME_MICROFRONTEND_URL': '/learner/my',
    'PROFILE_MICROFRONTEND_URL': '/learner/profile/u/',
    'ACCOUNT_MICROFRONTEND_URL': '/learner/profile',
}


def _learner_switch(allowed, enabled):
    """Return a theme_v2 config with the learner theme switch"""
    return {'learner_theme': {'allowed': allowed, 'enabled': enabled}, 'other': 'kept'}


SAVED_COLOR = 'THEME_OPTIONS.interactive_color'


def _active_configs(**extra):
    """Return the lms_configs of a tenant with the learner theme active"""
    configs = {
        'theme_v2': _learner_switch(True, True),
        'THEME_OPTIONS': {
            'theme': {'name': 'fx-learner', 'parent': 'indigo'}, 'other_option': 1, 'interactive_color': '#1B8354',
        },
        'MFE_CONFIG': {'FX_LEARNER_THEME': True, 'OTHER': 'x'},
        'ENABLE_LEARNER_HOME_MFE': True,
        'FX_LEARNER_THEME_SAVED': {SAVED_COLOR: None},
        **LEARNER_URLS,
    }
    configs.update(extra)
    return configs


def _visual_identity(primary_color):
    """Return a theme_v2.visual_identity with the given primary colour"""
    return {'colors': [{'color_type': 'primary_color', 'hex': primary_color}]}


@pytest.mark.parametrize('theme_name', ['indigo', 'fx-learner'])
def test_apply_learner_theme_activates(theme_name):
    """Verify the hook switches the theme on, keeping the other THEME_OPTIONS and MFE_CONFIG keys"""
    tenant = Mock(id=7, lms_configs={
        'theme_v2': _learner_switch(True, True),
        'THEME_OPTIONS': {'theme': {'name': theme_name}, 'other_option': 1},
        'MFE_CONFIG': {'OTHER': 'x'},
        'LMS_BASE': 's.sample.com',
    })

    with patch('futurex_openedx_extensions.helpers.tenants.invalidate_cache') as mock_invalidate:
        assert tenants.apply_learner_theme(tenant) is True

    assert tenant.lms_configs == _active_configs(LMS_BASE='s.sample.com')
    tenant.save.assert_called_once_with()
    mock_invalidate.assert_called_once_with()


def test_apply_learner_theme_activates_without_mfe_config():
    """Verify the hook creates MFE_CONFIG when it is missing"""
    tenant = Mock(id=7, lms_configs={
        'theme_v2': _learner_switch(True, True),
        'THEME_OPTIONS': {'theme': {'name': 'indigo'}},
        'MFE_CONFIG': 'not a dict',
    })

    assert tenants.apply_learner_theme(tenant, save=False) is True
    assert tenant.lms_configs['MFE_CONFIG'] == {'FX_LEARNER_THEME': True}
    assert tenant.lms_configs['THEME_OPTIONS']['interactive_color'] == '#1B8354'
    tenant.save.assert_not_called()


def test_apply_learner_theme_idempotent():
    """Verify applying the hook on an already active tenant changes nothing and saves nothing"""
    tenant = Mock(id=7, lms_configs=_active_configs())

    assert tenants.apply_learner_theme(tenant) is False
    assert tenant.lms_configs == _active_configs()
    tenant.save.assert_not_called()


def test_apply_learner_theme_adds_learner_home_flag_to_an_already_active_tenant():
    """Verify a tenant activated before the hook set ENABLE_LEARNER_HOME_MFE gets the key on the next apply"""
    lms_configs = _active_configs()
    lms_configs.pop('ENABLE_LEARNER_HOME_MFE')
    lms_configs.pop('FX_LEARNER_THEME_SAVED')
    lms_configs['THEME_OPTIONS'].pop('interactive_color')
    tenant = Mock(id=7, lms_configs=lms_configs)

    with patch('futurex_openedx_extensions.helpers.tenants.invalidate_cache'):
        assert tenants.apply_learner_theme(tenant) is True

    assert tenant.lms_configs == _active_configs()
    tenant.save.assert_called_once_with()
    assert tenants.apply_learner_theme(tenant) is False


@pytest.mark.parametrize('own_value', [True, False])
def test_apply_learner_theme_records_own_flag_of_an_already_active_tenant(own_value):
    """Verify a tenant activated before the hook set the key, with its own value, has that value recorded"""
    lms_configs = _active_configs(ENABLE_LEARNER_HOME_MFE=own_value)
    lms_configs.pop('FX_LEARNER_THEME_SAVED')
    tenant = Mock(id=7, lms_configs=lms_configs)

    assert tenants.apply_learner_theme(tenant, save=False) is True

    assert tenant.lms_configs == _active_configs(
        FX_LEARNER_THEME_SAVED={'ENABLE_LEARNER_HOME_MFE': own_value, SAVED_COLOR: '#1B8354'},
    )
    assert tenants.apply_learner_theme(tenant, save=False) is False


@pytest.mark.parametrize('own_flag', [{}, {'ENABLE_LEARNER_HOME_MFE': True}, {'ENABLE_LEARNER_HOME_MFE': False}])
def test_apply_learner_theme_on_then_off_restores_learner_home_flag(own_flag):
    """Verify on (twice) then off leaves ENABLE_LEARNER_HOME_MFE exactly as the tenant had it before the theme"""
    original = {'THEME_OPTIONS': {'theme': {'name': 'indigo'}}, 'X': 1, **own_flag}
    tenant = Mock(id=7, lms_configs={**copy.deepcopy(original), 'theme_v2': _learner_switch(True, True)})

    assert tenants.apply_learner_theme(tenant, save=False) is True
    assert tenant.lms_configs['ENABLE_LEARNER_HOME_MFE'] is True
    assert tenant.lms_configs['FX_LEARNER_THEME_SAVED'] == {**own_flag, SAVED_COLOR: None}
    assert tenants.apply_learner_theme(tenant, save=False) is False

    tenant.lms_configs['theme_v2'] = _learner_switch(True, False)
    assert tenants.apply_learner_theme(tenant, save=False) is True
    assert tenant.lms_configs == {**original, 'theme_v2': _learner_switch(True, False), 'MFE_CONFIG': {}}
    assert tenants.apply_learner_theme(tenant, save=False) is False


def test_apply_learner_theme_activation_replaces_invalid_saved_record():
    """Verify activation rewrites an FX_LEARNER_THEME_SAVED that is not a dict"""
    tenant = Mock(id=7, lms_configs=_active_configs(FX_LEARNER_THEME_SAVED='broken'))

    assert tenants.apply_learner_theme(tenant, save=False) is True
    assert tenant.lms_configs == _active_configs(
        FX_LEARNER_THEME_SAVED={'ENABLE_LEARNER_HOME_MFE': True, SAVED_COLOR: '#1B8354'},
    )


@pytest.mark.parametrize('own_options, primary_color, expected_color', [
    ({}, None, '#1B8354'),
    ({'interactive_color': '#3b85ff'}, None, '#1B8354'),
    ({'interactive_color': '#3b85ff'}, '#4600C7', '#1B8354'),
    ({'interactive_color': '#3b85ff'}, '#a1b', '#aa11bb'),
    ({}, '#0A7D4F', '#0A7D4F'),
    ({'interactive_color': None}, '#0A7D4F', '#0A7D4F'),
])
def test_apply_learner_theme_interactive_color_on_then_off(own_options, primary_color, expected_color):
    """
    Verify the hook sets the colour the MFEs get (THEME_OPTIONS.interactive_color) to the learner pages' brand
    colour while the theme is on, and that switching off leaves the tenant's own value exactly as it was
    """
    original = {'THEME_OPTIONS': {'theme': {'name': 'indigo'}, **own_options}, 'theme_v2': {}}
    if primary_color:
        original['theme_v2']['visual_identity'] = _visual_identity(primary_color)
    lms_configs = copy.deepcopy(original)
    lms_configs['theme_v2'].update(_learner_switch(True, True))
    tenant = Mock(id=7, lms_configs=lms_configs)

    assert tenants.apply_learner_theme(tenant, save=False) is True
    assert tenant.lms_configs['THEME_OPTIONS']['interactive_color'] == expected_color
    assert tenant.lms_configs['FX_LEARNER_THEME_SAVED'] == {SAVED_COLOR: own_options.get('interactive_color')}
    assert tenants.apply_learner_theme(tenant, save=False) is False

    tenant.lms_configs['theme_v2'].update(_learner_switch(True, False))
    assert tenants.apply_learner_theme(tenant, save=False) is True
    if own_options == {'interactive_color': None}:
        original['THEME_OPTIONS'].pop('interactive_color')
    original['theme_v2'].update(_learner_switch(True, False))
    assert tenant.lms_configs == {**original, 'MFE_CONFIG': {}}
    assert tenants.apply_learner_theme(tenant, save=False) is False


def test_apply_learner_theme_interactive_color_follows_published_primary_color():
    """Verify a primary colour published while the theme is on reaches the MFEs, without touching the record"""
    lms_configs = _active_configs(FX_LEARNER_THEME_SAVED={SAVED_COLOR: '#3b85ff'})
    lms_configs['theme_v2']['visual_identity'] = _visual_identity('#0A7D4F')
    tenant = Mock(id=7, lms_configs=lms_configs)

    assert tenants.apply_learner_theme(tenant, save=False) is True
    assert tenant.lms_configs['THEME_OPTIONS']['interactive_color'] == '#0A7D4F'
    assert tenant.lms_configs['FX_LEARNER_THEME_SAVED'] == {SAVED_COLOR: '#3b85ff'}

    tenant.lms_configs['theme_v2']['visual_identity'] = _visual_identity('#4600C7')
    assert tenants.apply_learner_theme(tenant, save=False) is True
    assert tenant.lms_configs['THEME_OPTIONS']['interactive_color'] == '#1B8354'
    assert tenant.lms_configs['FX_LEARNER_THEME_SAVED'] == {SAVED_COLOR: '#3b85ff'}


@pytest.mark.parametrize('own_options', [{}, {'interactive_color': '#3b85ff'}])
def test_apply_learner_theme_records_own_interactive_color_of_an_already_active_tenant(own_options):
    """Verify a tenant activated before the hook set the colour has its own colour recorded on the next apply"""
    lms_configs = _active_configs(FX_LEARNER_THEME_SAVED={'ENABLE_LEARNER_HOME_MFE': False})
    lms_configs['THEME_OPTIONS'].pop('interactive_color')
    lms_configs['THEME_OPTIONS'].update(own_options)
    tenant = Mock(id=7, lms_configs=lms_configs)

    assert tenants.apply_learner_theme(tenant, save=False) is True
    assert tenant.lms_configs == _active_configs(FX_LEARNER_THEME_SAVED={
        'ENABLE_LEARNER_HOME_MFE': False, SAVED_COLOR: own_options.get('interactive_color'),
    })
    assert tenants.apply_learner_theme(tenant, save=False) is False

    tenant.lms_configs['theme_v2'] = _learner_switch(True, False)
    assert tenants.apply_learner_theme(tenant, save=False) is True
    assert tenant.lms_configs['THEME_OPTIONS'] == {'theme': {'name': 'indigo'}, 'other_option': 1, **own_options}
    assert tenant.lms_configs['ENABLE_LEARNER_HOME_MFE'] is False


def test_apply_learner_theme_deactivate_keeps_interactive_color_without_a_record():
    """Verify switching off leaves the colour alone when the hook has no record of taking it over"""
    tenant = Mock(id=7, lms_configs=_active_configs(
        theme_v2=_learner_switch(True, False), FX_LEARNER_THEME_SAVED={},
    ))

    assert tenants.apply_learner_theme(tenant, save=False) is True
    assert tenant.lms_configs['THEME_OPTIONS'] == {
        'theme': {'name': 'indigo'}, 'other_option': 1, 'interactive_color': '#1B8354',
    }


@pytest.mark.parametrize('theme_options, saved_color, expected', [
    ('broken', '#3b85ff', {'interactive_color': '#3b85ff'}),
    ('broken', None, 'broken'),
])
def test_apply_learner_theme_deactivate_restores_color_into_broken_theme_options(theme_options, saved_color, expected):
    """Verify switching off restores a recorded colour even when THEME_OPTIONS is no longer a dict"""
    tenant = Mock(id=7, lms_configs={
        'theme_v2': _learner_switch(True, False),
        'THEME_OPTIONS': theme_options,
        'FX_LEARNER_THEME_SAVED': {SAVED_COLOR: saved_color},
    })

    assert tenants.apply_learner_theme(tenant, save=False) is True
    assert tenant.lms_configs == {'theme_v2': _learner_switch(True, False), 'THEME_OPTIONS': expected}


@pytest.mark.parametrize('theme_options', [
    {'theme': {'name': 'bragi'}},
    {'theme': 'indigo'},
    {},
    None,
])
def test_apply_learner_theme_refuses_other_themes(theme_options, caplog):
    """Verify the hook leaves a tenant whose theme is neither indigo nor fx-learner untouched, with a warning"""
    lms_configs = {'theme_v2': _learner_switch(True, True), 'MFE_CONFIG': {'OTHER': 'x'}}
    if theme_options is not None:
        lms_configs['THEME_OPTIONS'] = theme_options
    tenant = Mock(id=7, lms_configs=copy.deepcopy(lms_configs))

    assert tenants.apply_learner_theme(tenant) is False

    assert tenant.lms_configs == lms_configs
    tenant.save.assert_not_called()
    assert 'neither indigo nor fx-learner; theme left untouched' in caplog.text


@pytest.mark.parametrize('allowed, enabled', [
    (True, False), (False, True), (None, True), ('true', True), (True, 1),
])
def test_apply_learner_theme_deactivates(allowed, enabled):
    """Verify the hook switches the theme off when the switch is not fully on"""
    tenant = Mock(id=7, lms_configs=_active_configs(theme_v2=_learner_switch(allowed, enabled)))

    assert tenants.apply_learner_theme(tenant, save=False) is True

    assert tenant.lms_configs == {
        'theme_v2': _learner_switch(allowed, enabled),
        'THEME_OPTIONS': {'theme': {'name': 'indigo'}, 'other_option': 1},
        'MFE_CONFIG': {'OTHER': 'x'},
    }


def test_apply_learner_theme_deactivate_keeps_tenant_urls():
    """Verify switching off keeps MFE URLs the tenant set to its own values"""
    tenant = Mock(id=7, lms_configs=_active_configs(
        theme_v2=_learner_switch(False, True),
        LEARNER_HOME_MICROFRONTEND_URL='https://apps.sample.com/learner-dashboard',
    ))

    assert tenants.apply_learner_theme(tenant, save=False) is True
    assert tenant.lms_configs['LEARNER_HOME_MICROFRONTEND_URL'] == 'https://apps.sample.com/learner-dashboard'
    assert 'PROFILE_MICROFRONTEND_URL' not in tenant.lms_configs
    assert 'ACCOUNT_MICROFRONTEND_URL' not in tenant.lms_configs
    assert 'ENABLE_LEARNER_HOME_MFE' not in tenant.lms_configs
    assert 'FX_LEARNER_THEME_SAVED' not in tenant.lms_configs


@pytest.mark.parametrize('flag_value', [False, 1, 'true'])
def test_apply_learner_theme_deactivate_keeps_changed_learner_home_flag(flag_value):
    """Verify switching off keeps an ENABLE_LEARNER_HOME_MFE that no longer holds the value the hook set"""
    tenant = Mock(id=7, lms_configs=_active_configs(
        theme_v2=_learner_switch(False, True), ENABLE_LEARNER_HOME_MFE=flag_value,
        FX_LEARNER_THEME_SAVED={'ENABLE_LEARNER_HOME_MFE': True},
    ))

    assert tenants.apply_learner_theme(tenant, save=False) is True
    assert tenant.lms_configs['ENABLE_LEARNER_HOME_MFE'] == flag_value
    assert 'LEARNER_HOME_MICROFRONTEND_URL' not in tenant.lms_configs
    assert 'FX_LEARNER_THEME_SAVED' not in tenant.lms_configs


@pytest.mark.parametrize('saved', [None, 'broken'])
def test_apply_learner_theme_deactivate_keeps_flag_the_hook_did_not_take_over(saved):
    """Verify switching off keeps a true ENABLE_LEARNER_HOME_MFE when there is no record that the hook set it"""
    lms_configs = _active_configs(theme_v2=_learner_switch(False, True), FX_LEARNER_THEME_SAVED=saved)
    if saved is None:
        lms_configs.pop('FX_LEARNER_THEME_SAVED')
    tenant = Mock(id=7, lms_configs=lms_configs)

    assert tenants.apply_learner_theme(tenant, save=False) is True
    assert tenant.lms_configs['ENABLE_LEARNER_HOME_MFE'] is True
    assert 'FX_LEARNER_THEME_SAVED' not in tenant.lms_configs


def test_apply_learner_theme_never_active_tenant_keeps_flag_with_hook_like_url():
    """Verify a tenant that never had the theme keeps its own flag even when its learner home URL equals ours"""
    tenant = Mock(id=7, lms_configs={
        'ENABLE_LEARNER_HOME_MFE': True,
        'LEARNER_HOME_MICROFRONTEND_URL': '/learner/my',
        'THEME_OPTIONS': {'theme': {'name': 'bragi'}},
    })

    assert tenants.apply_learner_theme(tenant, save=False) is True
    assert tenant.lms_configs == {'ENABLE_LEARNER_HOME_MFE': True, 'THEME_OPTIONS': {'theme': {'name': 'bragi'}}}


@pytest.mark.parametrize('lms_configs', [
    {'THEME_OPTIONS': {'theme': {'name': 'indigo'}}, 'LMS_BASE': 's.sample.com'},
    {'THEME_OPTIONS': {'theme': {'name': 'bragi'}}, 'MFE_CONFIG': {'A': 1}},
    {'theme_v2': _learner_switch(False, False), 'THEME_OPTIONS': {'theme': {'name': 'indigo', 'parent': 'x'}}},
    {'LMS_BASE': 's.sample.com'},
    {'ENABLE_LEARNER_HOME_MFE': True, 'THEME_OPTIONS': {'theme': {'name': 'indigo'}}},
    {'ENABLE_LEARNER_HOME_MFE': True, 'LEARNER_HOME_MICROFRONTEND_URL': 'https://apps.sample.com/learner-dashboard'},
    {'theme_v2': _learner_switch(True, False), 'ENABLE_LEARNER_HOME_MFE': False},
    'not a dict',
])
def test_apply_learner_theme_no_op_without_the_switch(lms_configs):
    """Verify a tenant that never had the learner theme is left exactly as it is"""
    tenant = Mock(id=7, lms_configs=copy.deepcopy(lms_configs))

    assert tenants.apply_learner_theme(tenant) is False
    assert tenant.lms_configs == lms_configs
    tenant.save.assert_not_called()


@pytest.mark.django_db
def test_publish_tenant_config_applies_learner_theme_in_one_save(base_data):  # pylint: disable=unused-argument
    """Verify publishing the switch activates the learner theme in the published config"""
    tenant = TenantConfig.objects.get(id=1)
    tenant.lms_configs['THEME_OPTIONS'] = {'theme': {'name': 'indigo'}}
    tenant.save()
    for path, value in (
        ('theme_v2.learner_theme.allowed', True),
        ('theme_v2.learner_theme.enabled', True),
        ('theme_v2.visual_identity', _visual_identity('#0A7D4F')),
    ):
        DraftConfig.objects.create(
            tenant=tenant, config_path=path, config_value=value, created_by_id=1, updated_by_id=1,
        )

    with patch('futurex_openedx_extensions.helpers.tenants.ConfigMirror.sync_tenant') as mock_sync:
        tenants.publish_tenant_config(tenant_id=tenant.id)

    synced_tenant = mock_sync.call_args[1]['tenant']
    expected_theme_options = {'theme': {'name': 'fx-learner', 'parent': 'indigo'}, 'interactive_color': '#0A7D4F'}
    assert synced_tenant.lms_configs['THEME_OPTIONS'] == expected_theme_options
    tenant.refresh_from_db()
    assert tenant.lms_configs['THEME_OPTIONS'] == expected_theme_options
    assert tenant.lms_configs['MFE_CONFIG'] == {'FX_LEARNER_THEME': True}
    assert tenant.lms_configs['ENABLE_LEARNER_HOME_MFE'] is True
    assert tenant.lms_configs['FX_LEARNER_THEME_SAVED'] == {SAVED_COLOR: None}
    assert tenant.lms_configs['theme_v2']['learner_theme'] == {'allowed': True, 'enabled': True}
    assert DraftConfig.objects.filter(tenant=tenant).count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize('config_key, expected_theme', [
    ('learner_theme_allowed', {'name': 'fx-learner', 'parent': 'indigo'}),
    ('other_key', {'name': 'indigo'}),
])
@patch('futurex_openedx_extensions.helpers.tenants.invalidate_tenant_readable_lms_configs')
@patch('futurex_openedx_extensions.helpers.tenants.get_config_access_control')
def test_set_tenant_config_value_applies_learner_theme(
    mock_access, mock_invalidate, config_key, expected_theme, base_data,
):  # pylint: disable=unused-argument
    """Verify writing learner_theme_allowed directly applies the learner theme switch; other keys do not"""
    mock_access.return_value = {config_key: {'path': 'theme_v2.learner_theme.allowed'}}
    tenant = TenantConfig.objects.get(id=1)
    tenant.lms_configs = {
        'theme_v2': {'learner_theme': {'enabled': True}},
        'THEME_OPTIONS': {'theme': {'name': 'indigo'}},
    }
    tenant.save()

    tenants.set_tenant_config_value(tenant_id=1, config_key=config_key, value=True)

    tenant.refresh_from_db()
    assert tenant.lms_configs['THEME_OPTIONS']['theme'] == expected_theme
    assert mock_invalidate.call_count == (1 if config_key == 'learner_theme_allowed' else 0)


@pytest.mark.parametrize('default_theme, expected', [
    (None, {'name': 'fx-learner', 'parent': 'indigo'}),
    ('indigo', {'name': 'fx-learner', 'parent': 'indigo'}),
    ('fx-learner', {'name': 'fx-learner', 'parent': 'indigo'}),
    ('nelp-edx-theme-bragi', {'name': 'fx-learner', 'parent': 'indigo', 'grandparent': 'nelp-edx-theme-bragi'}),
])
def test_get_learner_theme_options(default_theme, expected):
    """Verify that the platform default theme is kept as the grandparent of the learner theme."""
    with override_settings(EOX_THEMING_DEFAULT_THEME_NAME=default_theme):
        assert tenants.get_learner_theme_options() == expected


def _set_extended_profile_fields(tenant_id, value):
    """Helper to set extended_profile_fields of a tenant"""
    tenant = TenantConfig.objects.get(id=tenant_id)
    tenant.lms_configs['extended_profile_fields'] = value
    tenant.save()


@pytest.mark.django_db
def test_get_all_extended_profile_fields(base_data):  # pylint: disable=unused-argument
    """Verify that only valid tenants with custom fields are returned, with non-string names dropped"""
    _set_extended_profile_fields(1, ['region', 5, '', 'employer'])
    _set_extended_profile_fields(2, 'not a list')
    _set_extended_profile_fields(3, [])
    _set_extended_profile_fields(4, ['excluded_tenant'])
    _set_extended_profile_fields(7, ['region'])

    assert tenants.get_all_extended_profile_fields() == {1: ['region', 'employer'], 7: ['region']}


@pytest.mark.django_db
def test_get_all_extended_profile_fields_is_being_cached(base_data, cache_testing):  # pylint: disable=unused-argument
    """Verify that get_all_extended_profile_fields is being cached."""
    _set_extended_profile_fields(1, ['region'])
    assert cache.get(cs.CACHE_NAME_ALL_EXTENDED_PROFILE_FIELDS) is None
    result = tenants.get_all_extended_profile_fields()
    assert cache.get(cs.CACHE_NAME_ALL_EXTENDED_PROFILE_FIELDS)['data'] == result


@pytest.mark.django_db
@pytest.mark.parametrize('tenant_ids, expected', [
    ([1, 7], ['employer', 'region']),
    ([7], ['region']),
    ([2, 3], []),
    ([], []),
    (None, []),
])
def test_get_tenants_extended_profile_fields(base_data, tenant_ids, expected):  # pylint: disable=unused-argument
    """Verify that the union of the tenants' custom field names is returned sorted"""
    _set_extended_profile_fields(1, ['region', 'employer'])
    _set_extended_profile_fields(7, ['region'])

    assert tenants.get_tenants_extended_profile_fields(tenant_ids) == expected
