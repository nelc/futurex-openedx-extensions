"""Tests for models module."""
# pylint: disable=too-many-lines
import copy
import json
from itertools import product
from unittest.mock import Mock, patch

import pytest
from common.djangoapps.student.models import CourseAccessRole
from deepdiff import DeepDiff
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.utils import timezone

from futurex_openedx_extensions.helpers.clickhouse_operations import ClickhouseBaseError
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.extractors import (
    dot_separated_path_force_set_value,
    dot_separated_path_get_value,
)
from futurex_openedx_extensions.helpers.model_helpers import NoUpdateQuerySet
from futurex_openedx_extensions.helpers.models import (
    ClickhouseQuery,
    ConfigMirror,
    DataExportTask,
    DraftConfig,
    ViewUserMapping,
)


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


@pytest.mark.django_db
@pytest.mark.parametrize(
    'config_value, expected_saved_string, test_case',
    [
        (
            'a string value',
            f'{{"{DraftConfig.ROOT}": "a string value"}}',
            'sample string value saved as JSON string',
        ),
        (
            {'src': '/logo.png'},
            f'{{"{DraftConfig.ROOT}": {{"src": "/logo.png"}}}}',
            'saves dictionary value as JSON string',
        ),
        (
            123,
            f'{{"{DraftConfig.ROOT}": 123}}',
            'saves integer value as JSON string',
        ),
        (
            {},
            f'{{"{DraftConfig.ROOT}": {{}}}}',
            'saves empty dictionary as JSON string',
        ),
        (
            None,
            f'{{"{DraftConfig.ROOT}": null}}',
            'saves None as JSON null value',
        ),
    ]
)
def test_draft_config_save_value_as_dictionary(
    base_data, config_value, expected_saved_string, test_case,
):  # pylint: disable=unused-argument
    """Verify that DraftConfig.save correctly saves config_value as a dictionary inside a root key."""
    draft_config = DraftConfig.objects.create(
        tenant_id=1,
        config_path='any',
        config_value=config_value,
        created_by_id=1,
        updated_by_id=1
    )
    assert draft_config.config_value == expected_saved_string, test_case
    assert not DeepDiff(json.loads(draft_config.config_value), {
        DraftConfig.ROOT: config_value,
    }, ignore_order=True), test_case


@pytest.mark.django_db
def test_draft_config_save_update_value(base_data):  # pylint: disable=unused-argument
    """Verify that DraftConfig.save updates existing config_value."""
    draft_config = DraftConfig.objects.create(
        tenant_id=1,
        config_path='any',
        config_value=123,
        created_by_id=1,
        updated_by_id=1
    )
    assert draft_config.config_value == f'{{"{DraftConfig.ROOT}": 123}}', 'test case failed: initial save'

    new_value = [1, 2]
    draft_config.config_value = new_value
    draft_config.save()
    draft_config.refresh_from_db()
    assert draft_config.config_value == f'{{"{DraftConfig.ROOT}": [1, 2]}}', 'test case failed: change existing value'

    draft_config.config_value = new_value
    draft_config.save()
    draft_config.refresh_from_db()
    assert draft_config.config_value == f'{{"{DraftConfig.ROOT}": [1, 2]}}', 'test case failed: save same value again'


@pytest.mark.django_db
def test_draft_config_save_change_value(base_data, draft_configs):  # pylint: disable=unused-argument
    """Verify that DraftConfig.save changes the revision_id only when config_value is changed."""
    draft_config = draft_configs[0]
    revision_id = draft_config.revision_id
    assert draft_config.config_value == f'{{"{DraftConfig.ROOT}": "https://linkedin.com/test"}}', 'bad test data'

    draft_config.config_value = 'new value'
    draft_config.save()
    draft_config.refresh_from_db()
    assert draft_config.revision_id != revision_id, 'revision_id should change on value update'

    revision_id = draft_config.revision_id
    draft_config.config_value = 'new value'
    draft_config.save()
    draft_config.refresh_from_db()
    assert draft_config.revision_id == revision_id, 'revision_id should not change on same value update'


@pytest.mark.parametrize('input_value, expected_json_string, test_case', [
    ('a string', f'{{"{DraftConfig.ROOT}": "a string"}}', 'string input'),
    ({'key': 'value'}, f'{{"{DraftConfig.ROOT}": {{"key": "value"}}}}', 'dictionary input'),
    (123, f'{{"{DraftConfig.ROOT}": 123}}', 'integer input'),
    (None, f'{{"{DraftConfig.ROOT}": null}}', 'None input'),
    (f'{{"{DraftConfig.ROOT}": "already json"}}', f'{{"{DraftConfig.ROOT}": "already json"}}', 'already JSON string'),
])
def test_draft_config_get_save_ready_config_value(input_value, expected_json_string, test_case):
    """Verify that DraftConfig.get_save_ready_config_value works correctly."""
    result = DraftConfig.get_save_ready_config_value(input_value)
    assert result == expected_json_string, test_case


