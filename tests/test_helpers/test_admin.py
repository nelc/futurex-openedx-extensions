"""Tests for the admin helpers."""
from unittest.mock import patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.core.cache import cache
from django.http import Http404, HttpResponseRedirect
from django.test import override_settings
from django.utils.timezone import now
from rest_framework.test import APIRequestFactory

from futurex_openedx_extensions.helpers.admin import (
    CacheInvalidator,
    CacheInvalidatorAdmin,
    ClickhouseQueryAdmin,
    ViewAllowedRolesHistoryAdmin,
)
from futurex_openedx_extensions.helpers.constants import CACHE_NAMES
from futurex_openedx_extensions.helpers.models import ClickhouseQuery, ViewAllowedRoles
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
@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
def test_cache_invalidator_admin_invalidate_cache(cache_invalidator_admin):  # pylint: disable=redefined-outer-name
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
@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
def test_cache_invalidator_admin_changelist_view_context(
    cache_invalidator_admin
):  # pylint: disable=redefined-outer-name
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

    ClickhouseQuery.load_missing_queries.assert_called_once()
    assert isinstance(response, HttpResponseRedirect)
    assert response.url == '/admin/fx_helpers/clickhousequery'
