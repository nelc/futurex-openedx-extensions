"""Tests for the admin helpers."""
from unittest.mock import Mock, patch

import pytest
from django import forms
from django.contrib.admin.sites import AdminSite
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseRedirect
from django.utils.timezone import now
from django_mysql.models import QuerySet
from openedx.core.lib.api.authentication import BearerAuthentication
from rest_framework.test import APIRequestFactory

from futurex_openedx_extensions.helpers.admin import (
    CacheInvalidator,
    CacheInvalidatorAdmin,
    ClickhouseQueryAdmin,
    ConfigAccessControlForm,
    ViewAllowedRolesHistoryAdmin,
    ViewAllowedRolesModelForm,
    ViewUserMappingHistoryAdmin,
    ViewUserMappingModelForm,
    YesNoFilter,
)
from futurex_openedx_extensions.helpers.constants import CACHE_NAMES
from futurex_openedx_extensions.helpers.models import ClickhouseQuery, ViewAllowedRoles, ViewUserMapping
from tests.fixture_helpers import set_user


@pytest.fixture
def admin_site():
    """Fixture for the admin site."""
    return AdminSite()


@pytest.fixture
def view_allowed_roles_admin(admin_site):  # pylint: disable=redefined-outer-name
    """Fixture for the ViewAllowedRolesHistoryAdmin."""
    return ViewAllowedRolesHistoryAdmin(ViewAllowedRoles, admin_site)


@pytest.fixture
def cache_invalidator_admin(admin_site):  # pylint: disable=redefined-outer-name
    """Fixture for the CacheInvalidatorAdmin."""
    return CacheInvalidatorAdmin(CacheInvalidator, admin_site)


@pytest.fixture
def clickhouse_query_admin(admin_site):  # pylint: disable=redefined-outer-name
    """Fixture for the ClickhouseQueryAdmin."""
    return ClickhouseQueryAdmin(ClickhouseQuery, admin_site)


@pytest.fixture
def mock_clickhousequery_methods():
    """Fixture to mock the ClickhouseQuery methods."""
    with patch(
        'futurex_openedx_extensions.helpers.admin.ClickhouseQuery.get_missing_queries_count',
        return_value=5
    ):
        with patch('futurex_openedx_extensions.helpers.admin.ClickhouseQuery.load_missing_queries'):
            yield


@pytest.fixture
def mock_get_fx_view_with_roles():
    """Fixture to mock the get_fx_view_with_roles method."""
    with patch(
        'futurex_openedx_extensions.helpers.admin.get_fx_view_with_roles',
        return_value={
            '_all_view_names': {
                'view_name9': Mock(authentication_classes=[BearerAuthentication]),
                'view_name2': Mock(authentication_classes=[BearerAuthentication]),
                'view_no_auth_classes': Mock(),
                'view_no_bearer_class': Mock(authentication_classes=[]),
            },
        },
    ) as mocked_result:
        del mocked_result.return_value['_all_view_names']['view_no_auth_classes'].authentication_classes
        yield


def test_view_allowed_roles_admin_main_settings(view_allowed_roles_admin):  # pylint: disable=redefined-outer-name
    """Verify the main settings of the ViewAllowedRolesHistoryAdmin."""
    assert view_allowed_roles_admin.list_display == ('view_name', 'view_description', 'allowed_role')


def test_cache_invalidator_admin_get_urls(cache_invalidator_admin):  # pylint: disable=redefined-outer-name
    """Verify the get_urls method of the CacheInvalidatorAdmin."""
    expected_config = {
        'fx_helpers_cacheinvalidator_changelist': {
            'callback': CacheInvalidatorAdmin.changelist_view,
        },
        'fx_helpers_cacheinvalidator_invalidate_cache': {
            'callback': CacheInvalidatorAdmin.invalidate_cache,
        },
    }
    urls = cache_invalidator_admin.get_urls()
    assert len(urls) == 2
    for url in urls:
        assert url.name in expected_config
        assert url.callback.__name__ == expected_config[url.name]['callback'].__name__