@pytest.mark.django_db
def test_draft_config_save_change_value_db_value_match(base_data, draft_configs):  # pylint: disable=unused-argument
    """
    Verify that DraftConfig.save will not json-dumps the config_value if it is already a JSON string, and will not
    regenerate the revision_id if the value is the same.
    """
    draft_config = draft_configs[0]
    revision_id = draft_config.revision_id
    assert draft_config.config_value == f'{{"{DraftConfig.ROOT}": "https://linkedin.com/test"}}', 'bad test data'

    draft_config.config_value = f'{{"{DraftConfig.ROOT}": "https://linkedin.com/test"}}'
    draft_config.save()
    draft_config.refresh_from_db()
    assert draft_config.config_value == f'{{"{DraftConfig.ROOT}": "https://linkedin.com/test"}}', \
        'config_value should match DB value'
    assert draft_config.revision_id == revision_id, 'revision_id should not change on same value update'


@pytest.mark.django_db
@pytest.mark.parametrize('new_config_value', ['test', 123, None, {'key': 'value'}])
def test_draft_config_save_change_value_with_root(
    base_data, draft_configs, new_config_value,
):  # pylint: disable=unused-argument
    """
    Verify that DraftConfig.save will not json-dumps the config_value if it is already a JSON string starting with
    the `DraftConfig.ROOT` key.
    """
    draft_config = draft_configs[0]
    revision_id = draft_config.revision_id
    assert draft_config.config_value == f'{{"{DraftConfig.ROOT}": "https://linkedin.com/test"}}', 'bad test data'

    final_new_value = json.dumps({
        DraftConfig.ROOT: new_config_value,
    })
    draft_config.config_value = final_new_value
    draft_config.save()
    draft_config.refresh_from_db()
    assert draft_config.config_value == final_new_value, 'config_value should match DB value'
    assert draft_config.revision_id != revision_id, 'revision_id should change'

    revision_id = draft_config.revision_id
    draft_config.config_value = new_config_value
    draft_config.save()
    draft_config.refresh_from_db()
    assert draft_config.config_value == final_new_value, 'config_value should match DB value'
    assert draft_config.revision_id == revision_id, 'revision_id should not be changed'


@pytest.mark.django_db
@pytest.mark.parametrize(
    'config_paths, expected, test_case',
    [
        (
            None,
            {},
            'None should return empty dict',
        ),
        (
            [],
            {},
            'Empty list should return empty dict',
        ),
        (
            ['theme_v2.footer.linkedin_url'],
            {
                'theme_v2.footer.linkedin_url': {
                    'config_value': 'https://linkedin.com/test',
                    'revision_id': 999,
                },
            },
            'selected paths should return only the specified path',
        ),
        (
            ['non.existent.key'],
            {
                'non.existent.key': {
                    'config_value': None,
                    'revision_id': 0,
                },
            },
            'Non-existing path should return None and a zero revision_id',
        ),
    ]
)
def test_draft_config_get_config_values(
    base_data, draft_configs, config_paths, expected, test_case,
):  # pylint: disable=unused-argument
    """Verify DraftConfig.get_config_values returns correctly nested dict based on config_path"""
    result = DraftConfig.get_config_values(tenant_id=1, config_paths=config_paths)
    assert result == expected, test_case


def test_draft_config_does_not_allow_update_method():
    """Verify that DraftConfig does not allow update method."""
    assert DraftConfig.objects.__class__.__name__ == NoUpdateQuerySet.as_manager().__class__.__name__, \
        'DraftConfig.objects should be NoUpdateQuerySet.as_manager to prevent updates using .update() method'


@pytest.mark.django_db
def test_draft_config_must_not_allow_null_value():
    """Verify that DraftConfig does not allow null config_value."""
    sample = DraftConfig.objects.create(
        tenant_id=1,
        config_path='any.path',
        config_value=None,
        revision_id=999,
        created_by_id=1,
        updated_by_id=1,
    )
    assert sample is not None, 'Should be able to create with null config_value since it will be saved as JSON null'
    with pytest.raises(IntegrityError) as exc_info:
        DraftConfig.objects.allow_update().update(config_value=None)
    assert 'NOT NULL constraint failed' in str(exc_info.value)


