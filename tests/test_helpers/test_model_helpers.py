"""Tests for DraftConfigUpdatePreparer in model_helpers.py."""
from unittest.mock import patch

import pytest
from deepdiff import DeepDiff
from django.contrib.auth import get_user_model
from django.db import connection, models
from django.db.models import Q, Value
from django.test import override_settings

from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.model_helpers import DraftConfigUpdatePreparer, NoUpdateQuerySet
from futurex_openedx_extensions.helpers.models import DraftConfig


class DummyManagingClass:
    """A dummy managing class to be used by DraftConfigUpdatePreparer."""
    def __init__(
        self, tenant_id, config_path, config_value, revision_id, created_by, updated_by,
    ):  # pylint: disable=too-many-arguments
        """Initialize the DummyManagingClass with given parameters."""
        self.tenant_id = tenant_id
        self.config_path = config_path
        self.config_value = config_value
        self.revision_id = revision_id
        self.created_by = created_by
        self.updated_by = updated_by

    @staticmethod
    def get_save_ready_config_value(value):
        """Simulate preparing a config value for saving."""
        return f'ready_{value}'

    @classmethod
    def json_load_config_value(cls, config_value):
        """Mock method to load JSON config value.
        """
        return config_value


@pytest.fixture
def mock_get_fast_access():
    """Fixture to mock get_fast_access to return a test dictionary."""
    with patch('futurex_openedx_extensions.helpers.model_helpers.DraftConfigUpdatePreparer.get_fast_access') as mock:
        mock.return_value = {
            'a.b': {'pk': 1, 'config_value': 'old_val1', 'revision_id': 100},
            'c.d': {'pk': 2, 'config_value': 'old_val2', 'revision_id': 200},
            'a.b.c': {'pk': 3, 'config_value': 'old_val3', 'revision_id': 300},
            'e.f': {'pk': 4, 'config_value': 'old_val4', 'revision_id': 400},
        }
        yield mock


@pytest.fixture
def sample_no_update_manager():
    """Fixture to create a sample model with NoUpdateQuerySet as manager."""
    class SampleModel(models.Model):
        """Sample model to test NoUpdateManager."""
        name = models.CharField(max_length=100)
        objects = NoUpdateQuerySet.as_manager()

        class Meta:
            app_label = 'fake_models'

    if 'fake_models_samplemodel' not in connection.introspection.table_names():
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(SampleModel)

    return SampleModel


@pytest.mark.django_db(transaction=True)
def test_no_update_manager_update_raises_error(sample_no_update_manager):  # pylint: disable=redefined-outer-name
    """Verify NoUpdateQuerySet raises AttributeError on .update()"""
    obj = sample_no_update_manager.objects.create(name='initial')

    with pytest.raises(AttributeError) as exc:
        sample_no_update_manager.objects.filter(pk=obj.pk).update(name='changed')

    assert 'SampleModel.objects.update() method is not allowed' in str(exc.value)


@pytest.mark.django_db(transaction=True)
def test_no_update_manager_update_works_with_override(sample_no_update_manager):  # pylint: disable=redefined-outer-name
    """Verify NoUpdateQuerySet.update works if the override flag is set"""
    obj = sample_no_update_manager.objects.create(name='initial')

    sample_no_update_manager.objects.filter(pk=obj.pk).allow_update().update(name='changed')
    obj.refresh_from_db()
    assert obj.name == 'changed', 'Object name should be updated when override flag is set'


@pytest.mark.django_db(transaction=True)
def test_no_update_manager_bulk_update_raises_error(sample_no_update_manager):  # pylint: disable=redefined-outer-name
    """Verify NoUpdateQuerySet raises AttributeError on .bulk_update()"""
    obj = sample_no_update_manager.objects.create(name='initial')
    obj.name = 'changed'
    with pytest.raises(AttributeError) as exc:
        sample_no_update_manager.objects.bulk_update([obj], ['name'])

    assert 'SampleModel.objects.bulk_update() method is not allowed' in str(exc.value)


@pytest.mark.django_db(transaction=True)
def test_no_update_manager_bulk_update_works_with_override(
    sample_no_update_manager,
):  # pylint: disable=redefined-outer-name
    """Verify NoUpdateQuerySet.bulk_update works if the override flag is set"""
    obj = sample_no_update_manager.objects.create(name='initial')
    obj.name = 'changed'
    sample_no_update_manager.objects.allow_update().bulk_update([obj], ['name'])
    obj.refresh_from_db()
    assert obj.name == 'changed', 'Object name should be updated when override flag is set'