@pytest.mark.django_db
def test_cache_invalidator_admin_changelist_view(
    base_data, cache_invalidator_admin
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify the changelist_view method of the CacheInvalidatorAdmin."""
    request = APIRequestFactory().get('/admin/fx_helpers/cacheinvalidator/')
    set_user(request, 1)
    response = cache_invalidator_admin.changelist_view(request)

    assert response.status_code == 200
    assert 'fx_cache_info' in response.context_data


@pytest.mark.django_db
def test_cache_invalidator_admin_invalidate_cache(
    cache_invalidator_admin, cache_testing
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify the invalidate_cache method of the CacheInvalidatorAdmin."""
    cache_name = list(CACHE_NAMES.keys())[0]
    cache.set(cache_name, {
        'created_datetime': now(),
        'expiry_datetime': now(),
        'data': {}
    })

    request = APIRequestFactory().get(f'/admin/fx_helpers/cacheinvalidator/invalidate_{cache_name}/')
    assert cache.get(cache_name) is not None
    response = cache_invalidator_admin.invalidate_cache(request, cache_name)

    assert response.status_code == 302
    assert cache.get(cache_name) is None


@pytest.mark.django_db
def test_cache_invalidator_admin_invalidate_cache_invalid_name(
    cache_invalidator_admin
):  # pylint: disable=redefined-outer-name
    """Verify the invalidate_cache method of the CacheInvalidatorAdmin with invalid cache name."""
    request = APIRequestFactory().get('/admin/fx_helpers/cacheinvalidator/invalidate_invalid_name/')
    with pytest.raises(Http404) as exc_info:
        cache_invalidator_admin.invalidate_cache(request, 'invalid_name')
    assert 'Cache name invalid_name not found' in str(exc_info.value)


@pytest.mark.django_db
def test_cache_invalidator_admin_changelist_view_context(
    cache_invalidator_admin, cache_testing
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify the context of the changelist_view method of the CacheInvalidatorAdmin."""
    request = APIRequestFactory().get('/admin/fx_helpers/cacheinvalidator/')
    set_user(request, 1)
    cache_name = list(CACHE_NAMES.keys())[0]
    cache.set(cache_name, {
        'created_datetime': now(),
        'expiry_datetime': now(),
        'data': {'key': 'value'}
    })

    response = cache_invalidator_admin.changelist_view(request)

    assert response.status_code == 200
    cache_info = response.context_data['fx_cache_info']
    assert cache_name in cache_info
    assert cache_info[cache_name]['available'] == 'Yes'
    cache.set(cache_name, None)


@pytest.mark.django_db
def test_clickhouse_query_admin_changelist_view(
    base_data, clickhouse_query_admin, mock_clickhousequery_methods
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify the changelist_view method of the ClickhouseQueryAdmin."""
    request = APIRequestFactory().get('/admin/fx_helpers/clickhousequery/')
    set_user(request, 1)

    response = clickhouse_query_admin.changelist_view(request)

    assert response.status_code == 200
    assert 'fx_missing_queries_count' in response.context_data
    assert response.context_data['fx_missing_queries_count'] == 5


def test_clickhouse_query_admin_get_urls(clickhouse_query_admin):  # pylint: disable=redefined-outer-name
    """Verify the get_urls method of the ClickhouseQueryAdmin."""
    urls = clickhouse_query_admin.get_urls()
    url_names = [url.name for url in urls]

    assert 'fx_helpers_clickhousequery_load_missing_queries' in url_names


@pytest.mark.django_db
def test_clickhouse_query_admin_load_missing_queries(
    base_data, clickhouse_query_admin, mock_clickhousequery_methods
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify the load_missing_queries method of the ClickhouseQueryAdmin."""
    request = APIRequestFactory().get('/admin/fx_helpers/clickhousequery/load_missing_queries/')
    set_user(request, 1)

    response = clickhouse_query_admin.load_missing_queries(request)

    ClickhouseQuery.load_missing_queries.assert_called_once()  # pylint: disable=no-member
    assert isinstance(response, HttpResponseRedirect)
    assert response.url == '/admin/fx_helpers/clickhousequery'


@patch('futurex_openedx_extensions.helpers.admin.CourseAccessRoleForm')
def test_view_allowed_roles_model_form(
    mock_course_access_form, mock_get_fx_view_with_roles,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify the ViewAllowedRolesModelForm model form."""
    mock_course_access_form.COURSE_ACCESS_ROLES = [('role99', 'role99'), ('role44', 'role44')]

    form = ViewAllowedRolesModelForm()

    assert isinstance(form.fields['view_name'], forms.TypedChoiceField)
    assert form.fields['view_name'].choices == [
        ('view_name2', 'view_name2'),
        ('view_name9', 'view_name9'),
        ('view_no_auth_classes', 'view_no_auth_classes'),
        ('view_no_bearer_class', 'view_no_bearer_class'),
    ]
    assert isinstance(form.fields['allowed_role'], forms.TypedChoiceField)
    assert form.fields['allowed_role'].choices == mock_course_access_form.COURSE_ACCESS_ROLES


@pytest.mark.django_db
def test_yes_no_filter_lookups():
    """Verify the lookups method of the YesNoFilter."""
    filter_instance = YesNoFilter(request=None, params={}, model=None, model_admin=None)
    expected_lookups = [('yes', 'Yes'), ('no', 'No')]
    assert filter_instance.lookups(None, None) == expected_lookups


@pytest.mark.django_db
@pytest.mark.parametrize('not_yet_set_must_be_replaced, filter_called, expected_flag', [
    ('yes', True, True),
    ('no', True, False),
    ('Yes', False, None),
    ('NO', False, None),
    ('something', False, None),
    (None, False, None),
])
def test_yes_no_filter_queryset(not_yet_set_must_be_replaced, filter_called, expected_flag):
    """Verify the queryset method of the YesNoFilter."""
    filter_instance = YesNoFilter(
        request=None,
        params={'not_yet_set_must_be_replaced': not_yet_set_must_be_replaced},
        model=None,
        model_admin=None,
    )
    mock_queryset = Mock(spec=QuerySet)
    mock_queryset.filter.return_value = 'filtered_queryset'
    result = filter_instance.queryset(None, mock_queryset)
    if filter_called:
        mock_queryset.filter.assert_called_once_with(not_yet_set_must_be_replaced=expected_flag)
        assert result == 'filtered_queryset'
    else:
        mock_queryset.filter.assert_not_called()
        assert result == mock_queryset


def test_view_user_mapping_model_form_initialization(
    mock_get_fx_view_with_roles,
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify the initialization of the ViewUserMappingModelForm."""
    form = ViewUserMappingModelForm()

    assert isinstance(form.fields['view_name'], forms.TypedChoiceField)
    assert form.fields['view_name'].choices == [('view_name2', 'view_name2'), ('view_name9', 'view_name9')]


@pytest.mark.django_db
@pytest.mark.parametrize('attribute_name', [
    'is_user_active', 'is_user_system_staff', 'has_access_role', 'usable',
])
def test_view_user_mapping_model_form_extra_attributes(attribute_name):
    """Verify the extra attributes of the ViewUserMappingModelForm."""
    obj = Mock(**{
        'spec': ViewUserMapping,
        f'get_{attribute_name}': Mock(return_value='testing-attribute'),
    })

    admin = ViewUserMappingHistoryAdmin(model=ViewUserMapping, admin_site=Mock())
    attribute_to_test = getattr(admin, attribute_name)
    assert attribute_to_test(obj) == 'testing-attribute'
    assert attribute_to_test.short_description == attribute_name.replace('_', ' ').title()
    assert attribute_to_test.boolean is True
    assert attribute_to_test.admin_order_field == attribute_name


@pytest.mark.django_db
@pytest.mark.parametrize(
    'default_config, input_path, expected_error, usecase',
    [
        (
            {'themev2': {'footer': {'linkedin_url': 'https://linkedin.com'}}},
            'themev2.footer.linkedin_url',
            None,
            'Valid path should pass without errors.'
        ),
        (
            {'themev2': {'footer': {'linkedin_url': 'https://linkedin.com'}}},
            'themev2. footer.linkedin_url',
            'Key path must not contain spaces.',
            'key_path should not contain any spaces.'
        ),
        (
            {'themev2': {'footer': {}}},
            'invalid_start.path',
            'Invalid path: "invalid_start" does not exist in the default config.',
            'Invalid key should raise a proper error.'
        ),
        (
            {'themev2': {'footer': {}}},
            'themev2.footer.linkedin_url',
            'Path "themev2.footer" found in default config but unable to find "linkedin_url" in "themev2.footer"',
            'Partial path match but missing final key should show accurate error.'
        ),
        (
            {'themev2': {'header': {}}},
            'themev2.footer',
            'Path "themev2" found in default config but unable to find "footer" in "themev2"',
            'Valid parent but invalid child key should provide informative feedback.'
        ),
        (
            {'themev2': {'header-color': {}}},
            'themev2.header-color',
            'Key path parts must include only alphanumeric characters and underscores.',
            'Only alphanumeric characters and underscores are allowed in the path parts.'
        ),
        (
            {'themev2': {'header': {}}},
            'themev2.header.',
            'Key path must not contain empty parts. It should not have leading, trailing, or double dots.',
            'Leading, trailing, and double dots should not be in the path.'
        ),
        (
            {'themev2': {'header': {}}},
            '.themev2.header',
            'Key path must not contain empty parts. It should not have leading, trailing, or double dots.',
            'Leading, trailing, and double dots should not be in the path.'
        ),
        (
            {'themev2': {'header': {}}},
            'themev2..header',
            'Key path must not contain empty parts. It should not have leading, trailing, or double dots.',
            'Leading, trailing, and double dots should not be in the path.'
        ),
        (
            {'themev2': {'whatever': {}}},
            None,
            'This field is required.',
            'Key path is required. It cannot be None or empty.'
        ),
    ]
)
@patch('futurex_openedx_extensions.helpers.admin.TenantConfig.objects.get')
def test_validate_path(mock_get, default_config, input_path, expected_error, usecase):
    """Test clean_path validation with various path inputs and descriptive use cases."""
    mock_get.return_value = Mock(lms_configs=default_config)
    form_data = {
        'path': input_path,
        'key_name': 'test_key',
        'writable': True,
        'key_type': 'string'
    }
    form = ConfigAccessControlForm(data=form_data)
    form.is_valid()

    if expected_error:
        assert expected_error in form.errors.get('path', []), usecase
    else:
        assert form.errors == {}, usecase


@pytest.mark.django_db
@pytest.mark.parametrize(
    'path, mirror_path, extra_mirror_path, expected_error_field, usecase',
    [
        ('a.b.c', 'a.b.c', None, 'mirror_path', 'invalid: mirror_path is exactly same as path'),
        ('a.b.c', 'a.b', None, 'mirror_path', 'invalid: mirror_path is a prefix (ancestor) of path'),
        ('a.b.c', 'a', None, 'mirror_path', 'invalid: mirror_path is a prefix (ancestor) of path'),
        ('a.b', 'a.b.c', None, 'mirror_path', 'invalid: mirror_path is a descendant of path'),
        ('a.b.c', None, 'a.b.c.d', 'extra_mirror_path', 'invalid: extra_mirror_path is a descendant of path'),
        ('a.b', None, 'a', 'extra_mirror_path', 'invalid: extra_mirror_path is a prefix (ancestor) of path'),
        ('a.b.c', None, 'a.z', None, 'valid: extra_mirror_path is unrelated to path'),
        ('a.b.c', None, 'a.c', None, 'valid: extra_mirror_path is unrelated to path'),
        ('a.b.c', None, 'a.b.x', None, 'valid: extra_mirror_path is unrelated to path'),
    ]
)
@patch('futurex_openedx_extensions.helpers.admin.TenantConfig.objects.get')
def test_config_access_control_path_overlap(
    mock_get, path, mirror_path, extra_mirror_path, expected_error_field, usecase
):  # pylint: disable=too-many-arguments
    """
    Tests overlapping logic in ConfigAccessControlForm.

    Validates that `mirror_path` and `extra_mirror_path` do not overlap with `path` in ways that would
    violate configuration structure. Covers:
      - Exact match
      - Prefix (ancestor/descendant)
      - Unrelated (valid)
    """
    mock_get.return_value.lms_configs = {
        'a': {
            'b': {
                'c': {
                    'd': 'some_value'
                },
                'x': 'value'
            },
            'z': 'value',
            'c': 'value'
        }
    }

    data = {'path': path, 'key_name': 'something', 'key_type': 'dict'}
    if mirror_path is not None:
        data['mirror_path'] = mirror_path
    if extra_mirror_path is not None:
        data['extra_mirror_path'] = extra_mirror_path

    form = ConfigAccessControlForm(data=data)
    is_valid = form.is_valid()

    if expected_error_field:
        assert not is_valid, f'Expected form to be invalid for: {usecase}'
        assert expected_error_field in form.errors, f'Expected error in: {expected_error_field} for: {usecase}'
        assert 'should not overlap' in form.errors[expected_error_field][0]
    else:
        assert is_valid, f'Expected form to be valid for: {usecase}'


@pytest.mark.django_db
def test_config_access_control_form_clean_path_default_config_not_exist():
    """Test clean_path validation when default config does not exist."""
    form = ConfigAccessControlForm(data={'path': 'does.not.matter', 'key_name': 'dummy'})
    with pytest.raises(ValidationError) as exc_info:
        form.full_clean()
    assert str(exc_info.value) == "[\'Unable to update path as default TenantConfig not found.\']"


def test_validate_path_raises_value_error_if_default_config_none():
    """
    Ensure that validate_path raises a ValueError if default_config is not set.

    This simulates a scenario where full_clean was not called successfully
    and default_config remains None.
    """
    form = ConfigAccessControlForm(data={'path': 'a.b.c'})
    form.default_config = None

    with pytest.raises(ValueError, match='default_config must be set before using it.'):
        form.validate_path('a.b.c')
