"""Test views for the dashboard app - clickhouse"""
# pylint: disable=duplicate-code
import json
from unittest.mock import Mock

import ddt
from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage
from django.urls import resolve
from rest_framework import status as http_status

from futurex_openedx_extensions.dashboard.views.clickhouse import ClickhouseQueryView
from futurex_openedx_extensions.helpers import clickhouse_operations as ch
from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers.pagination import DefaultPagination
from futurex_openedx_extensions.helpers.permissions import FXHasTenantCourseAccess
from tests.test_dashboard.test_mixins import BaseTestViewMixin, MockPatcherMixin


class MockClickhouseQuery:
    """Mock ClickhouseQuery"""
    def __init__(
        self, query, slug, version, scope, enabled, params_config, paginated
    ):  # pylint: disable=too-many-arguments
        self.query = query
        self.slug = slug
        self.version = version
        self.scope = scope
        self.enabled = enabled
        self.params_config = params_config
        self.paginated = paginated

    def fix_param_types(self, *args, **kwargs):
        """Mock parse_query"""
        return self.query

    @classmethod
    def get_query_record(cls, scope, version, slug):
        """Mock get_query_record"""
        if slug == 'non-existing-query':
            return None

        paginated = not slug.endswith('-nop')

        enabled = 'disabled' not in slug

        query = 'SELECT * FROM table'
        if 'ca-users' in slug:
            query += f' WHERE user_id IN {{{{{cs.CLICKHOUSE_FX_BUILTIN_CA_USERS_OF_TENANTS}}}}}'

        return MockClickhouseQuery(
            query=query,
            slug=slug,
            version=version,
            scope=scope,
            enabled=enabled,
            params_config={},
            paginated=paginated,
        )


