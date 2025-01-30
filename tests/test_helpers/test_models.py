"""Tests for models module."""
from itertools import product
from unittest.mock import Mock, patch

import pytest
from common.djangoapps.student.models import CourseAccessRole
from django.core.exceptions import ValidationError
from django.utils import timezone

from futurex_openedx_extensions.helpers.clickhouse_operations import ClickhouseBaseError
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.models import ClickhouseQuery, DataExportTask, ViewUserMapping


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


@pytest.fixture
def view_user_mapping():
    """Return a ViewUserMapping instance."""
    return ViewUserMapping(
        user_id=1,
        view_name='test_view',
        enabled=True,
    )


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


@pytest.mark.django_db
def test_data_export_task_get_task(base_data):  # pylint: disable=unused-argument
    """Verify that DataExportTask.get_task returns correct task."""
    task = DataExportTask.objects.create(
        filename='test.csv',
        view_name='test_view',
        user_id=1,
        tenant_id=1,
    )
    assert DataExportTask.get_task(task.id) == task
    task.refresh_from_db()
    assert task.status == DataExportTask.STATUS_IN_QUEUE

    with pytest.raises(FXCodedException) as exc_info:
        DataExportTask.get_task(task.id + 1)
    assert exc_info.value.code == FXExceptionCodes.EXPORT_CSV_TASK_NOT_FOUND.value


@pytest.mark.django_db
@pytest.mark.parametrize('task_id', [
    None, 'not an int', 1.0,
])
def test_data_export_task_get_task_invalid_id(task_id):
    """Verify that DataExportTask.get_task raises FXCodedException for invalid task id."""
    with pytest.raises(FXCodedException) as exc_info:
        DataExportTask.get_task(task_id)
    assert exc_info.value.code == FXExceptionCodes.EXPORT_CSV_TASK_NOT_FOUND.value


@pytest.mark.django_db
def test_data_export_task_get_status(base_data):  # pylint: disable=unused-argument
    """Verify that DataExportTask.get_status returns correct status."""
    task = DataExportTask.objects.create(
        filename='test.csv',
        view_name='test_view',
        user_id=1,
        tenant_id=1,
    )
    assert DataExportTask.get_status(task.id) == DataExportTask.STATUS_IN_QUEUE
    task.status = DataExportTask.STATUS_PROCESSING
    task.save()
    assert DataExportTask.get_status(task.id) == DataExportTask.STATUS_PROCESSING


@pytest.mark.django_db
@pytest.mark.parametrize('status, new_status, error_filled', [
    (DataExportTask.STATUS_IN_QUEUE, DataExportTask.STATUS_PROCESSING, False),
    (DataExportTask.STATUS_PROCESSING, DataExportTask.STATUS_COMPLETED, False),
    (DataExportTask.STATUS_PROCESSING, DataExportTask.STATUS_FAILED, True),
    (DataExportTask.STATUS_IN_QUEUE, DataExportTask.STATUS_FAILED, True),
])
def test_data_export_task_set_status(
    base_data, status, new_status, error_filled,
):  # pylint: disable=unused-argument
    """Verify that DataExportTask.set_status sets correct status."""
    task = DataExportTask.objects.create(
        filename='test.csv',
        view_name='test_view',
        user_id=1,
        tenant_id=1,
        status=status,
    )
    DataExportTask.set_status(task.id, new_status, error_message='an error message')
    task.refresh_from_db()
    assert task.status == new_status
    assert task.error_message == ('an error message' if error_filled else None)


@pytest.mark.django_db
@pytest.mark.parametrize('status, new_status', [
    (DataExportTask.STATUS_IN_QUEUE, DataExportTask.STATUS_IN_QUEUE),
    (DataExportTask.STATUS_IN_QUEUE, DataExportTask.STATUS_COMPLETED),
    (DataExportTask.STATUS_PROCESSING, DataExportTask.STATUS_IN_QUEUE),
])
def test_data_export_task_set_status_invalid_transition(
    base_data, status, new_status,
):  # pylint: disable=unused-argument
    """Verify that DataExportTask.set_status raises FXCodedException for invalid status transition."""
    task = DataExportTask.objects.create(
        filename='test.csv',
        view_name='test_view',
        user_id=1,
        tenant_id=1,
        status=status,
    )
    with pytest.raises(FXCodedException) as exc_info:
        DataExportTask.set_status(task.id, new_status)
    assert exc_info.value.code == FXExceptionCodes.EXPORT_CSV_TASK_CHANGE_STATUS_NOT_POSSIBLE.value
    assert str(exc_info.value) == f'Cannot change task status from ({status}) to ({new_status})'