@pytest.mark.django_db(transaction=True)
def test_no_update_manager_other_queryset_operations_work(
    sample_no_update_manager,
):  # pylint: disable=redefined-outer-name
    """Verify standard queryset methods still work (e.g., filter, get)"""
    obj = sample_no_update_manager.objects.create(name='test')

    queryset = sample_no_update_manager.objects.filter(name='test')
    assert queryset.exists(), 'Queryset should exist after filtering'
    assert queryset.first().id == obj.id, 'Filtered object should match the created object'

    retrieved = sample_no_update_manager.objects.get(pk=obj.pk)
    assert retrieved.name == 'test', 'Retrieved object should match the created object'

    assert not sample_no_update_manager.objects.exclude(pk=obj.pk).exists(), \
        'Excluding the created object should yield no results'


def test_get_to_create_valid():
    """Verify that get_to_create returns correct objects for a valid creation plan with multiple items."""
    preparer = DraftConfigUpdatePreparer(DummyManagingClass, tenant_id=3, user='user1')
    to_create_plan = {
        'a.b': {'new_config_value': 'val1', 'new_revision_id': 101},
        'c.d': {'new_config_value': 'val2', 'new_revision_id': 102},
    }
    result = preparer.get_to_create(to_create_plan)
    assert len(result) == 2
    assert result[0].tenant_id == 3
    assert result[0].config_path == 'a.b'
    assert result[0].config_value == 'ready_val1'
    assert result[0].revision_id == 101
    assert result[0].created_by == 'user1'
    assert result[1].config_path == 'c.d'
    assert result[1].config_value == 'ready_val2'


def test_get_to_create_empty_plan_raises():
    """Verify that get_to_create raises FXCodedException when given an empty creation plan."""
    preparer = DraftConfigUpdatePreparer(DummyManagingClass, tenant_id=1, user='user1')
    with pytest.raises(FXCodedException) as excinfo:
        preparer.get_to_create({})
    assert 'got nothing to create' in str(excinfo.value)
    assert excinfo.value.code == FXExceptionCodes.INVALID_INPUT.value


def test_get_to_update_raises_on_empty_plan():
    """Verify that get_to_update raises FXCodedException when given an empty update plan."""
    preparer = DraftConfigUpdatePreparer(DummyManagingClass, tenant_id=1, user='user1')
    with pytest.raises(FXCodedException) as excinfo:
        preparer.get_to_update({})
    assert 'got nothing to update' in str(excinfo.value)
    assert excinfo.value.code == FXExceptionCodes.INVALID_INPUT.value


def test_get_to_update_valid():
    """Verify that get_to_update returns correct update rules for multiple config paths."""
    preparer = DraftConfigUpdatePreparer(DummyManagingClass, tenant_id=1, user='user1')
    to_update_plan = {
        'a.b': {
            'current_revision_id': 0,
            'new_config_value': 'new_val1',
            'new_revision_id': 201,
        },
        'c.d': {
            'current_revision_id': -1,
            'new_config_value': 'new_val2',
            'new_revision_id': 202,
        },
    }
    result = preparer.get_to_update(to_update_plan)
    assert set(result.keys()) == {'config_value', 'revision_id', 'updated_by'}

    assert result['config_value'].cases[0].condition == Q(config_path='a.b', revision_id=0), \
        'condition should include revision_id for non-negative current_revision_id'
    assert result['config_value'].cases[0].result.value == 'ready_new_val1'
    assert result['revision_id'].cases[0].result.value == 201
    assert result['updated_by'] == 'user1'

    assert result['config_value'].cases[1].condition == Q(config_path='c.d'), \
        'condition should not include revision_id for negative current_revision_id'
    assert result['config_value'].cases[1].result.value == 'ready_new_val2'
    assert result['revision_id'].cases[1].result.value == 202
    assert result['updated_by'] == 'user1'

    assert result['revision_id'].default == Value(None)


def test_get_prevent_default_config_value():
    """Verify that get_prevent_default_config_value returns None."""
    assert DraftConfigUpdatePreparer.get_prevent_default_config_value() is None


