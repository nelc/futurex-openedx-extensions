"""Tests for tenants helpers."""
from unittest.mock import MagicMock, Mock, patch

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


@pytest.fixture
def lms_configs_mock():
    """Mock LMS configs."""
    lms_configs = {
        'key1': 'value1',
        'key2': 'value2',
        'key3': {
            'key3_1': 'value3_1',
            'key3_2': {
                'key3_2_1': 'value3_2_1',
            },
        },
        'key4': {
            'key4_1': 'value4_1',
            'key4_2': 'value4_2',
        },
        cs.CONFIG_DRAFT: {'key4': 'value4'},
    }
    with patch('futurex_openedx_extensions.helpers.tenants.TenantConfig.objects.get') as mock_lms_configs:
        mock_lms_configs.return_value = Mock(lms_configs=lms_configs)
        yield mock_lms_configs


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


@pytest.mark.parametrize(
    'config, path, publish_status, expected_value, expected_path_exist, usecase',
    [
        (
            {'Other': 'some value'},
            'LMS_BASE', tenants.ConfigPublishStatus.DRAFT_THEN_PUBLISHED, None, False,
            'Key missing in both draft and published config, path exist should be False with value None'
        ),
        (
            {'Other': 'some value', 'LMS_BASE': None},
            'LMS_BASE', tenants.ConfigPublishStatus.DRAFT_THEN_PUBLISHED, None, True,
            'Only root config contains value as None, path exist should be True with value None'
        ),
        (
            {'LMS_BASE': 'example.com'},
            'LMS_BASE', tenants.ConfigPublishStatus.DRAFT_THEN_PUBLISHED, 'example.com', True,
            'Retrieve from published config, when draft does not exist (default behavior)'
        ),
        (
            {'theme': {'colors': {'primary': 'blue'}}},
            'theme.colors.primary', tenants.ConfigPublishStatus.DRAFT_THEN_PUBLISHED, 'blue', True,
            'Retrieve from nested published config, when draft does not exist'
        ),
        (
            {'LMS_BASE': 'example.com', 'config_draft': {'LMS_BASE': 'draft.example.com'}},
            'LMS_BASE', tenants.ConfigPublishStatus.DRAFT_THEN_PUBLISHED, 'draft.example.com', True,
            'Retrieve from draft config when both published and draft exist'
        ),
        (
            {'LMS_BASE': 'example.com', 'config_draft': {'LMS_BASE': 'draft.example.com'}},
            'LMS_BASE', tenants.ConfigPublishStatus.ONLY_PUBLISHED, 'example.com', True,
            'Retrieve from published config when published_only=True'
        ),
        (
            {'LMS_BASE': 'example.com', 'config_draft': {'LMS_BASE': 'draft.example.com'}},
            'LMS_BASE', tenants.ConfigPublishStatus.ONLY_DRAFT, 'draft.example.com', True,
            'Retrieve from draft config when draft_only=True',
        ),
        (
            {'LMS_BASE': 'example.com', 'config_draft': {'LMS_BASE': None}},
            'LMS_BASE', tenants.ConfigPublishStatus.ONLY_DRAFT, None, True,
            'Retrieve from draft config when draft_only=True even if value is None with path_exist should be True'
        ),
        (
            {'LMS_BASE': 'example.com', 'config_draft': {'LMS_BASE': ''}},
            'LMS_BASE', tenants.ConfigPublishStatus.ONLY_DRAFT, '', True,
            'Retrieve from draft config when draft_only=True even if value is empty with path_exist should be True'
        ),
        (
            {'LMS_BASE': 'example.com', 'config_draft': {}},
            'LMS_BASE', tenants.ConfigPublishStatus.ONLY_DRAFT, None, False,
            'Key exists only in published and draft_only=True, retrieve from the draft config'
            'with path_exist=False and value=None'
        ),
        (
            {'LMS_BASE': 'example.com', 'config_draft': {}},
            'LMS_BASE', tenants.ConfigPublishStatus.DRAFT_THEN_PUBLISHED, 'example.com', True,
            'Key missing in draft but present in published (fallback works)'
        ),
        (
            {'config_draft': {'LMS_BASE': 'draft.example.com'}},
            'LMS_BASE', tenants.ConfigPublishStatus.ONLY_PUBLISHED, None, False,
            'Key exists only in draft and published_only=True is set'
        ),
        (
            None,
            'LMS_BASE', tenants.ConfigPublishStatus.DRAFT_THEN_PUBLISHED, None, False,
            'Config is None, should return None'
        ),
        (
            {},
            'LMS_BASE', tenants.ConfigPublishStatus.DRAFT_THEN_PUBLISHED, None, False,
            'Config is an empty dictionary, should return None'
        ),
    ]
)
def test_get_tenant_config_value(
    config, path, publish_status, expected_value, expected_path_exist, usecase,
):  # pylint: disable=too-many-arguments
    """Test get_tenant_config_value"""
    path_exist, value = tenants.get_tenant_config_value(config, path, publish_status=publish_status)
    assert value == expected_value, f'Failed usecase: {usecase}'
    assert path_exist == expected_path_exist, f'Failed usecase: {usecase}'


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


