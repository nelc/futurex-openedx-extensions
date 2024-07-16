"""Tests for models module."""
from unittest.mock import Mock, patch

import pytest
from django.core.exceptions import ValidationError

from futurex_openedx_extensions.helpers.clickhouse_operations import ClickhouseBaseError
from futurex_openedx_extensions.helpers.models import ClickhouseQuery


@pytest.fixture
def sample_clickhouse_query():
    """Return a ClickhouseQuery instance."""
    return ClickhouseQuery(
        scope='course',
        slug='test-query',
        version='v1',
        description='Test query',
        query='SELECT * FROM table',
        params_config={},
        paginated=True,
        enabled=True,
    )


@pytest.fixture
def get_client_mock(settings):
    """Mock clickhouse_get_client."""
    settings.FX_CLICKHOUSE_USER = 'user'
    settings.FX_CLICKHOUSE_PASSWORD = 'password'

    with patch('futurex_openedx_extensions.helpers.clickhouse_operations.clickhouse_get_client') as mocked:
        mocked.return_value = Mock(
            dummy_client=1,
            __enter__=lambda *_: mocked.return_value,
            __exit__=lambda *_: None,
        )
        yield mocked


@pytest.mark.parametrize('sample_data, configured_type, expected_result', [
    ('1', 'int', 1),
    ('1', 'float', 1.0),
    ('1', 'str', '1'),
    ('1', 'list_str', ['1']),
    ('1,2', 'list_str', ['1', '2']),
])
def test_clickhouse_query_str_to_typed_data(sample_data, configured_type, expected_result):
    """Verify that ClickhouseQuery.str_to_typed_data returns correct data."""
    assert ClickhouseQuery.str_to_typed_data(sample_data, configured_type) == expected_result


@pytest.mark.parametrize('sample_data, configured_type', [
    ('today', 'date'),
    ('days,3', 'date'),
    ('2024-12-26', 'date'),
])
def test_clickhouse_query_str_to_typed_data_date_method(sample_data, configured_type):
    """Verify that ClickhouseQuery.str_to_typed_data calls DateMethods for dates and date methods."""
    with patch('futurex_openedx_extensions.helpers.models.DateMethods') as mock_date_methods:
        ClickhouseQuery.str_to_typed_data(sample_data, configured_type)
        mock_date_methods.parse_date_method.assert_called_once_with(sample_data)


def test_clickhouse_query_str_to_typed_data_invalid_type():
    """Verify that ClickhouseQuery.str_to_typed_data raises ValueError for invalid type."""
    with pytest.raises(ValueError) as exc_info:
        ClickhouseQuery.str_to_typed_data('1', 'bad_type')
    assert exc_info.value.args[0] == 'ClickhouseQuery.str_to_typed_data error: invalid param type: bad_type'


@pytest.mark.django_db
def test_clickhouse_query_clean_on_save():
    """Verify that ClickhouseQuery.save calls clean."""
    query = ClickhouseQuery()
    with patch('futurex_openedx_extensions.helpers.models.ClickhouseQuery.clean') as mock_clean:
        query.save()
        mock_clean.assert_called_once()