@pytest.mark.django_db
def test_get_config_value_by_path_found(base_data, draft_configs):  # pylint: disable=unused-argument
    """Verify get_config_value_by_path returns correct dict when config exists"""
    draft_config = DraftConfig.get_config_value_by_path(
        tenant_id=1,
        config_path='theme_v2.footer.linkedin_url'
    )
    assert draft_config['config_value'] == 'https://linkedin.com/test'
    assert draft_config['revision_id'] != 0


@pytest.mark.django_db
@pytest.mark.parametrize('config_path,test_case', [
    ('non.existent.path', 'non-existent path'),
    ('', 'empty string path'),
    (None, 'None path'),
])
def test_get_config_value_by_path_not_found(
    base_data, draft_configs, config_path, test_case,
):  # pylint: disable=unused-argument
    """Verify get_config_value_by_path returns fallback dict when config is missing"""
    result = DraftConfig.get_config_value_by_path(tenant_id=1, config_path=config_path)
    assert result == {'config_value': None, 'revision_id': 0}, test_case


@pytest.mark.parametrize('mock_config_values, expected_merged, test_case', [
    (
        {
            'theme_v2.footer.linkedin_url': {
                'config_value': 'https://linkedin.com',
                'revision_id': 123
            },
            'theme_v2.footer.twitter_url': {
                'config_value': 'https://twitter.com',
                'revision_id': 123
            }
        },
        {
            'theme_v2': {
                'footer': {
                    'linkedin_url': 'https://linkedin.com',
                    'twitter_url': 'https://twitter.com',
                    'height': 100,
                },
                'header': {
                    'logo': {'src': '/logo.png'},
                },
            },
        },
        'valid flat config values get merged into nested dict'
    ),
    (
        {
            'theme_v2.footer.linkedin_url': {
                'config_value': None,
                'revision_id': 123,
            },
            'theme_v2.footer.twitter_url': {
                'config_value': 'https://twitter.com',
                'revision_id': 123,
            },
            'theme_v2.footer.facebook_url': {
                'config_value': 'https://facebook.com',
                'revision_id': 0,
            },
        },
        {
            'theme_v2': {
                'footer': {
                    'linkedin_url': 'https://linkedin.com/test',
                    'twitter_url': 'https://twitter.com',
                    'height': 100,
                },
                'header': {
                    'logo': {'src': '/logo.png'},
                },
            },
        },
        'skips values with None or revision_id == 0'
    ),
    (
        {},
        {
            'theme_v2': {
                'footer': {
                    'linkedin_url': 'https://linkedin.com/test',
                    'height': 100,
                },
                'header': {
                    'logo': {'src': '/logo.png'},
                },
            },
        },
        'empty config_values is OK'
    ),
    (
        {
            'theme_v2.footer.colors.text': {
                'config_value': '#998877',
                'revision_id': 999,
            },
        },
        {
            'theme_v2': {
                'footer': {
                    'linkedin_url': 'https://linkedin.com/test',
                    'height': 100,
                    'colors': {
                        'text': '#998877',
                    },
                },
                'header': {
                    'logo': {'src': '/logo.png'},
                },
            },
        },
        'New dictionary levels can be added with no problem'
    ),
    (
        {
            'theme_v2.header.logo.src.details': {
                'config_value': 'extra level',
                'revision_id': 999,
            },
        },
        {
            'theme_v2': {
                'footer': {
                    'linkedin_url': 'https://linkedin.com/test',
                    'height': 100,
                },
                'header': {
                    'logo': {'src': {'details': 'extra level'}},
                },
            },
        },
        'Overriding a value into a dictionary is possible because the priority is for the config_path to be created'
    ),
    (
        {
            'theme_v2': {
                'config_value': {
                    'footer': {
                        'linkedin_url': 'https://linkedin.com/v1',
                        'facebook_url': 'https://facebook.com/v1',
                    },
                },
                'revision_id': 999,
            },
            'theme_v2.footer.linkedin_url': {
                'config_value': 'https://linkedin.com/v2',
                'revision_id': 888,
            },
            'theme_v2.footer': {
                'config_value': {
                    'linkedin_url': 'https://linkedin.com/v3',
                    'facebook_url': 'https://facebook.com/v3',
                },
                'revision_id': 777,
            },
        },
        {
            'theme_v2': {
                'footer': {
                    'linkedin_url': 'https://linkedin.com/v2',
                    'facebook_url': 'https://facebook.com/v3',
                },
            },
        },
        'always consider the value of the most specific path (leaf node)'
    ),
    (
        {
            'theme_v2.header.color': {
                'config_value': '#445566',
                'revision_id': 999,
            },
        },
        {
            'theme_v2': {
                'footer': {
                    'linkedin_url': 'https://linkedin.com/test',
                    'height': 100,
                },
                'header': {
                    'logo': {'src': '/logo.png'},
                    'color': '#445566',
                },
            },
        },
        'adds new config value to existing nested dict structure',
    ),
])
@patch.object(DraftConfig, 'get_config_values')
def test_draft_config_loads_into(mock_get_config_values, mock_config_values, expected_merged, test_case):
    """Verify DraftConfig.loads_into returns the expected merged config values."""
    mock_get_config_values.return_value = mock_config_values

    dest = {
        'theme_v2': {
            'footer': {
                'linkedin_url': 'https://linkedin.com/test',
                'height': 100,
            },
            'header': {
                'logo': {'src': '/logo.png'},
            },
        },
    }
    config_values = DraftConfig.loads_into(
        tenant_id=1,
        config_paths=['theme_v2.footer.linkedin_url'],
        dest=dest,
    )
    assert dest == expected_merged, test_case
    assert config_values == mock_config_values


