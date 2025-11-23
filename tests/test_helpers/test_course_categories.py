"""Tests for futurex_openedx_extensions.helpers.course_categories."""
import logging
from unittest.mock import Mock, patch

import pytest
from django.test import override_settings

from futurex_openedx_extensions.helpers import course_categories as module
from futurex_openedx_extensions.helpers.course_categories import CourseCategories
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes


@pytest.fixture
def patched_config_loader():
    """Patch get_tenant_config_value and set_tenant_config_value."""
    with patch.object(module, 'get_tenant_config_value') as mock_get, \
         patch.object(module, 'set_tenant_config_value') as mock_set:
        mock_get.return_value = {
            'categories': {
                'featured': {
                    'label': {'en': 'Featured'},
                    'courses': ['course-v1:edX+DemoX+2025'],
                },
            },
            'sorting': ['featured'],
        }
        yield mock_get, mock_set


@pytest.mark.parametrize(
    'courses, expected, test_case',
    [
        (['course-v1:x+Y+Z'], ['course-v1:x+Y+Z'], 'single valid course'),
        (['course-v1:x+Y+Z', 'course-v1:A+B+C'], ['course-v1:x+Y+Z', 'course-v1:A+B+C'], 'multiple valid'),
        ([], [], 'empty'),
    ],
)
def test_validated_courses_valid(
    courses, expected, test_case, patched_config_loader,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify validated_courses returns the same list when all courses are valid."""
    result = CourseCategories.validated_courses(courses)
    assert result == expected, test_case


@pytest.mark.parametrize(
    'courses, error_msg, test_case',
    [
        ([123], 'course_id is not a string: 123', 'not a string'),
        (['course-v1:org+cs101+2025', 5], 'course_id is not a string: 5', 'mixed invalid'),
        (
            ['course-v1:org+cs101+2025', 'course-v2:org+cs101+2025'],
            'course_id is not valid: course-v2:org+cs101+2025',
            'invalid course format',
        ),
    ],
)
def test_validated_courses_raises_invalid_type(
    courses, error_msg, test_case, patched_config_loader,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify validated_courses raises FXCodedException when a non-string appears and silent_fail=False."""
    with pytest.raises(FXCodedException) as exc:
        CourseCategories.validated_courses(courses, silent_fail=False)

    assert exc.value.code == FXExceptionCodes.COURSE_CATEGORY_INVALID_SETTINGS.value, test_case
    assert str(exc.value) == error_msg, test_case


@pytest.mark.parametrize(
    'courses, error_log_msg, expected_result, test_case',
    [
        ([123], 'course_id is not a string: 123', [], 'not a string'),
        (['course-v1:org+cs9+2025', 5], 'course_id is not a string: 5', ['course-v1:org+cs9+2025'], 'mixed invalid'),
        (
            ['course-v1:org+cs101+2025', 'course-v2:org+cs101+2025'],
            'course_id is not valid: course-v2:org+cs101+2025',
            ['course-v1:org+cs101+2025'],
            'invalid course format',
        ),
    ],
)
def test_validated_courses_silent_fail_logs(
    courses, error_log_msg, expected_result, test_case, patched_config_loader, caplog,
):  # pylint: disable=unused-argument, redefined-outer-name, too-many-arguments
    """Verify silent_fail=True logs but ignores invalid formats."""
    caplog.set_level(logging.ERROR)
    result = CourseCategories.validated_courses(courses, silent_fail=True)

    assert result == expected_result
    assert any(error_log_msg in msg for msg in caplog.messages)


def test_reformat_categories_and_sorting_normalizes(
    patched_config_loader,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify reformat_categories_and_sorting filters unknown sorting and invalid course IDs."""
    course_cat = CourseCategories(tenant_id=1)

    with patch.object(module, 'COURSE_ID_REGX_EXACT', r'^ok:.+$'):
        categories = {
            'cat1': {'label': {'en': 'One'}, 'courses': ['ok:1', 'bad']},
            'cat2': {'label': {'en': 'Two'}, 'courses': ['ok:2']},
        }
        course_cat.reformat_categories_and_sorting(categories, ['cat2', 'unknown'])

    assert course_cat.sorting == ['cat2', 'cat1']
    assert course_cat.categories['cat1']['courses'] == ['ok:1']
    assert course_cat.categories['cat2']['courses'] == ['ok:2']


def test_reformat_categories_raises_when_courses_not_list(
    patched_config_loader,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify reformat_categories_and_sorting raises when courses is not a list."""
    course_cat = CourseCategories(1)
    categories = {
        'bad': {
            'label': {'en': 'Bad'},
            'courses': 'not list',
        },
    }

    with pytest.raises(FXCodedException) as exc:
        course_cat.reformat_categories_and_sorting(categories, [])

    assert exc.value.code == FXExceptionCodes.COURSE_CATEGORY_INVALID_SETTINGS.value
    assert str(exc.value) == 'Courses for category bad must be a list. tenant_id: 1'


def test_init_raises_when_get_config_fails():
    """Verify initialization wraps get_tenant_config_value errors into INVALID_SETTINGS."""
    failing = Mock(side_effect=FXCodedException(
        code=FXExceptionCodes.COURSE_CATEGORY_INVALID_SETTINGS.value,
        message='fail',
    ))

    with patch.object(module, 'get_tenant_config_value', failing):
        with pytest.raises(FXCodedException) as exc:
            CourseCategories(1)

    assert exc.value.code == FXExceptionCodes.COURSE_CATEGORY_INVALID_SETTINGS.value
    assert 'initialization failed' in str(exc.value)


def test_save_read_only(patched_config_loader):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify save raises READ_ONLY error when in read-only mode."""
    course_cat = CourseCategories(1, open_as_read_only=True)

    with pytest.raises(FXCodedException) as exc:
        course_cat.save()

    assert exc.value.code == FXExceptionCodes.COURSE_CATEGORY_READ_ONLY.value


def test_save_writes_fine(patched_config_loader, settings):  # pylint: disable=redefined-outer-name
    """Verify save delegates to set_tenant_config_value correctly."""
    _, set_mock = patched_config_loader

    course_cat = CourseCategories(42, open_as_read_only=False)
    course_cat.categories['featured']['courses'] = ['course-v1:new+X+Y']
    course_cat.sorting = ['featured']

    course_cat.save()

    set_mock.assert_called_once_with(
        tenant_id=42,
        config_key=settings.FX_COURSE_CATEGORY_CONFIG_KEY,
        value={
            'categories': course_cat.categories,
            'sorting': course_cat.sorting,
        },
    )


def test_verify_category_name_exists_raises(
    patched_config_loader,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify verify_category_name_exists raises for missing category."""
    course_cat = CourseCategories(1)
    course_cat.categories = {'a': {'label': {}, 'courses': []}}

    with pytest.raises(FXCodedException) as exc:
        course_cat.verify_category_name_exists('missing')

    assert exc.value.code == FXExceptionCodes.COURSE_CATEGORY_INVALID_SETTINGS.value


def test_verify_category_name_exists_ok(
    patched_config_loader,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify verify_category_name_exists succeeds for existing category."""
    course_cat = CourseCategories(1)
    course_cat.categories = {'a': {'label': {}, 'courses': []}}

    course_cat.verify_category_name_exists('a')


def test_set_courses_for_category_validates(
    patched_config_loader,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify set_courses_for_category uses validated_courses."""
    fake = Mock(return_value=['canon'])

    with patch.object(CourseCategories, 'validated_courses', staticmethod(fake)):
        course_cat = CourseCategories(1)
        fake.assert_called_once()
        fake.reset_mock()
        course_cat.categories = {'x': {'label': {'en': 'X'}, 'courses': []}}

        course_cat.set_courses_for_category('x', ['a', 'b'])

        fake.assert_called_once_with(['a', 'b'])
        assert course_cat.categories['x']['courses'] == ['canon']


def test_get_category_success(patched_config_loader):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify get_category returns the stored category."""
    course_cat = CourseCategories(1)
    data = {'label': {'en': 'X'}, 'courses': ['c']}
    course_cat.categories = {'x': data}

    assert course_cat.get_category('x') is data


def test_get_category_missing(patched_config_loader):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify get_category raises when missing."""
    course_cat = CourseCategories(1)
    course_cat.categories = {}

    with pytest.raises(FXCodedException) as exc:
        course_cat.get_category('missing')

    assert exc.value.code == FXExceptionCodes.COURSE_CATEGORY_INVALID_SETTINGS.value


@pytest.mark.parametrize(
    'existing, expected, test_case',
    [
        ({}, 'category_1', 'no categories'),
        ({'category_1': {}, 'category_3': {}}, 'category_2', 'first missing'),
    ],
)
def test_get_new_category_name(
    existing, expected, test_case, patched_config_loader,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify get_new_category_name returns the first unused name."""
    course_cat = CourseCategories(1)
    course_cat.categories = existing

    assert course_cat.get_new_category_name() == expected, test_case


@pytest.mark.parametrize(
    'existing_count, test_case',
    [
        (5, 'at limit'),
        (10, 'over limit'),
    ],
)
@override_settings(FX_COURSE_CATEGORY_NAME_MAX_LENGTH=5)
def test_get_new_category_name_too_many(
    existing_count, test_case, patched_config_loader,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify get_new_category_name raises when too many categories exist."""
    course_cat = CourseCategories(1)
    course_cat.categories = {f'category_{i}': {} for i in range(1, existing_count + 1)}

    with pytest.raises(FXCodedException) as exc_info:
        course_cat.get_new_category_name()
    assert exc_info.value.code == FXExceptionCodes.COURSE_CATEGORY_TOO_MANY_CATEGORIES.value, test_case
    assert str(exc_info.value) == 'Unable to generate a new unique category name!', test_case


@override_settings(FX_COURSE_CATEGORY_NAME_MAX_LENGTH=1)
def test_get_new_category_name_bad_settings_value(
    patched_config_loader,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify get_new_category_name raises and error when FX_COURSE_CATEGORY_NAME_MAX_LENGTH is less than 2."""
    course_cat = CourseCategories(1)
    course_cat.categories = {}

    with pytest.raises(FXCodedException) as exc_info:
        course_cat.get_new_category_name()
    assert exc_info.value.code == FXExceptionCodes.COURSE_CATEGORY_TOO_MANY_CATEGORIES.value
    assert str(exc_info.value) == 'Unable to generate a new unique category name!'


@patch.object(CourseCategories, 'validated_courses', return_value=['c'])
def test_add_category(
    mock_validate_courses, patched_config_loader,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify add_category creates a category and returns its name."""
    course_cat = CourseCategories(1)
    course_cat.categories = {}
    course_cat.sorting = []
    mock_validate_courses.assert_called_once()

    mock_validate_courses.reset_mock()
    with patch.object(course_cat, 'get_new_category_name', return_value='category_1'):
        name = course_cat.add_category({'en': 'Hello'}, ['c'])

    assert name == 'category_1'
    assert 'category_1' in course_cat.categories
    assert 'category_1' in course_cat.sorting
    mock_validate_courses.assert_called_once_with(['c'])


def test_remove_category(patched_config_loader):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify remove_category deletes category and re-normalizes sorting."""
    course_cat = CourseCategories(1)
    course_cat.categories = {
        'a': {'label': {}, 'courses': []},
        'b': {'label': {}, 'courses': []},
    }
    course_cat.sorting = ['a', 'b']

    course_cat.remove_category('a')

    assert 'a' not in course_cat.categories
    assert course_cat.sorting == ['b']


def test_set_categories_sorting(patched_config_loader):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify set_categories_sorting updates sorting correctly."""
    course_cat = CourseCategories(1)
    course_cat.categories = {
        'a': {'label': {}, 'courses': []},
        'b': {'label': {}, 'courses': []},
        'c': {'label': {}, 'courses': []},
    }
    course_cat.sorting = ['a', 'b', 'c']

    course_cat.set_categories_sorting(['c', 'unknown'])

    assert course_cat.sorting == ['c', 'a', 'b']


@pytest.mark.parametrize(
    'course_id, expected, test_case',
    [
        (
            'course-v1:org+course1+2025',
            {'cat1': {'label': {'en': 'Category 1'}}, 'cat3': {'label': {'en': 'Category 3'}}},
            'course in multiple categories',
        ),
        ('course-v1:org+course2+2025', {'cat2': {'label': {'en': 'Category 2'}}}, 'course in single category'),
        ('course-v1:org+course99+2025', {}, 'course not in any category'),
    ],
)
def test_get_categories_for_course(
    course_id, expected, test_case, patched_config_loader,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify get_categories_for_course returns correct categories for a course."""
    course_cat = CourseCategories(1)
    course_cat.categories = {
        'cat1': {'label': {'en': 'Category 1'}, 'courses': ['course-v1:org+course1+2025']},
        'cat2': {'label': {'en': 'Category 2'}, 'courses': ['course-v1:org+course2+2025']},
        'cat3': {'label': {'en': 'Category 3'}, 'courses': ['course-v1:org+course1+2025']},
    }

    result = course_cat.get_categories_for_course(course_id)

    assert result == expected, test_case


def test_get_categories_for_course_excludes_courses_list(
    patched_config_loader,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify get_categories_for_course returns only label without courses list."""
    course_cat = CourseCategories(1)
    course_cat.categories = {
        'cat1': {
            'label': {'en': 'Category 1'},
            'courses': ['course-v1:org+course1+2025', 'course-v1:org+course2+2025'],
        },
    }

    result = course_cat.get_categories_for_course('course-v1:org+course1+2025')

    assert 'cat1' in result
    assert 'courses' not in result['cat1']
    assert result['cat1'] == {'label': {'en': 'Category 1'}}


def test_set_categories_for_course_adds_to_new_categories(
    patched_config_loader,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify set_categories_for_course adds course to specified categories."""
    course_cat = CourseCategories(1)
    course_cat.categories = {
        'cat1': {'label': {'en': 'Category 1'}, 'courses': []},
        'cat2': {'label': {'en': 'Category 2'}, 'courses': []},
        'cat3': {'label': {'en': 'Category 3'}, 'courses': []},
    }

    course_cat.set_categories_for_course('course-v1:org+course1+2025', ['cat1', 'cat3'])

    assert 'course-v1:org+course1+2025' in course_cat.categories['cat1']['courses']
    assert 'course-v1:org+course1+2025' not in course_cat.categories['cat2']['courses']
    assert 'course-v1:org+course1+2025' in course_cat.categories['cat3']['courses']


def test_set_categories_for_course_removes_from_old_categories(
    patched_config_loader,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify set_categories_for_course removes course from categories not in the new list."""
    course_cat = CourseCategories(1)
    course_cat.categories = {
        'cat1': {'label': {'en': 'Category 1'}, 'courses': ['course-v1:org+course1+2025']},
        'cat2': {'label': {'en': 'Category 2'}, 'courses': ['course-v1:org+course1+2025']},
        'cat3': {'label': {'en': 'Category 3'}, 'courses': []},
    }

    course_cat.set_categories_for_course('course-v1:org+course1+2025', ['cat2', 'cat3'])

    assert 'course-v1:org+course1+2025' not in course_cat.categories['cat1']['courses']
    assert 'course-v1:org+course1+2025' in course_cat.categories['cat2']['courses']
    assert 'course-v1:org+course1+2025' in course_cat.categories['cat3']['courses']


def test_set_categories_for_course_handles_duplicates(
    patched_config_loader,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify set_categories_for_course deduplicates category names."""
    course_cat = CourseCategories(1)
    course_cat.categories = {
        'cat1': {'label': {'en': 'Category 1'}, 'courses': []},
        'cat2': {'label': {'en': 'Category 2'}, 'courses': []},
    }

    course_cat.set_categories_for_course('course-v1:org+course1+2025', ['cat1', 'cat1', 'cat2'])

    assert course_cat.categories['cat1']['courses'].count('course-v1:org+course1+2025') == 1
    assert course_cat.categories['cat2']['courses'].count('course-v1:org+course1+2025') == 1


def test_set_categories_for_course_raises_for_invalid_category(
    patched_config_loader,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify set_categories_for_course raises when category doesn't exist."""
    course_cat = CourseCategories(1)
    course_cat.categories = {
        'cat1': {'label': {'en': 'Category 1'}, 'courses': []},
    }

    with pytest.raises(FXCodedException) as exc:
        course_cat.set_categories_for_course('course-v1:org+course1+2025', ['cat1', 'nonexistent'])

    assert exc.value.code == FXExceptionCodes.COURSE_CATEGORY_INVALID_SETTINGS.value


def test_set_categories_for_course_removes_all_when_empty_list(
    patched_config_loader,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify set_categories_for_course removes course from all categories when given empty list."""
    course_cat = CourseCategories(1)
    course_cat.categories = {
        'cat1': {'label': {'en': 'Category 1'}, 'courses': ['course-v1:org+course1+2025']},
        'cat2': {'label': {'en': 'Category 2'}, 'courses': ['course-v1:org+course1+2025']},
    }

    course_cat.set_categories_for_course('course-v1:org+course1+2025', [])

    assert 'course-v1:org+course1+2025' not in course_cat.categories['cat1']['courses']
    assert 'course-v1:org+course1+2025' not in course_cat.categories['cat2']['courses']


def test_set_categories_for_course_idempotent(
    patched_config_loader,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify set_categories_for_course is idempotent when called with same categories."""
    course_cat = CourseCategories(1)
    course_cat.categories = {
        'cat1': {'label': {'en': 'Category 1'}, 'courses': ['course-v1:org+course1+2025']},
        'cat2': {'label': {'en': 'Category 2'}, 'courses': []},
    }

    course_cat.set_categories_for_course('course-v1:org+course1+2025', ['cat1'])

    assert course_cat.categories['cat1']['courses'] == ['course-v1:org+course1+2025']
    assert course_cat.categories['cat2']['courses'] == []
