"""Test library helpers"""
from unittest.mock import patch

import pytest

from futurex_openedx_extensions.helpers.library import get_accessible_libraries


@patch('futurex_openedx_extensions.helpers.library.get_partial_access_course_ids')
def test_get_accessible_libraries_full_access(mocked_get_partial_ids):  # pylint: disable=unused-argument
    """Test that libraries are returned when the user has full access."""
    results = get_accessible_libraries({
        'view_allowed_full_access_orgs': ['org1'],
        'view_allowed_course_access_orgs': [],
    })
    assert len(results) == 2

    returned_lib_ids = [str(lib.location.library_key) for lib in results]
    assert 'library-v1:org1+11' in returned_lib_ids
    assert 'library-v1:org1+22' in returned_lib_ids


@pytest.mark.parametrize('usecase, mock_return, access_data, expected', [
    (
        'Empty partial access list',
        [],
        {'view_allowed_full_access_orgs': [], 'view_allowed_course_access_orgs': ['org5']},
        [],
    ),
    (
        'Partial access to a different org',
        ['library-v1:org1+other'],
        {'view_allowed_full_access_orgs': [], 'view_allowed_course_access_orgs': ['org5']},
        [],
    ),
    (
        'Partial access includes target org',
        ['library-v1:org1+other', 'library-v1:org5+11'],
        {'view_allowed_full_access_orgs': [], 'view_allowed_course_access_orgs': ['org5']},
        ['library-v1:org5+11'],
    ),
])
@patch('futurex_openedx_extensions.helpers.library.get_partial_access_course_ids')
def test_get_accessible_libraries_partial_access(mocked_get_partial_ids, usecase, mock_return, access_data, expected):
    """Test that libraries are returned when the user has partial access"""
    mocked_get_partial_ids.return_value = mock_return
    results = get_accessible_libraries(access_data)
    returned_lib_ids = [str(lib.location.library_key) for lib in results]
    assert returned_lib_ids == expected, f'Failed: {usecase} | Expected: {expected}, Got: {results}'


@patch('futurex_openedx_extensions.helpers.library.get_partial_access_course_ids')
def test_get_accessible_libraries(mocked_get_partial_ids):
    """Test that libraries are returned when the user has partial access to a library along with full access to org."""
    mocked_get_partial_ids.return_value = ['library-v1:org1+11']
    results = get_accessible_libraries({
        'view_allowed_full_access_orgs': ['org5'],
        'view_allowed_course_access_orgs': ['org1'],
    })
    assert len(results) == 2
    returned_lib_ids = [str(lib.location.library_key) for lib in results]
    assert 'library-v1:org1+11' in returned_lib_ids
    assert 'library-v1:org5+11' in returned_lib_ids


@patch('futurex_openedx_extensions.helpers.library.get_partial_access_course_ids')
def test_get_accessible_libraries_filtered_by_search_text(mock_get_partial_access):  # pylint: disable=unused-argument
    """Test that libraries are filtered by search text."""
    results = get_accessible_libraries({
        'view_allowed_full_access_orgs': ['org5', 'org1'],
    })
    assert len(results) == 3

    results = get_accessible_libraries({'view_allowed_full_access_orgs': ['org5', 'org1']}, search_text='one')
    assert len(results) == 2
    returned_lib_ids = [str(lib.location.library_key) for lib in results]
    assert 'library-v1:org1+11' in returned_lib_ids
    assert 'library-v1:org5+11' in returned_lib_ids

    results = get_accessible_libraries({'view_allowed_full_access_orgs': ['org5', 'org1']}, search_text='not-exist')
    assert len(results) == 0