def test_draft_config_loads_into_must_be_dict():
    """Verify that DraftConfig.loads_into raises an error if src is not a dictionary"""
    with pytest.raises(TypeError) as exc_info:
        DraftConfig.loads_into(
            tenant_id=1,
            config_paths=['any'],
            dest='not dictionary'
        )
    assert str(exc_info.value) == 'DraftConfig.loads: destination must be a dictionary.'


@pytest.mark.django_db
def test_draft_config_update_from_dict_new(base_data):  # pylint: disable=unused-argument
    """Verify that DraftConfig.update_from_dict works fine with new records"""
    def _assert_draft_configs(_src):
        for draft_config in DraftConfig.objects.all():
            current = _src
            parts = draft_config.config_path.split('.')
            for part in parts:
                current = current[part]
            assert draft_config.get_config_value()['config_value'] == current

    user1 = get_user_model().objects.get(id=1)
    user2 = get_user_model().objects.get(id=2)

    assert DraftConfig.objects.count() == 0, 'bad test data'
    config_paths = [
        'level1.level2.level3',
        'level1.level2.level3',
        'level1',
        'level1-1.level2.level3',
        'level1-1.level2.level4',
    ]

    src = {
        'level1': {
            'level2': {
                'level3': 'value33',
            },
            'level2-2': 'value22',
        },
        'level1-1': {
            'level2': {
                'level3': 'value33-2',
                'level4': 'value33-3',
                'level5': 'value33-4',
            },
        },
    }

    update_plan = DraftConfig.update_from_dict(
        tenant_id=1,
        config_paths=config_paths,
        src=src,
        user=user1,
        verify_revision_ids=None,
    )

    assert DraftConfig.objects.count() == 4, 'should create 4 records'
    assert set(update_plan['to_create'].keys()) == {
        'level1-1.level2.level4',
        'level1.level2.level3',
        'level1',
        'level1-1.level2.level3'
    }
    assert DraftConfig.objects.filter(updated_by=user1).count() == 4, 'all records should be created by the same user'
    _assert_draft_configs(_src=src)

    src['level1']['level2']['level3'] = None
    DraftConfig.update_from_dict(
        tenant_id=1,
        config_paths=config_paths,
        src=src,
        user=user2,
        verify_revision_ids=None,
    )
    assert DraftConfig.objects.count() == 3, 'the record related to the None value should be deleted'
    assert DraftConfig.objects.filter(updated_by=user2).count() == 1, 'one record should be updated'
    assert DraftConfig.objects.filter(updated_by=user1).count() == 2, 'rest of the records should not be updated'

    _assert_draft_configs(_src=src)


@pytest.mark.django_db
@pytest.mark.parametrize('src, test_case', [
    (
        {
            'level1': {
                'level2b': 'value',
            },
        }, 'the key does not exist at all'
    ),
    (
        {
            'level1': {
                'level2': 'value',
            },
        }, 'the key exists but the type is not dictionary'
    ),
])
def test_draft_config_update_from_dict_delete_non_existing(
    base_data, src, test_case,
):  # pylint: disable=unused-argument
    """Verify that DraftConfig.update_from_dict removes DraftConfig that their path is not included in the source"""
    assert DraftConfig.objects.count() == 0, 'bad test data'
    config_path = 'level1.level2.level3'
    DraftConfig.objects.create(
        tenant_id=1,
        config_path=config_path,
        config_value='value33',
        created_by_id=1,
        updated_by_id=1,
    )

    DraftConfig.update_from_dict(
        tenant_id=1,
        config_paths=[config_path],
        src=src,
        user=get_user_model().objects.first(),
        verify_revision_ids=None,
    )

    assert DraftConfig.objects.count() == 0, test_case