def test_get_to_delete_empty_plan_raises():
    """Verify that get_to_delete raises FXCodedException when given an empty creation plan."""
    preparer = DraftConfigUpdatePreparer(DummyManagingClass, tenant_id=1, user='user1')
    with pytest.raises(FXCodedException) as excinfo:
        preparer.get_to_delete({})
    assert 'got nothing to delete' in str(excinfo.value)
    assert excinfo.value.code == FXExceptionCodes.INVALID_INPUT.value


def test_get_to_delete_valid():
    """Verify that get_to_delete returns correct Q objects for multiple config paths."""
    preparer = DraftConfigUpdatePreparer(DummyManagingClass, tenant_id=1, user='user1')
    to_delete_plan = {
        'a.b': {'current_revision_id': 0},
        'c.d': {'current_revision_id': -1},
    }
    result = preparer.get_to_delete(to_delete_plan)
    assert len(result.children) == 2
    assert result.children[0] == Q(config_path='a.b', revision_id=0)
    assert result.children[1] == ('config_path', 'c.d')


@pytest.mark.django_db
def test_get_fast_access(base_data):  # pylint: disable=unused-argument
    """Verify that get_fast_access returns correct mapping of config paths to values."""
    user10 = get_user_model().objects.get(username='user10')
    test_data = [
        {
            'pk': 1, 'tenant_id': 2, 'config_path': 'config.path1',
            'config_value': 'value1', 'revision_id': 101,
        },
        {
            'pk': 2, 'tenant_id': 1, 'config_path': 'config.path1',
            'config_value': 'value2', 'revision_id': 102,
        },
        {
            'pk': 3, 'tenant_id': 1, 'config_path': 'config.path3',
            'config_value': 'value3', 'revision_id': 103,
        },
        {
            'pk': 4, 'tenant_id': 1, 'config_path': 'config.path4',
            'config_value': 'value4', 'revision_id': 104,
        },
    ]
    bulk_data = []
    for data in test_data:
        bulk_data.append(DraftConfig(
            tenant_id=data['tenant_id'],
            config_path=data['config_path'],
            config_value=data['config_value'],
            revision_id=data['revision_id'],
            created_by=user10,
            updated_by=user10,
        ))
    DraftConfig.objects.bulk_create(bulk_data)
    assert DraftConfig.objects.count() == 4, 'should have 4 draft config records'

    preparer = DraftConfigUpdatePreparer(DraftConfig, tenant_id=1, user=user10)
    config_paths = ['config.path1', 'config.path3', 'non.existent']
    result = preparer.get_fast_access(tenant_id=1, config_paths=config_paths)
    assert len(result) == 2, 'should return 2 existing config paths for tenant_id=1'
    assert result == {
        'config.path1': {
            'pk': 2,
            'config_value': 'value2',
            'revision_id': 102,
        },
        'config.path3': {
            'pk': 3,
            'config_value': 'value3',
            'revision_id': 103,
        },
    }