@pytest.mark.django_db
def test_data_export_task_set_status_processing_continue(base_data):  # pylint: disable=unused-argument
    """Verify that DataExportTask.set_status will not call save if status is just a continuation of processing."""
    task = DataExportTask.objects.create(
        filename='test.csv',
        view_name='test_view',
        user_id=1,
        tenant_id=1,
        status=DataExportTask.STATUS_PROCESSING,
    )
    with patch('futurex_openedx_extensions.helpers.models.DataExportTask.save') as mock_save:
        DataExportTask.set_status(task.id, DataExportTask.STATUS_PROCESSING)
    mock_save.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize('status', [DataExportTask.STATUS_COMPLETED, DataExportTask.STATUS_FAILED])
def test_data_export_task_set_status_invalid_transition_for_closed(
    base_data, status,
):  # pylint: disable=unused-argument
    """Verify that DataExportTask.set_status raises FXCodedException for transition from closed statuses."""
    task = DataExportTask.objects.create(
        filename='test.csv',
        view_name='test_view',
        user_id=1,
        tenant_id=1,
        status=status,
    )
    for new_status in DataExportTask.STATUS_CHOICES:
        with pytest.raises(FXCodedException) as exc_info:
            DataExportTask.set_status(task.id, new_status[0])
        assert exc_info.value.code == FXExceptionCodes.EXPORT_CSV_TASK_CHANGE_STATUS_NOT_POSSIBLE.value
        assert str(exc_info.value) == f'Cannot change task status from ({status}) to ({new_status[0]})'


@pytest.mark.django_db
@pytest.mark.parametrize('new_status', [None, ['not a string'], 1, 'invalid_status'])
def test_data_export_task_set_status_invalid_status(base_data, new_status):  # pylint: disable=unused-argument
    """Verify that DataExportTask.set_status raises FXCodedException for invalid status transition."""
    task = DataExportTask.objects.create(
        filename='test.csv',
        view_name='test_view',
        user_id=1,
        tenant_id=1,
    )
    with pytest.raises(FXCodedException) as exc_info:
        DataExportTask.set_status(task.id, status=new_status)
    assert exc_info.value.code == FXExceptionCodes.EXPORT_CSV_TASK_CHANGE_STATUS_NOT_POSSIBLE.value
    assert str(exc_info.value) == f'Invalid status! ({new_status})'


@pytest.mark.django_db
def test_data_export_task_set_progress(base_data):  # pylint: disable=unused-argument
    """Verify that DataExportTask.set_progress sets correct progress."""
    valid_progress = 0.66
    task = DataExportTask.objects.create(
        filename='test.csv',
        view_name='test_view',
        user_id=1,
        tenant_id=1,
    )

    for status_choice in DataExportTask.STATUS_CHOICES:
        task.status = status_choice[0]
        task.save()

        if status_choice[0] != DataExportTask.STATUS_PROCESSING:
            with pytest.raises(FXCodedException) as exc_info:
                DataExportTask.set_progress(task.id, valid_progress)
            assert exc_info.value.code == FXExceptionCodes.EXPORT_CSV_TASK_CANNOT_CHANGE_PROGRESS.value
            assert str(exc_info.value) == f'Cannot set progress for a task with status ({status_choice[0]}).'
        else:
            DataExportTask.set_progress(task.id, valid_progress)
            task.refresh_from_db()
            assert task.progress == valid_progress