def test_draft_config_update_from_dict_src_must_be_dict():
    """Verify that DraftConfig.update_from_dict raises an error if src is not a dictionary"""
    with pytest.raises(TypeError) as exc_info:
        DraftConfig.update_from_dict(
            tenant_id=1,
            config_paths=['any'],
            src='not dictionary',
            user=Mock(),
            verify_revision_ids=None,
        )
    assert str(exc_info.value) == 'DraftConfig.update_from_dict: source must be a dictionary.'


def _prepare_test_data_for_conflict_tests(multi_user_scenario):
    """Create users and draft config records for conflict tests."""
    revision_id_to_verify = 100
    draft_config = DraftConfig.objects.create(
        tenant_id=1,
        config_path='a.b',
        config_value='value',
        revision_id=revision_id_to_verify,
        created_by_id=1,
        updated_by_id=1,
    )
    assert DraftConfig.objects.count() == 1, 'bad test data'
    if multi_user_scenario == 'updated_by_other':
        draft_config.config_value = 'changed by other user'
        draft_config.save()
        draft_config.refresh_from_db()
        assert draft_config.revision_id != 100, 'the revision_id should be changed'
    elif multi_user_scenario == 'deleted_by_other':
        draft_config.delete()
        assert DraftConfig.objects.count() == 0, 'the record should be deleted'

    return get_user_model().objects.get(id=10), draft_config


@pytest.mark.django_db
@pytest.mark.parametrize('multi_user_scenario', ['nothing', 'updated_by_other', 'deleted_by_other'])
@patch('futurex_openedx_extensions.helpers.models.DraftConfigUpdatePreparer.get_update_plan')
def test_draft_config_update_from_dict_conflict_delete(
    mock_update_plan, base_data, multi_user_scenario,
):  # pylint: disable=unused-argument
    """
    Verify that DraftConfig.update_from_dict detects if a record that is supposed to be deleted was changed or deleted
    by another user after the update plan was prepared.
    """
    revision_id_to_verify = 100
    mock_update_plan.return_value = {
        'to_delete': {'a.b': {'current_revision_id': revision_id_to_verify}},
        'to_create': {},
        'to_update': {},
    }
    user10, _ = _prepare_test_data_for_conflict_tests(multi_user_scenario)

    if multi_user_scenario == 'nothing':
        DraftConfig.update_from_dict(
            tenant_id=1,
            config_paths=['a.b'],
            src={},
            user=user10,
            verify_revision_ids={'dummy': 'this has no effect here since we mocked get_update_plan'},
        )
        assert DraftConfig.objects.count() == 0, 'the record should be deleted with no problem'
    else:
        with pytest.raises(FXCodedException) as exc_info:
            DraftConfig.update_from_dict(
                tenant_id=1,
                config_paths=['a.b'],
                src={},
                user=user10,
                verify_revision_ids={'dummy': 'this has no effect here since we mocked get_update_plan'},
            )
        assert exc_info.value.code == FXExceptionCodes.DRAFT_CONFIG_DELETE_MISMATCH.value
        assert str(exc_info.value) == 'Failed to delete all the specified draft config paths.'


@pytest.mark.django_db
@pytest.mark.parametrize('multi_user_scenario', ['nothing', 'updated_by_other', 'deleted_by_other'])
@patch('futurex_openedx_extensions.helpers.models.DraftConfigUpdatePreparer.get_update_plan')
def test_draft_config_update_from_dict_conflict_update(
    mock_update_plan, base_data, multi_user_scenario,
):  # pylint: disable=unused-argument
    """
    Verify that DraftConfig.update_from_dict detects if a record that is supposed to be updated was changed or deleted
    by another user after the update plan was prepared.
    """
    revision_id_to_verify = 100
    mock_update_plan.return_value = {
        'to_update': {
            'a.b': {
                'new_config_value': 'newVal',
                'current_revision_id': revision_id_to_verify,
                'new_revision_id': 123,
            },
        },
        'to_create': {},
        'to_delete': {},
    }
    user10, draft_config = _prepare_test_data_for_conflict_tests(multi_user_scenario)

    if multi_user_scenario == 'nothing':
        DraftConfig.update_from_dict(
            tenant_id=1,
            config_paths=['a.b'],
            src={},
            user=user10,
            verify_revision_ids={'dummy': 'this has no effect here since we mocked get_update_plan'},
        )
        assert DraftConfig.objects.count() == 1, 'the record should be there'
        draft_config.refresh_from_db()
        assert draft_config.get_save_ready_config_value('newVal') == draft_config.config_value, \
            'the record should be updated'
        assert draft_config.revision_id == 123, 'the revision_id should be updated too'
    else:
        with pytest.raises(FXCodedException) as exc_info:
            DraftConfig.update_from_dict(
                tenant_id=1,
                config_paths=['a.b'],
                src={},
                user=user10,
                verify_revision_ids={'dummy': 'this has no effect here since we mocked get_update_plan'},
            )
        assert exc_info.value.code == FXExceptionCodes.DRAFT_CONFIG_UPDATE_MISMATCH.value
        assert str(exc_info.value) == 'Failed to update all the specified draft config paths.'