@ddt.ddt
class TestClickhouseQueryView(MockPatcherMixin, BaseTestViewMixin):
    """Tests for ClickhouseQueryView"""
    VIEW_NAME = 'fx_dashboard:clickhouse-query'

    patching_config = {
        'get_query_record': ('futurex_openedx_extensions.dashboard.views.clickhouse.ClickhouseQuery.get_query_record', {
            'side_effect': MockClickhouseQuery.get_query_record,
        }),
        'parse_query': ('futurex_openedx_extensions.dashboard.views.clickhouse.ClickhouseQuery.fix_param_types', {
            'side_effect': MockClickhouseQuery.fix_param_types,
        }),
        'get_client': ('futurex_openedx_extensions.helpers.clickhouse_operations.get_client', {}),
        'execute_query': ('futurex_openedx_extensions.helpers.clickhouse_operations.execute_query', {
            'return_value': (100, 2, Mock(column_names=['col_name'], result_rows=[[1]])),
        }),
        'get_usernames_with_access_roles': (
            'futurex_openedx_extensions.dashboard.views.clickhouse.get_usernames_with_access_roles',
            {'return_value': []}
        ),
    }

    def setUp(self):
        """Setup"""
        super().setUp()
        self.url_args = ['course', 'test-query']

    def test_permission_classes(self):
        """Verify that the view has the correct permission classes"""
        view_func, _, _ = resolve(self.url)
        view_class = view_func.view_class
        self.assertEqual(view_class.permission_classes, [FXHasTenantCourseAccess])

    def test_unauthorized(self):
        """Verify that the view returns 403 when the user is not authenticated"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_success(self):
        """Verify that the view returns the correct response"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(json.loads(response.content), {
            'count': 100,
            'next': 'http://testserver/api/fx/query/v1/course/test-query/?page=2',
            'previous': None,
            'results': [{'col_name': 1}]
        })
        self.mocks['get_usernames_with_access_roles'].assert_not_called()

    def test_success_no_pagination(self):
        """Verify that the view returns the correct response when pagination is disabled"""
        self.url_args = ['course', 'test-query-nop']

        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(json.loads(response.content), [{'col_name': 1}])
        self.mocks['get_usernames_with_access_roles'].assert_not_called()

    def test_success_ca_users_needed(self):
        """Verify that the view gets the CA users when the query needs them"""
        self.url_args = ['course', 'test-query-ca-users-nop']
        all_orgs = ['org1', 'org2', 'org3', 'org8', 'org4', 'org5']

        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(json.loads(response.content), [{'col_name': 1}])
        self.mocks['get_usernames_with_access_roles'].assert_called_once_with(all_orgs)

    @ddt.data(
        ('?page=3', 5, '?page=5'),
        ('?page=3', 1, '?page=1'),
        ('?page=3&page_size=33', 5, '?page_size=33&page=5'),
        ('?page=3&whatever=any&page_size=33', 5, '?whatever=any&page_size=33&page=5'),
        ('?page=3&whatever=any&page_size=33', None, None),
    )
    @ddt.unpack
    def test_get_page_url_with_page(self, param_string, new_page_no, expected_result):
        """Verify that get_page_url_with_page returns the correct URL"""
        url = f'http://testserver/api/fx/query/v1/course/test-query/{param_string}'

        if expected_result:
            expected_result = f'http://testserver/api/fx/query/v1/course/test-query/{expected_result}'

        self.assertEqual(ClickhouseQueryView.get_page_url_with_page(url, new_page_no), expected_result)

    @ddt.data(
        ({}, True, (1, DefaultPagination.page_size)),
        ({'page': '4'}, True, (4, DefaultPagination.page_size)),
        ({'page': None}, True, (1, DefaultPagination.page_size)),
        ({'page': '2', 'page_size': '23'}, True, (2, 23)),
        ({'page_size': '23'}, True, (1, 23)),
        ({}, False, (None, DefaultPagination.page_size)),
        ({'page': '4'}, False, (None, DefaultPagination.page_size)),
        ({'page': None}, False, (None, DefaultPagination.page_size)),
        ({'page': '2', 'page_size': '23'}, False, (None, 23)),
        ({'page_size': '23'}, False, (None, 23)),
    )
    @ddt.unpack
    def test_pop_out_page_params(self, params, paginated, expected_result):
        """Verify that pop_out_page_params returns the correct page number and page size"""
        self.assertEqual(ClickhouseQueryView.pop_out_page_params(params, paginated), expected_result)

    def _assert_not_ok_response(self, status_code, reason):
        """Helper to assert that the response is not OK"""
        self.login_user(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status_code)
        self.assertEqual(response.data, {'details': {}, 'reason': reason})

    def test_query_does_no_exist(self):
        """Verify that the view returns 404 when the query does not exist"""
        self.url_args = ['course', 'non-existing-query']
        self._assert_not_ok_response(
            status_code=404,
            reason='Query not found course.v1.non-existing-query'
        )

    def test_query_not_enabled(self):
        """Verify that the view returns 400 when the query is not enabled"""
        self.url_args = ['course', 'test-query-disabled']
        self._assert_not_ok_response(
            status_code=400,
            reason='Query is disabled course.v1.test-query-disabled'
        )

    def test_empty_page(self):
        """Verify that the view returns 404 when the requested page is empty"""
        self.mocks['execute_query'].side_effect = EmptyPage('wrong page number!')
        self._assert_not_ok_response(
            status_code=404,
            reason='wrong page number!'
        )

    @ddt.data(
        ch.ClickhouseClientNotConfiguredError,
        ch.ClickhouseClientConnectionError,
    )
    def test_clickhouse_connection_error(self, side_effect):
        """Verify that the view returns 503 when there is a Clickhouse connection error"""
        self.mocks['get_client'].side_effect = side_effect('connection issue with clickhouse')
        self._assert_not_ok_response(
            status_code=503,
            reason='connection issue with clickhouse'
        )

    @ddt.data(
        ch.ClickhouseBaseError,
        ValueError,
        ValidationError,
    )
    def test_bad_use_of_arguments(self, side_effect):
        """Verify that the view returns 400 when there is a bad use of arguments"""
        self.mocks['execute_query'].side_effect = side_effect('bad use of arguments')
        self._assert_not_ok_response(
            status_code=400,
            reason='bad use of arguments'
        )