@pytest.mark.django_db
@pytest.mark.parametrize('invalid_progress', [
    None, 'not an int', 1.0001, -0.00001,
])
def test_data_export_task_set_progress_invalid_value(base_data, invalid_progress):  # pylint: disable=unused-argument
    """Verify that DataExportTask.set_progress raises FXCodedException for invalid progress value."""
    task = DataExportTask.objects.create(
        filename='test.csv',
        view_name='test_view',
        user_id=1,
        tenant_id=1,
        status=DataExportTask.STATUS_PROCESSING,
    )

    with pytest.raises(FXCodedException) as exc_info:
        DataExportTask.set_progress(task.id, invalid_progress)
    assert exc_info.value.code == FXExceptionCodes.EXPORT_CSV_TASK_INVALID_PROGRESS_VALUE.value
    assert str(exc_info.value) == f'Invalid progress value! ({invalid_progress}).'


@pytest.mark.django_db
@pytest.mark.parametrize('role_definition, is_staff, is_active, enabled, expires_at', product(
    [  # expected_permitted , role, org, course_id
        (True, 'global', '', ''),
        (True, 'tenant_only', 'org1', ''),
        (True, 'course_only', 'org1', 'course-v1:org+1+1'),
        (True, 'tenant_or_course', 'org1', ''),
        (True, 'tenant_or_course', 'org1', 'course-v1:org+1+1'),
        (False, 'global', 'org', ''),
        (False, 'global', 'org', 'course-v1:org+1+1'),
        (False, 'global', '', 'course-v1:org+1+1'),
        (False, 'tenant_only', '', ''),
        (False, 'tenant_only', 'org1', 'course-v1:org+1+1'),
        (False, 'tenant_only', '', 'course-v1:org+1+1'),
        (False, 'course_only', '', 'course-v1:org+1+1'),
        (False, 'course_only', 'org1', ''),
        (False, 'course_only', '', ''),
        (False, 'tenant_or_course', '', ''),
        (False, 'tenant_or_course', '', 'course-v1:org+1+1'),
    ],
    [True, False],
    [True, False],
    [True, False],
    [None, timezone.now() + timezone.timedelta(minutes=1), timezone.now() + timezone.timedelta(minutes=-1)],
))
def test_view_user_mapping_manager_get_queryset(
    role_definition, is_staff, is_active, enabled, expires_at, base_data, view_user_mapping,
):  # pylint: disable=unused-argument, too-many-arguments, redefined-outer-name
    """
    Verify that ViewAllowedRolesManager.get_queryset returns correct value. This is a critical test that ensures
    that get_queryset method is returning the correct queryset based on the role definition and user properties. The
    returned annotations will determine if an API mapping is usable or not. This why we test all possible combinations
    of the role definition and user properties with no exceptions.
    """
    user_id = 1
    expected_permitted = role_definition[0]
    role = role_definition[1]
    org = role_definition[2]
    course_id = role_definition[3]
    CourseAccessRole.objects.create(
        user_id=user_id,
        role=role,
        org=org,
        course_id=course_id,
    )
    view_user_mapping.user.is_staff = is_staff
    view_user_mapping.user.is_superuser = is_staff
    view_user_mapping.user.is_active = is_active
    view_user_mapping.user.save()
    view_user_mapping.enabled = enabled
    view_user_mapping.expires_at = expires_at
    view_user_mapping.save()

    expected_usable = is_active and (
        is_staff or (
            expected_permitted and enabled and (
                expires_at is None or expires_at > timezone.now()
            )
        )
    )

    with patch('futurex_openedx_extensions.helpers.models.get_allowed_roles') as mocked_roles:
        mocked_roles.return_value = {
            'global': ['global'],
            'tenant_only': ['tenant_only'],
            'course_only': ['course_only'],
            'tenant_or_course': ['tenant_or_course'],
        }
        assert view_user_mapping.get_is_user_active() == is_active
        assert view_user_mapping.get_is_user_system_staff() == is_staff
        assert view_user_mapping.get_has_access_role() == expected_permitted
        assert view_user_mapping.get_usable() == expected_usable
        assert ViewUserMapping.is_usable_access(
            view_user_mapping.user, view_user_mapping.view_name,
        ) == expected_usable
