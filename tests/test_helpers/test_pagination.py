"""Tests for pagination helpers"""
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import QuerySet
from django.test.utils import CaptureQueriesContext
from lms.djangoapps.certificates.models import GeneratedCertificate
from lms.djangoapps.courseware.models import StudentModule
from rest_framework.pagination import PageNumberPagination

from futurex_openedx_extensions.dashboard.details.learners import get_learners_by_course_queryset
from futurex_openedx_extensions.helpers.pagination import (
    AnnotateAfterPagination,
    AnnotateAfterPaginationPaginator,
    DefaultPagination,
    DefaultPaginator,
)


def test_default_pagination():
    """Verify that the DefaultPagination class is correctly defined."""
    assert issubclass(DefaultPagination, PageNumberPagination)
    assert DefaultPagination.page_size == 20
    assert DefaultPagination.page_size_query_param == 'page_size'
    assert DefaultPagination.max_page_size == 100
    assert DefaultPagination.django_paginator_class == DefaultPaginator


@patch('futurex_openedx_extensions.helpers.pagination.Paginator.count', new_callable=PropertyMock)
@patch('futurex_openedx_extensions.helpers.pagination.verify_queryset_removable_annotations')
def test_count_with_query_set_and_removable_annotations(mock_verify, mock_super_count):
    """Verify that the count property is correctly defined."""
    mock_super_count.return_value = 'should not be reached'

    mock_queryset = MagicMock(spec=QuerySet)
    mock_queryset.removable_annotations = {'annotation1'}
    mock_queryset._chain.return_value = mock_queryset  # pylint: disable=protected-access
    mock_queryset.query.annotations = {'annotation1': None, 'annotation2': None}
    mock_queryset.count.return_value = 5

    paginator = DefaultPaginator(mock_queryset, per_page=10)

    assert paginator.count == 5
    assert 'annotation1' not in mock_queryset.query.annotations
    mock_super_count.assert_not_called()
    mock_verify.assert_called_once_with(mock_queryset)


@patch('futurex_openedx_extensions.helpers.pagination.Paginator.count', new_callable=PropertyMock)
@patch('futurex_openedx_extensions.helpers.pagination.verify_queryset_removable_annotations')
def test_count_with_query_set_no_removable_annotations(mock_verify, mock_super_count):
    """Verify that the count property is correctly defined."""
    mock_super_count.return_value = 44

    mock_queryset = MagicMock(spec=QuerySet)
    del mock_queryset.removable_annotations
    mock_queryset.count.return_value = 'should not be reached'
    mock_queryset.query.annotations = {'annotation1': None, 'annotation2': None}

    paginator = DefaultPaginator(mock_queryset, per_page=10)

    assert paginator.count == mock_super_count.return_value
    assert mock_queryset.query.annotations == {'annotation1': None, 'annotation2': None}
    mock_verify.assert_not_called()


@patch('futurex_openedx_extensions.helpers.pagination.Paginator.count', new_callable=PropertyMock)
@patch('futurex_openedx_extensions.helpers.pagination.verify_queryset_removable_annotations')
def test_count_with_not_query_set(mock_verify, mock_super_count):
    """Verify that the count property is correctly defined."""
    mock_super_count.return_value = 44

    object_list = 'not a queryset'
    paginator = DefaultPaginator(object_list, per_page=10)

    assert paginator.count == mock_super_count.return_value
    mock_verify.assert_not_called()


def test_annotate_after_pagination():
    """Verify that AnnotateAfterPagination keeps the default settings and uses its own paginator."""
    assert issubclass(AnnotateAfterPagination, DefaultPagination)
    assert AnnotateAfterPagination.page_size == 20
    assert AnnotateAfterPagination.django_paginator_class == AnnotateAfterPaginationPaginator
    assert issubclass(AnnotateAfterPaginationPaginator, DefaultPaginator)


def _page_rows(page):
    """Return (id, certificate_available, course_score, active_in_course) for each row of the page."""
    return [(row.id, row.certificate_available, row.course_score, row.active_in_course) for row in page]