@pytest.mark.django_db
def test_clickhouse_query_clean_to_lower_strip(
    sample_clickhouse_query, get_client_mock
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that ClickhouseQuery.clean sets slug, scope, version to lower case and strips whitespaces."""
    sample_clickhouse_query.slug = ' Testing-Query '
    sample_clickhouse_query.scope = ' User '
    sample_clickhouse_query.version = ' V2 '
    sample_clickhouse_query.clean()
    assert sample_clickhouse_query.slug == 'testing-query'
    assert sample_clickhouse_query.scope == 'user'
    assert sample_clickhouse_query.version == 'v2'


@pytest.mark.django_db
@pytest.mark.parametrize('bad_slug', [
    'test query',
    'test-special-!',
    'test-no_underscore',
    'test-not-english-عربي',
])
def test_clickhouse_query_clean_slug_pattern(sample_clickhouse_query, bad_slug):  # pylint: disable=redefined-outer-name
    """Verify that ClickhouseQuery.clean raises ValidationError if slug does not match pattern."""
    sample_clickhouse_query.slug = bad_slug
    with pytest.raises(ValidationError) as exc_info:
        sample_clickhouse_query.clean()
    assert exc_info.value.message == \
           f'Invalid slug ({bad_slug}) only lowercase alphanumeric characters and hyphens are allowed'


@pytest.mark.django_db
def test_clickhouse_query_clean_bad_scope(sample_clickhouse_query):  # pylint: disable=redefined-outer-name
    """Verify that ClickhouseQuery.clean raises ValidationError if scope is not in the allowed list."""
    sample_clickhouse_query.scope = 'bad_scope'
    with pytest.raises(ValidationError) as exc_info:
        sample_clickhouse_query.clean()
    assert exc_info.value.message == 'Invalid scope: (bad_scope)'


@pytest.mark.django_db
def test_clickhouse_query_clean_call_validation_if_enabled(
    sample_clickhouse_query
):  # pylint: disable=redefined-outer-name
    """Verify that ClickhouseQuery.clean calls validate_clickhouse_query only if the record is enabled."""
    with patch('futurex_openedx_extensions.helpers.models.ClickhouseQuery.validate_clickhouse_query') as mock_validate:
        sample_clickhouse_query.enabled = False
        sample_clickhouse_query.clean()
        mock_validate.assert_not_called()

        sample_clickhouse_query.enabled = True
        sample_clickhouse_query.clean()
        mock_validate.assert_called_once()


@patch('futurex_openedx_extensions.helpers.models.ClickhouseQuery.fix_param_types')
@patch('futurex_openedx_extensions.helpers.models.ClickhouseQuery.get_sample_params', return_value={'a': 1})
def test_clickhouse_query_validate_clickhouse_query(
    _, mocked_fix_param_types, sample_clickhouse_query, get_client_mock
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that ClickhouseQuery.validate_clickhouse_query calls Clickhouse client."""
    sample_clickhouse_query.validate_clickhouse_query()
    mocked_fix_param_types.assert_called_once_with(params={'a': 1})


@patch('futurex_openedx_extensions.helpers.models.ClickhouseQuery.fix_param_types')
@patch('futurex_openedx_extensions.helpers.models.ClickhouseQuery.get_sample_params')
def test_clickhouse_query_validate_clickhouse_query_invalid_query(
    _, mocked_fix_param_types, sample_clickhouse_query, get_client_mock
):  # pylint: disable=unused-argument, redefined-outer-name
    """Verify that ClickhouseQuery.validate_clickhouse_query raises ValidationError if query is invalid."""
    mocked_fix_param_types.side_effect = ClickhouseBaseError('syntax issue')
    with pytest.raises(ValidationError) as exc_info:
        sample_clickhouse_query.validate_clickhouse_query()
    assert exc_info.value.message == 'Clickhouse Query Error: syntax issue'


@pytest.mark.parametrize('not_allowed_query, expected_error_msg', [
    ('SELECT anythin ends with semicolon;', 'Query must not end with a semicolon'),
    ('Anything does not start with SELECT', 'Query must start with SELECT'),
])
def test_clickhouse_query_validate_clickhouse_query_forbidden_syntax(
    sample_clickhouse_query, get_client_mock, not_allowed_query, expected_error_msg
):  # pylint: disable=unused-argument, redefined-outer-name
    """
    Verify that ClickhouseQuery.validate_clickhouse_query raises ValidationError if query contains forbidden syntax.
    """
    sample_clickhouse_query.query = not_allowed_query
    with pytest.raises(ValidationError) as exc_info:
        sample_clickhouse_query.validate_clickhouse_query()
    assert exc_info.value.message == expected_error_msg


def test_clickhouse_query_get_sample_params(sample_clickhouse_query):  # pylint: disable=redefined-outer-name
    """Verify that ClickhouseQuery.get_sample_params returns correct sample params."""
    sample_clickhouse_query.params_config = {
        'a': {'type': 'int', 'optional': False, 'sample_data': '1'},
        'b': {'type': 'str', 'optional': True, 'sample_data': '2'},
        'c': {'type': 'int', 'optional': True},
        'd': {'type': 'int', 'optional': True, 'sample_data': None},
    }
    assert sample_clickhouse_query.get_sample_params() == {
        '__orgs_of_tenants__': ['org1', 'org2'],
        '__ca_users_of_tenants__': ['user1', 'user2'],
        'a': 1,
        'b': '2',
        'c': None,
        'd': None,
    }


@pytest.mark.parametrize('params_config, expected_error_msg', [
    (
        {'a': {'type': 'bad_type', 'optional': False, 'sample_data': '1'}},
        'ClickhouseQuery.get_sample_params error: Invalid param type: bad_type for param: a',
    ),
    (
        {'a': {'type': 'int', 'optional': False, 'sample_data': None}},
        'ClickhouseQuery.get_sample_params error: No sample data provided for required param: a',
    ),
    (
        {'a': {'type': 'int', 'optional': False, 'sample_data': 1}},
        'ClickhouseQuery.get_sample_params error: Invalid sample data: a. It must be a string regardless of the type',
    ),
])
def test_clickhouse_query_get_sample_params_invalid_configs(
    sample_clickhouse_query, params_config, expected_error_msg
):  # pylint: disable=redefined-outer-name
    """Verify that ClickhouseQuery.get_sample_params raises ValidationError for invalid params."""
    sample_clickhouse_query.params_config = params_config
    with pytest.raises(ValidationError) as exc_info:
        sample_clickhouse_query.get_sample_params()
    assert exc_info.value.message == expected_error_msg


@pytest.mark.django_db
def test_clickhouse_query_get_missing_query_ids():
    """Verify that ClickhouseQuery.get_missing_query_ids returns correct missing query ids."""
    with patch('futurex_openedx_extensions.helpers.models.ClickhouseQuery.validate_clickhouse_query'):
        ClickhouseQuery.objects.create(scope='course', version='v1', slug='query1', enabled=True)
        ClickhouseQuery.objects.create(scope='user', version='v1', slug='query2', enabled=False)

    assert not ClickhouseQuery.get_missing_query_ids([])
    assert ClickhouseQuery.get_missing_query_ids([
        ('user', 'v1', 'query2'), ('user', 'v1', 'query1'),
    ]) == [('user', 'v1', 'query1')]


@pytest.mark.django_db
def test_clickhouse_query_get_query_record():
    """Verify that ClickhouseQuery.get_query_record returns correct query record."""
    with patch('futurex_openedx_extensions.helpers.models.ClickhouseQuery.validate_clickhouse_query'):
        query1 = ClickhouseQuery.objects.create(scope='course', version='v1', slug='query1', enabled=True)
        query2 = ClickhouseQuery.objects.create(scope='user', version='v1', slug='query2', enabled=False)

    assert ClickhouseQuery.get_query_record('course', 'v1', 'query1') == query1
    assert ClickhouseQuery.get_query_record('user', 'v1', 'query2') == query2
    assert ClickhouseQuery.get_query_record('course', 'v1', 'query2') is None


def test_clickhouse_query_get_default_query_ids():
    """Verify that ClickhouseQuery.get_default_query_ids returns correct default query ids."""
    defaults = {
        'default_queries': {
            'course': {
                'v1': {
                    'slug1': {}
                }
            },
            'user': {
                'v1': {
                    'slug2': {}
                }
            },
        },
    }
    with patch('futurex_openedx_extensions.helpers.clickhouse_operations.get_default_queries') as mocked_defaults:
        mocked_defaults.return_value = defaults
        assert ClickhouseQuery.get_default_query_ids() == [
            ('course', 'v1', 'slug1'), ('user', 'v1', 'slug2'),
        ]


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.models.ClickhouseQuery.get_missing_query_ids')
@patch('futurex_openedx_extensions.helpers.clickhouse_operations.get_default_queries')
def test_clickhouse_query_load_missing_queries(mocked_default, mocked_missing):
    """Verify that ClickhouseQuery.load_missing_queries loads missing queries."""
    mocked_default.return_value = {
        'default_queries': {
            'course': {
                'v1': {
                    'slug1': {'query': 'SELECT * FROM table'},
                }
            },
            'user': {
                'v1': {
                    'slug2': {'query': 'SELECT * FROM table'}
                }
            },
        },
    }
    mocked_missing.return_value = [
        ('course', 'v1', 'slug1'), ('user', 'v1', 'slug2'),
    ]

    assert ClickhouseQuery.objects.count() == 0
    with patch('futurex_openedx_extensions.helpers.models.ClickhouseQuery.validate_clickhouse_query'):
        ClickhouseQuery.load_missing_queries()
        assert ClickhouseQuery.objects.count() == 2
        assert ClickhouseQuery.objects.filter(scope='course', version='v1', slug='slug1').exists()
        assert ClickhouseQuery.objects.filter(scope='user', version='v1', slug='slug2').exists()


@patch('futurex_openedx_extensions.helpers.models.ClickhouseQuery.get_missing_query_ids')
@patch('futurex_openedx_extensions.helpers.models.ClickhouseQuery.get_default_query_ids')
def test_clickhouse_query_get_missing_queries_count(mocked_defaults, mocked_missing):
    """Verify that ClickhouseQuery.get_missing_queries_count returns correct count of missing queries."""
    mocked_missing.return_value = ['few', 'queries']
    assert ClickhouseQuery.get_missing_queries_count() == 2
    mocked_defaults.assert_called_once()
    mocked_missing.assert_called_once_with(compared_to=mocked_defaults.return_value)


def test_clickhouse_query_fix_param_types(sample_clickhouse_query):  # pylint: disable=redefined-outer-name
    """Verify that ClickhouseQuery.fix_param_types processes the params correctly"""
    sample_clickhouse_query.params_config = {
        'a': {'type': 'int', 'optional': False},
        'b': {'type': 'str', 'optional': False},
        'c': {'type': 'str', 'optional': True},
    }
    params = {'a': '1', 'b': '2'}
    sample_clickhouse_query.fix_param_types(params)
    assert params == {'a': 1, 'b': '2', 'c': None}


def test_clickhouse_query_fix_param_types_disabled(sample_clickhouse_query):  # pylint: disable=redefined-outer-name):
    """Verify that ClickhouseQuery.fix_param_types raises ValidationError if query is disabled."""
    sample_clickhouse_query.enabled = False
    with pytest.raises(ValidationError) as exc_info:
        sample_clickhouse_query.fix_param_types({})
    assert exc_info.value.message == \
           'ClickhouseQuery.fix_param_types error on (course.v1.test-query): Trying to use a disabled query'


def test_clickhouse_query_fix_param_types_missing_param(
    sample_clickhouse_query
):  # pylint: disable=redefined-outer-name
    """Verify that ClickhouseQuery.fix_param_types raises ValidationError for missing required params."""
    sample_clickhouse_query.params_config = {
        'a': {'type': 'int', 'optional': False},
        'b': {'type': 'str', 'optional': False},
    }
    with pytest.raises(ValidationError) as exc_info:
        sample_clickhouse_query.fix_param_types({'a': 1})
    assert exc_info.value.message == \
           'ClickhouseQuery.fix_param_types error on (course.v1.test-query): Missing required param: b'


def test_clickhouse_query_fix_param_types_extra_param_allowed(
    sample_clickhouse_query,
):  # pylint: disable=redefined-outer-name
    """Verify that ClickhouseQuery.parse_query allows extra params that are not in the config."""
    sample_clickhouse_query.params_config = {
        'a': {'type': 'int', 'optional': False},
    }
    params = {'a': '1', 'extra_param': {'any-type': 'should not be changed!!!'}}
    sample_clickhouse_query.fix_param_types(params)
    assert params == {'a': 1, 'extra_param': {'any-type': 'should not be changed!!!'}}