@pytest.mark.django_db
@pytest.mark.parametrize('multi_user_scenario', ['nothing', 'created_by_other'])
@patch('futurex_openedx_extensions.helpers.models.DraftConfigUpdatePreparer.get_update_plan')
def test_draft_config_update_from_dict_conflict_create(
    mock_update_plan, base_data, multi_user_scenario,
):  # pylint: disable=unused-argument
    """
    Verify that DraftConfig.update_from_dict detects if a record that is supposed to be created was already created
    by another user after the update plan was prepared.
    """
    mock_update_plan.return_value = {
        'to_create': {
            'a.b': {
                'new_config_value': 'newVal',
                'new_revision_id': 123,
            },
        },
        'to_update': {},
        'to_delete': {},
    }
    user10 = get_user_model().objects.get(id=10)

    assert DraftConfig.objects.count() == 0, 'bad test data'
    if multi_user_scenario == 'created_by_other':
        DraftConfig.objects.create(
            tenant_id=1,
            config_path='a.b',
            config_value='changed by other user',
            revision_id=999,
            created_by_id=1,
            updated_by_id=1,
        )

    if multi_user_scenario == 'nothing':
        DraftConfig.update_from_dict(
            tenant_id=1,
            config_paths=['a.b'],
            src={},
            user=user10,
            verify_revision_ids={'dummy': 'this has no effect here since we mocked get_update_plan'},
        )
        assert DraftConfig.objects.count() == 1, 'the record should be there'
        draft_config = DraftConfig.objects.first()
        assert draft_config.get_save_ready_config_value('newVal') == draft_config.config_value, \
            'the record should be created'
        assert draft_config.revision_id == 123, 'the revision_id should be correct'
    else:
        with pytest.raises(FXCodedException) as exc_info:
            DraftConfig.update_from_dict(
                tenant_id=1,
                config_paths=['a.b'],
                src={},
                user=user10,
                verify_revision_ids={'dummy': 'this has no effect here since we mocked get_update_plan'},
            )
        assert exc_info.value.code == FXExceptionCodes.DRAFT_CONFIG_CREATE_MISMATCH.value
        assert str(exc_info.value) == 'Failed to create all the specified draft config paths.'


def test_draft_config_root_key():
    """Verify that DraftConfig.ROOT is a valid root key."""
    assert DraftConfig.ROOT == '___root', 'DANGEROUS ACTION: breaking this test means that data migration is needed ' \
        'to fix existing data, or at least ensure that all drafts are published before deploying this change!'


@pytest.mark.django_db
def test_config_mirror_sync_tenant(config_mirror_fixture):
    """Verify that config_mirror_sync_tenant copies the configs correctly."""
    tenant, _ = config_mirror_fixture
    tenant.lms_configs['LMS_NAME'] = 'Tenant LMS'
    tenant.save()

    ConfigMirror.sync_tenant(tenant.id)
    tenant.refresh_from_db()
    assert tenant.lms_configs['LMS_NAME'] == 'Dummy LMS', 'should be resynced from source'
    assert tenant.lms_configs['deep']['LMS_NAME'] == 'Dummy LMS', 'it is a source, should not change'

    tenant.lms_configs['deep']['LMS_NAME'] = 'Tenant LMS'
    tenant.save()

    ConfigMirror.sync_tenant(tenant.id)
    tenant.refresh_from_db()
    assert tenant.lms_configs['LMS_NAME'] == 'Tenant LMS', 'should be synced from source'
    assert tenant.lms_configs['deep']['LMS_NAME'] == 'Tenant LMS', 'it is a source, should not change'


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.models.invalidate_tenant_readable_lms_configs')
@patch('futurex_openedx_extensions.helpers.models.invalidate_cache')
def test_config_mirror_sync_tenant_calls_invalidate_cache(
    mock_invalidate_cache, mock_readable_lms_configs, config_mirror_fixture,
):
    """Verify that config_mirror_sync_tenant calls invalidate_cache when there is something to change."""
    tenant, _ = config_mirror_fixture
    ConfigMirror.sync_tenant(tenant.id)
    mock_readable_lms_configs.assert_called_once_with([tenant.id])
    mock_invalidate_cache.assert_called_once_with()