@pytest.mark.django_db
@pytest.mark.parametrize('per_page, number', [(2, 1), (2, 2), (1, 3), (20, 1)])
def test_annotate_after_page_matches_default_page(base_data, per_page, number):  # pylint: disable=unused-argument
    """Verify that the page holds the same rows, order and annotation values as the default paginator."""
    queryset = get_learners_by_course_queryset(course_id='course-v1:ORG1+5+5')

    expected = DefaultPaginator(queryset, per_page=per_page).page(number)
    result = AnnotateAfterPaginationPaginator(queryset, per_page=per_page).page(number)

    assert _page_rows(result) == _page_rows(expected)
    assert len(result) > 0
    assert result.paginator.count == expected.paginator.count == 3
    assert result.has_next() == expected.has_next()


@pytest.mark.django_db
def test_annotate_after_page_annotations_only_for_page_ids(base_data):  # pylint: disable=unused-argument
    """Verify that the ids query has no annotation subqueries and the annotated query is limited to the page ids."""
    queryset = get_learners_by_course_queryset(course_id='course-v1:ORG1+5+5')
    paginator = AnnotateAfterPaginationPaginator(queryset, per_page=2)
    assert paginator.count == 3

    with CaptureQueriesContext(connection) as captured:
        page = paginator.page(1)

    sqls = [query['sql'] for query in captured.captured_queries]
    student_module_table = StudentModule._meta.db_table
    certificate_table = GeneratedCertificate._meta.db_table
    assert len(sqls) == 2
    assert student_module_table not in sqls[0]
    assert certificate_table not in sqls[0]
    assert student_module_table in sqls[1]
    assert '"auth_user"."id" IN (' in sqls[1]
    assert len(page) == 2


@pytest.mark.django_db
def test_annotate_after_page_empty(base_data):  # pylint: disable=unused-argument
    """Verify that a course without learners gives an empty first page."""
    queryset = get_learners_by_course_queryset(course_id='course-v1:ORG1+999+999')

    page = AnnotateAfterPaginationPaginator(queryset, per_page=20).page(1)

    assert not list(page)
    assert page.paginator.count == 0


@pytest.mark.django_db
def test_annotate_after_page_skips_rows_gone_between_queries(base_data):  # pylint: disable=unused-argument
    """Verify that a row that no longer matches when the page is fetched is left out instead of failing."""
    queryset = get_learners_by_course_queryset(course_id='course-v1:ORG1+5+5')
    paginator = AnnotateAfterPaginationPaginator(queryset, per_page=20)
    assert paginator.count == 3
    first_id = DefaultPaginator(queryset, per_page=20).page(1)[0].id

    original_filter = QuerySet.filter

    def filter_and_drop_first(self, *args, **kwargs):
        """Drop the first page row from the annotated query, as if it had just been unenrolled."""
        return original_filter(self, *args, **kwargs).exclude(id=first_id) if 'pk__in' in kwargs else original_filter(
            self, *args, **kwargs,
        )

    with patch.object(QuerySet, 'filter', filter_and_drop_first):
        page = paginator.page(1)

    assert [row.id for row in page] == [row.id for row in DefaultPaginator(queryset, per_page=20).page(1)][1:]


@patch('futurex_openedx_extensions.helpers.pagination.DefaultPaginator.page')
def test_annotate_after_page_not_queryset(mock_super_page):
    """Verify that a plain list falls back to the default page."""
    paginator = AnnotateAfterPaginationPaginator([1, 2, 3], per_page=2)

    assert paginator.page(1) == mock_super_page.return_value
    mock_super_page.assert_called_once_with(1)


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.pagination.DefaultPaginator.page')
def test_annotate_after_page_no_removable_annotations(mock_super_page):
    """Verify that a queryset without removable annotations falls back to the default page."""
    paginator = AnnotateAfterPaginationPaginator(get_user_model().objects.order_by('id'), per_page=2)

    assert paginator.page(1) == mock_super_page.return_value
    mock_super_page.assert_called_once_with(1)


@pytest.mark.django_db
@pytest.mark.parametrize('ordering', ['course_score', '-course_score'])
@patch('futurex_openedx_extensions.helpers.pagination.DefaultPaginator.page')
def test_annotate_after_page_ordered_by_removable_annotation(mock_super_page, ordering):
    """Verify that ordering on a removable annotation falls back to the default page, which keeps that order."""
    queryset = get_learners_by_course_queryset(course_id='course-v1:ORG1+5+5').order_by(ordering)
    paginator = AnnotateAfterPaginationPaginator(queryset, per_page=2)

    assert paginator.page(1) == mock_super_page.return_value
    mock_super_page.assert_called_once_with(1)