@patch('futurex_openedx_extensions.helpers.tenants.get_tenant_readable_lms_config')
@patch('futurex_openedx_extensions.helpers.tenants.get_config_access_control')
def test_get_tenant_config_depends_on_published_only(_, mocked_get_lms_config):
    """Verify that get_tenant_config loads lms_configs correctly, according to the published_only argument."""
    for published_only in [True, False]:
        tenants.get_tenant_config(1, ['some_key'], published_only=published_only)
        mocked_get_lms_config.assert_called_with(1, __skip_cache=not published_only)
        mocked_get_lms_config.reset_mock()


@pytest.mark.django_db
def test_get_draft_tenant_config(base_data):  # pylint: disable=unused-argument
    """Test get_draft_tenant_config"""
    ConfigAccessControl.objects.create(key_name='facebook_link', path='theme_v2.links.facebook')
    assert tenants.get_draft_tenant_config(tenant_id=1) == {
        'facebook_link': {
            'published_value': 'facebook.com',
            'draft_value': 'draft.facebook.com'
        }
    }


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.tenants.TenantConfig.objects.filter')
@patch('futurex_openedx_extensions.helpers.tenants.annotate_queryset_for_update_draft_config')
@patch('futurex_openedx_extensions.helpers.tenants.apply_json_merge_for_update_draft_config')
def test_update_draft_tenant_config(mock_update_draft_json_merge, mock_annotate_queryset, mock_filter):
    """Test the update_draft_tenant_config function for both successful and unsuccessful updates."""
    tenant_id = 1
    key_path = 'some_key_path'
    current_value = 'current_value'
    new_value = 'new_value'
    reset = False

    mock_filter.return_value.exists.return_value = True
    mock_filter.return_value = TenantConfig.objects.filter(id=tenant_id)
    mock_annotate_queryset.return_value = mock_filter.return_value
    mock_update_draft_json_merge.return_value = MagicMock()
    tenants.update_draft_tenant_config(
        tenant_id=1,
        key_path=key_path,
        current_value=current_value,
        new_value=new_value,
        reset=reset,
    )
    mock_annotate_queryset.assert_called_with(mock_filter.return_value, key_path)
    mock_update_draft_json_merge.assert_called_once_with(F('lms_configs'), key_path, new_value, reset)
    mock_filter.return_value.filter.return_value.update.assert_called_once()

    mock_filter.return_value.filter.return_value.update.return_value = 0
    with pytest.raises(FXCodedException) as exc_info:
        tenants.update_draft_tenant_config(
            tenant_id=tenant_id,
            key_path=key_path,
            current_value=current_value,
            new_value=new_value,
            reset=reset,
        )
    assert str(exc_info.value) == (
        'Failed to update config for tenant 1. '
        'Key path may not exist or current value mismatch.'
    )


@pytest.mark.django_db
def test_delete_draft_tenant_config():
    """Test delete_draft_tenant_config"""
    tenant = TenantConfig.objects.get(id=1)
    assert tenant.lms_configs['config_draft'] != {}
    tenants.delete_draft_tenant_config(tenant_id=1)
    tenant.refresh_from_db()
    assert tenant.lms_configs['config_draft'] == {}


@pytest.mark.django_db
def test_delete_draft_tenant_clears_related_cache(base_data, cache_testing):  # pylint: disable=unused-argument
    """Verify that delete_draft_tenant_config clears the related cache."""
    new_tenant = TenantConfig.objects.create(external_key='new_tenant', lms_configs={
        'keep_this': 'value', cs.CONFIG_DRAFT: {'should-be-removed': 'value'}
    })
    cache_name = tenants.cache_name_tenant_readable_lms_configs(new_tenant.id)

    cache.set(cache_name, {'data': new_tenant.lms_configs})
    assert cache.get(cache_name) is not None
    assert cache.get(cache_name)['data'] == new_tenant.lms_configs

    tenants.delete_draft_tenant_config(tenant_id=new_tenant.id)
    assert cache.get(cache_name) is not None
    assert cache.get(cache_name)['data'] == {'keep_this': 'value', cs.CONFIG_DRAFT: {}}