@pytest.mark.django_db
@pytest.mark.parametrize(
    'action', [item[0] for item in ConfigMirror.MISSING_SOURCE_ACTION_CHOICES]
)
def test_config_mirror_sync_tenant_missing_source_action(action, config_mirror_fixture):
    """Verify that the correct method is called when the key of the source path does not exist."""
    tenant, mirror = config_mirror_fixture
    tenant.lms_configs['deep'].pop('LMS_NAME')
    tenant.save()
    mirror.missing_source_action = action
    mirror.save()

    method_name = f'_handle_missing_source_{action}'
    with patch(f'futurex_openedx_extensions.helpers.models.ConfigMirror.{method_name}') as mock_handle_missing:
        ConfigMirror.sync_tenant(tenant.id)
        mock_handle_missing.assert_called_once_with(configs=tenant.lms_configs)


@pytest.mark.django_db
def test_config_mirror_sync_tenant_missing_source_action_wrong(config_mirror_fixture):
    """Verify that an exception is raised if a non-supported value for the action is used."""
    tenant, mirror = config_mirror_fixture
    tenant.lms_configs['deep'].pop('LMS_NAME')
    tenant.save()
    mirror.missing_source_action = 'action_wrong'
    mirror.save()

    with pytest.raises(FXCodedException) as exc_info:
        ConfigMirror.sync_tenant(tenant.id)
    assert exc_info.value.code == FXExceptionCodes.CONFIG_MIRROR_INVALID_ACTION.value
    assert str(exc_info.value) == f'Invalid missing source action: action_wrong in record {mirror.id}'


def init_config_mirror_sync_tenant_action_test(tenant, mirror, action):
    """Helper function to initialize the test for ConfigMirror.sync_tenant with a specific action."""
    dest_original = copy.deepcopy(tenant.lms_configs['LMS_NAME']) if tenant.lms_configs.get('LMS_NAME') else None
    source_copy = copy.deepcopy(tenant.lms_configs['deep'])
    source_copy.pop('LMS_NAME', None)
    tenant.lms_configs['deep'] = source_copy
    tenant.save()
    mirror.missing_source_action = action
    mirror.save()

    method_name = f'_handle_missing_source_{action}'
    getattr(mirror, method_name)(configs=tenant.lms_configs)
    tenant.save()
    tenant.refresh_from_db()

    return tenant, mirror, dest_original


@pytest.mark.django_db
def test_config_mirror_sync_tenant_action_skip(config_mirror_fixture):
    """Verify that ConfigMirror._handle_missing_source_skip works as expected."""
    tenant, _, dest_original = init_config_mirror_sync_tenant_action_test(*config_mirror_fixture, action='skip')
    assert 'LMS_NAME' not in tenant.lms_configs['deep']
    assert tenant.lms_configs['LMS_NAME'] == dest_original


@pytest.mark.django_db
def test_config_mirror_sync_tenant_action_set_null(config_mirror_fixture):
    """Verify that ConfigMirror._handle_missing_source_set_null works as expected."""
    tenant, _, _ = init_config_mirror_sync_tenant_action_test(*config_mirror_fixture, action='set_null')
    assert tenant.lms_configs['deep']['LMS_NAME'] is None
    assert tenant.lms_configs['LMS_NAME'] is None


@pytest.mark.django_db
@pytest.mark.parametrize('dest_path, dest_value, dest_exists', product(
    ['LMS_NAME2', 'deep2.LMS_NAME2'],
    [{'dict': 'value'}, 'not dictionary'],
    [True, False],
))
def test_config_mirror_sync_tenant_action_delete(dest_path, dest_value, dest_exists, config_mirror_fixture):
    """Verify that ConfigMirror._handle_missing_source_delete works as expected."""
    tenant, mirror = config_mirror_fixture
    mirror.destination_path = dest_path
    mirror.save()
    if dest_exists:
        dot_separated_path_force_set_value(tenant.lms_configs, dest_path, dest_value)
    else:
        assert dot_separated_path_get_value(tenant.lms_configs, dest_path) == (False, None)
    tenant, mirror, _ = init_config_mirror_sync_tenant_action_test(tenant, mirror, action='delete')
    assert dot_separated_path_get_value(tenant.lms_configs, dest_path) == (False, None)
    assert dot_separated_path_get_value(tenant.lms_configs, mirror.source_path) == (False, None)