@pytest.mark.parametrize('config_paths', [
    ['a.b', ''],
    ['a.b', None],
])
def test_get_update_plan_empty_config_path(
    mock_get_fast_access, config_paths,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify that get_update_plan raises FXCodedException when config_paths contains an empty path."""
    preparer = DraftConfigUpdatePreparer(DummyManagingClass, tenant_id=1, user='user1')
    with pytest.raises(FXCodedException) as excinfo:
        preparer.get_update_plan(tenant_id=1, config_paths=config_paths, src={'a.b': 'val1'})
    assert 'got empty config_path' in str(excinfo.value)
    assert excinfo.value.code == FXExceptionCodes.INVALID_INPUT.value


@pytest.mark.django_db
@pytest.mark.parametrize(
    'in_draft, in_config_paths, in_src, expected_with_verify, expected_without_verify, expected_when_disable_verify', [
        [False, False, False, {}, {}, {}],
        [False, False, True, {}, {}, {}],
        [False, True, False, {}, {}, {}],
        [
            False, True, True,
            {'to_create': {'a.b': {'new_config_value': 'new_val1', 'new_revision_id': 99}}},
            {'to_create': {'a.b': {'new_config_value': 'new_val1', 'new_revision_id': 99}}},
            {'to_create': {'a.b': {'new_config_value': 'new_val1', 'new_revision_id': 99}}},
        ],
        [True, False, False, {}, {}, {}],
        [True, False, True, {}, {}, {}],
        [
            True, True, False,
            {'to_delete': {'a.b': {'current_revision_id': 123}}},
            {'to_delete': {'a.b': {'current_revision_id': 100}}},
            {'to_delete': {'a.b': {'current_revision_id': -1}}},
        ],
        [
            True, True, True,
            {
                'to_update': {
                    'a.b': {'pk': 1, 'current_revision_id': 123, 'new_config_value': 'new_val1', 'new_revision_id': 99},
                },
            },
            {
                'to_update': {
                    'a.b': {'pk': 1, 'current_revision_id': 100, 'new_config_value': 'new_val1', 'new_revision_id': 99},
                },
            },
            {
                'to_update': {
                    'a.b': {'pk': 1, 'current_revision_id': -1, 'new_config_value': 'new_val1', 'new_revision_id': 99},
                },
            },
        ],
    ]
)
@patch('futurex_openedx_extensions.helpers.models.DraftConfig.generate_revision_id', return_value=99)
def test_get_update_plan_create_valid(
    _, in_draft, in_config_paths, in_src, expected_with_verify, expected_without_verify, expected_when_disable_verify,
):  # pylint: disable=too-many-arguments. too-many-locals
    """Verify that get_update_plan returns correct plan based on draft presence, config paths, and source data."""
    user10 = get_user_model().objects.get(username='user10')
    preparer = DraftConfigUpdatePreparer(DraftConfig, tenant_id=1, user=user10)
    revision_id = 100

    assert DraftConfig.objects.count() == 0, 'should start with no draft config records'
    if in_draft:
        DraftConfig.objects.create(
            tenant_id=1,
            config_path='a.b',
            config_value='old_val1',
            revision_id=revision_id,
            created_by=user10,
            updated_by=user10,
        )

    if in_config_paths:
        config_paths = ['a.b']
    else:
        config_paths = []

    if in_src:
        src_tests = [{
            'a': {
                'b': 'new_val1',
            },
        }]
    else:
        src_tests = [{}, {'a': {}}, {'a': {'b': None}}, {'a': 'a is not a dict'}]

    for src in src_tests:
        full_expected_result = {
            'to_create': {},
            'to_update': {},
            'to_delete': {},
        }
        if expected_without_verify:
            update_key = list(expected_without_verify.keys())[0]
            full_expected_result[update_key] = expected_without_verify[update_key]

        for verify_revision_ids in (None, {}, {'a.b.some.other.path': 444}):
            result = preparer.get_update_plan(
                tenant_id=1,
                config_paths=config_paths,
                src=src,
                verify_revision_ids=verify_revision_ids,
            )
            assert not DeepDiff(result, full_expected_result), \
                f'Failed in_draft={in_draft}, in_config_paths={in_config_paths}, in_src={in_src}, ' \
                f'verify_revision_ids={verify_revision_ids}\n\n' \
                f'src={src}\n\n' \
                f'expected:\n{full_expected_result}\n\ngot:\n{result}'

        verify_revision_ids = {'a.b': 123}
        for disable_verify, expected_result in ((False, expected_with_verify), (True, expected_when_disable_verify)):
            full_expected_result = {
                'to_create': {},
                'to_update': {},
                'to_delete': {},
            }
            if expected_result:
                update_key = list(expected_result.keys())[0]
                full_expected_result[update_key] = expected_result[update_key]

            with override_settings(FX_DISABLE_CONFIG_VALIDATIONS=disable_verify):
                result = preparer.get_update_plan(
                    tenant_id=1,
                    config_paths=config_paths,
                    src=src,
                    verify_revision_ids=verify_revision_ids,
                )
            assert not DeepDiff(result, full_expected_result), \
                f'Failed in_draft={in_draft}, in_config_paths={in_config_paths}, in_src={in_src}, ' \
                f'verify_revision_ids={verify_revision_ids}\n\n' \
                f'src={src}\n\n' \
                f'FX_DISABLE_CONFIG_VALIDATIONS={disable_verify}\n\n' \
                f'expected:\n{full_expected_result}\n\ngot:\n{result}'


def test_get_update_plan_no_update_for_same_value(
    mock_get_fast_access,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify that get_update_plan will not plan an update if the value is the same."""
    preparer = DraftConfigUpdatePreparer(DummyManagingClass, tenant_id=1, user='user1')
    result = preparer.get_update_plan(
        tenant_id=1,
        config_paths=['a.b', 'c.d'],
        src={'a': {'b': 'old_val1'}, 'c': {'d': 'old_val2'}},
    )
    assert result == {
        'to_create': {},
        'to_update': {},
        'to_delete': {},
    }