@pytest.mark.parametrize('tenant_exists, merge_result, expected_exception, usecase', [
    (False, None, 'Tenant with ID 123 not found.', 'Tenant does not exist'),
    (True, 0, 'Failed to publish config for tenant 123.', 'Merge function returns 0 (publish failed)'),
    (True, 1, None, 'Successful publish'),
])
@patch('futurex_openedx_extensions.helpers.tenants.TenantConfig.objects.filter')
@patch('futurex_openedx_extensions.helpers.tenants.apply_json_merge_for_publish_draft_config')
def test_publish_tenant_config(
    mock_json_merge, mock_tenant_filter, tenant_exists, merge_result, expected_exception, usecase
):  # pylint: disable=too-many-arguments
    """Test publish_tenant_config"""
    tenant_id = 123
    mock_queryset = MagicMock()
    mock_queryset.exists.return_value = tenant_exists
    mock_tenant_filter.return_value = mock_queryset
    mock_json_merge.return_value = merge_result

    if expected_exception:
        with pytest.raises(FXCodedException) as exc_info:
            tenants.publish_tenant_config(tenant_id)
        assert str(exc_info.value) == expected_exception, f'Unexpected exception message for case: {usecase}'
    else:
        tenants.publish_tenant_config(tenant_id)
        mock_json_merge.assert_called_once_with(mock_queryset)


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
        with patch('futurex_openedx_extensions.helpers.tenants.get_tenant_config') as mock_get_tenant_config:
            tenants.get_config_current_request(keys=['testing_key'])

    mock_get_tenant_config.assert_called_once_with(
        tenant_id=1,
        keys=['testing_key'],
        published_only=expected_published_only,
    )


@pytest.mark.django_db
def test_get_config_access_control():
    """Verify get_config_access_control function."""
    assert tenants.get_config_access_control() == {}

    ConfigAccessControl.objects.create(key_name='test_key1', path='test.path.1')
    ConfigAccessControl.objects.create(key_name='test_key2', path='test.path.2')
    result = tenants.get_config_access_control()
    expected = {
        'test_key1': 'test.path.1',
        'test_key2': 'test.path.2',
    }
    assert result == expected, f'Unexpected result: {result}'


@pytest.mark.django_db
@pytest.mark.parametrize('test_use_case, readable_keys, expected_result', [
    (
        'simple existing keys should return as requested',
        {'control_key1': 'key1', 'control_key2': 'key4'},
        {'key1': 'value1', 'key4': {'key4_1': 'value4_1', 'key4_2': 'value4_2'}},
    ),
    (
        'non existing keys should be ignored',
        {'control_key1': 'key1', 'control_keyX': 'keyX'},
        {'key1': 'value1'},
    ),
    (
        'repeating keys is fine',
        {'control_key1': 'key1', 'control_key_repeat': 'key1'},
        {'key1': 'value1'},
    ),
    (
        'only root keys are considered',
        {'control_key4_1': 'key4.key4_1'},
        {'key4': {'key4_1': 'value4_1', 'key4_2': 'value4_2'}},
    ),
    (
        'only root keys are considered in nested request',
        {'control_key4': 'key4', 'control_key4_1': 'key4.key4_1'},
        {'key4': {'key4_1': 'value4_1', 'key4_2': 'value4_2'}},
    ),
])
@patch('futurex_openedx_extensions.helpers.tenants.get_config_access_control')
def test_get_tenant_readable_lms_config_success(
    mock_access_control, lms_configs_mock, test_use_case, readable_keys, expected_result,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that get_tenant_readable_lms_config function."""
    expected_result[cs.CONFIG_DRAFT] = {'key4': 'value4'}
    mock_access_control.return_value = readable_keys
    result = tenants.get_tenant_readable_lms_config(1)

    assert result == expected_result, f'Unexpected result for use-case ({test_use_case}): {result}'


@pytest.mark.django_db
def test_get_tenant_readable_lms_config_tenant_not_found():
    """Verify that get_tenant_readable_lms_config function raises exception when tenant is not found."""
    with pytest.raises(FXCodedException) as exc_info:
        tenants.get_tenant_readable_lms_config(999)
    assert exc_info.value.code == FXExceptionCodes.TENANT_NOT_FOUND.value
    assert str(exc_info.value) == 'Unable to find tenant with id: (999)'