@pytest.mark.django_db
def test_config_mirror_sync_tenant_action_copy_dest(config_mirror_fixture):
    """Verify that ConfigMirror._handle_missing_source_copy_dest works as expected."""
    tenant, _, dest_original = init_config_mirror_sync_tenant_action_test(
        *config_mirror_fixture, action='copy_dest',
    )
    assert tenant.lms_configs['deep']['LMS_NAME'] == dest_original
    assert tenant.lms_configs['LMS_NAME'] == dest_original


@pytest.mark.django_db
def test_config_mirror_sync_tenant_action_copy_dest_missing_dest(config_mirror_fixture):
    """Verify that ConfigMirror._handle_missing_source_copy_dest works as expected."""
    tenant, mirror = config_mirror_fixture
    tenant.lms_configs.pop('LMS_NAME')
    tenant.save()
    tenant, _, _ = init_config_mirror_sync_tenant_action_test(tenant, mirror, action='copy_dest')
    assert 'LMS_NAME' not in tenant.lms_configs['deep']
    assert 'LMS_NAME' not in tenant.lms_configs


@pytest.mark.django_db
def test_config_mirror_get_active_records(config_mirror_fixture):
    """Verify that ConfigMirror.get_active_records respects the priority of the records."""
    tenant, mirror = config_mirror_fixture
    tenant.lms_configs['lms_name'] = 'Dummy2 lms_name'
    tenant.save()
    mirror2 = ConfigMirror.objects.create(
        source_path='LMS_NAME',
        destination_path='lms_name',
        missing_source_action=ConfigMirror.MISSING_SOURCE_ACTION_SKIP,
        enabled=True,
    )

    result = ConfigMirror.get_active_records()
    assert len(result) == 2
    assert result[0] == mirror
    assert result[1] == mirror2

    mirror2.priority = 1
    mirror2.save()
    result = ConfigMirror.get_active_records()
    assert len(result) == 2
    assert result[0] == mirror2
    assert result[1] == mirror


@pytest.mark.django_db
def test_config_mirror_enabled(config_mirror_fixture):
    """Verify that ConfigMirror.get_active_records returns only enabled records."""
    _, mirror = config_mirror_fixture
    result = ConfigMirror.get_active_records()
    assert len(result) == 1, 'should return no records when all are disabled'
    assert result[0] == mirror

    mirror.enabled = False
    mirror.save()

    result = ConfigMirror.get_active_records()
    assert len(result) == 0, 'should return no records when all are disabled'


@pytest.mark.django_db
def test_config_mirror_sync_tenant_tenant_not_found():
    """Verify that ConfigMirror.sync_tenant raises an error if tenant is not found."""
    with pytest.raises(FXCodedException) as exc_info:
        ConfigMirror.sync_tenant(9999)
    assert exc_info.value.code == FXExceptionCodes.TENANT_NOT_FOUND.value
    assert str(exc_info.value) == 'Tenant with ID 9999 not found.'


@pytest.mark.django_db
@pytest.mark.parametrize(
    'source_path, destination_path, allowed',
    [
        ('l1.l2.l3', 'l1.l2.l3.l4', False),
        ('l1.l2.l3.l4', 'l1.l2.l3', False),
        ('l1', 'l1.l2.l3.l4', False),
        ('l1.l2.l3.l4', 'l1', False),
        ('l1.l2', 'l1.l2b.l3', True),
        ('l1.l2b.l3', 'l1.l2', True),
        ('l1.l2', 'l1.l2b', True),
        ('l1.l2b', 'l1.l2', True),
    ]
)
def test_config_mirror_no_same_path(source_path, destination_path, allowed, config_mirror_fixture):
    """
    Verify that ConfigMirror does not allow saving a record when the destination and the source share
    the same path or path origin.
    """
    _, mirror = config_mirror_fixture
    mirror.source_path = source_path
    mirror.destination_path = destination_path

    if allowed:
        mirror.save()
        assert mirror.id is not None, 'should save the mirror without errors'
    else:
        with pytest.raises(FXCodedException) as exc_info:
            mirror.save()
        assert exc_info.value.code == FXExceptionCodes.CONFIG_MIRROR_INVALID_PATH.value
        assert str(exc_info.value) == (
            f'ConfigMirror source path and destination path cannot share the same path. (source: '
            f'<{mirror.source_path}>, dest: <{mirror.destination_path}>).'
        )
