"""Tests for the per-tenant cache of the learner theme catalogue and its per-user `enrolled` overlay"""
from unittest.mock import Mock, patch

import pytest
from common.djangoapps.student.models import CourseEnrollment
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from opaque_keys.edx.keys import CourseKey
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers import learner_theme as lt
from futurex_openedx_extensions.helpers.tenants import publish_tenant_config, set_tenant_config_value
from tests.test_helpers.test_learner_theme import PROGRAM_KEYS, TENANT1_COURSES


def _request(domain='s1.sample.com', user=None):
    """Return a request-like object for the helpers"""
    return Mock(site=Mock(domain=domain), user=user or AnonymousUser(), scheme='https')


def test_add_enrolled_keeps_given_programs_and_key_order():
    """Verify the overlay returns new dicts (a cached list is never changed) with `enrolled` right before `price`"""
    programs = [{'id': 'course-v1:ORG1+5+5', 'start_date': None, 'price': None, 'currency': None}]

    result = lt.add_enrolled(programs, None)

    assert result == [
        {'id': 'course-v1:ORG1+5+5', 'start_date': None, 'enrolled': False, 'price': None, 'currency': None},
    ]
    assert list(result[0]) == ['id', 'start_date', 'enrolled', 'price', 'currency']
    assert programs == [{'id': 'course-v1:ORG1+5+5', 'start_date': None, 'price': None, 'currency': None}]
    assert not lt.add_enrolled([], Mock(id=3))


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.learner_theme.get_course_units_count', return_value=0)
def test_get_tenant_catalog_has_no_user_data(_, base_data):  # pylint: disable=unused-argument
    """Verify the cacheable catalogue carries nothing about a user, and get_catalog adds `enrolled` to it"""
    catalog = lt.get_tenant_catalog(1)

    assert {program['id'] for program in catalog['results']} == TENANT1_COURSES
    assert all(set(program) == PROGRAM_KEYS - {'enrolled'} for program in catalog['results'])
    assert all(set(program) == PROGRAM_KEYS for program in lt.get_catalog(_request())['results'])
    assert [key for key in lt.get_catalog(_request())['results'][0] if key != 'enrolled'] == list(
        catalog['results'][0]
    )


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.learner_theme.get_course_units_count', return_value=0)
def test_get_catalog_cache_hit_runs_no_catalog_queries(
    _, base_data, cache_testing, django_assert_num_queries,
):  # pylint: disable=unused-argument
    """Verify a warm cache serves the catalogue and the categories with no query at all for an anonymous visitor"""
    with CaptureQueriesContext(connection) as cold:
        first = lt.get_catalog(_request())
    assert len(cold) > 3
    assert len(first['results']) == len(TENANT1_COURSES)

    with django_assert_num_queries(0):
        assert lt.get_catalog(_request()) == first
        assert lt.get_learner_theme_catalog(_request()) == first['results']
        assert lt.get_learner_theme_categories(_request()) == first['categories']


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.learner_theme.get_course_units_count', return_value=0)
def test_get_catalog_enrolled_overlay(
    _, base_data, cache_testing, django_assert_num_queries,
):  # pylint: disable=unused-argument
    """
    Verify `enrolled` is the requesting user's own active enrollments, read with ONE query on a warm cache
    whatever the number of courses, and with none for an anonymous visitor
    """
    course5 = CourseKey.from_string('course-v1:ORG1+5+5')
    course2 = CourseKey.from_string('course-v1:ORG1+2+2')
    user_model = get_user_model()
    enrolled_user = user_model.objects.get(id=60)
    inactive_user = user_model.objects.get(id=61)
    other_user = user_model.objects.get(id=62)
    CourseEnrollment.objects.filter(user_id__in=[60, 61, 62]).delete()
    CourseEnrollment.objects.create(user=enrolled_user, course_id=course5, is_active=True)
    CourseEnrollment.objects.create(user=enrolled_user, course_id=course2, is_active=True)
    CourseEnrollment.objects.create(user=inactive_user, course_id=course5, is_active=False)

    def _enrolled_ids(user, expected_queries):
        with django_assert_num_queries(expected_queries):
            results = lt.get_catalog(_request(user=user))['results']
        assert len(results) == len(TENANT1_COURSES)
        return {program['id'] for program in results if program['enrolled']}

    lt.get_catalog(_request())  # warm the cache as an anonymous visitor

    assert _enrolled_ids(None, 0) == set()
    assert _enrolled_ids(enrolled_user, 1) == {'course-v1:ORG1+5+5', 'course-v1:ORG1+2+2'}
    assert _enrolled_ids(inactive_user, 1) == set()
    assert _enrolled_ids(other_user, 1) == set()
    assert _enrolled_ids(None, 0) == set()
    assert all('enrolled' not in program for program in lt.get_tenant_catalog(1)['results'])


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.learner_theme.get_course_units_count', return_value=0)
def test_get_catalog_cache_is_per_tenant(_, base_data, cache_testing):  # pylint: disable=unused-argument
    """Verify a tenant's cached catalogue is never served on another tenant's site"""
    tenant1 = lt.get_catalog(_request(domain='s1.sample.com'))
    tenant3 = lt.get_catalog(_request(domain='s3.sample.com'))
    tenant1_again = lt.get_catalog(_request(domain='s1.sample.com'))

    assert {program['id'] for program in tenant1['results']} == TENANT1_COURSES
    assert {program['id'] for program in tenant3['results']} == {'course-v1:ORG4+1+1'}
    assert tenant1_again == tenant1
    assert lt.get_catalog(_request(domain='s3.sample.com')) == tenant3
    assert {program['id'] for program in cache.get('fx_learner_theme_catalog_1')['data']['results']} == TENANT1_COURSES
    assert [program['id'] for program in cache.get('fx_learner_theme_catalog_3')['data']['results']] == [
        'course-v1:ORG4+1+1',
    ]
    assert lt.get_catalog(_request(domain='unknown.sample.com')) == {'results': [], 'categories': []}


def _catalog_title(course_id='course-v1:ORG1+5+5', domain='s1.sample.com'):
    """Return the title of the course in the catalogue of the tenant on the given site"""
    results = lt.get_catalog(_request(domain=domain))['results']
    return {program['id']: program['title'] for program in results}[course_id]


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.learner_theme.get_course_units_count', return_value=0)
def test_get_catalog_cache_invalidated_on_publish(_, base_data, cache_testing):  # pylint: disable=unused-argument
    """Verify publishing the tenant's config clears its catalogue, and only its own"""
    assert _catalog_title() == 'Course 5 of ORG1'
    assert _catalog_title('course-v1:ORG4+1+1', 's3.sample.com') == 'Course 1 of ORG4'
    CourseOverview.objects.filter(id='course-v1:ORG1+5+5').update(display_name='Edited in Studio')
    CourseOverview.objects.filter(id='course-v1:ORG4+1+1').update(display_name='Edited too')
    assert _catalog_title() == 'Course 5 of ORG1'

    publish_tenant_config(1)

    assert _catalog_title() == 'Edited in Studio'
    assert _catalog_title('course-v1:ORG4+1+1', 's3.sample.com') == 'Course 1 of ORG4'


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.learner_theme.get_course_units_count', return_value=0)
def test_get_catalog_cache_invalidated_on_config_value_write(
    _, base_data, cache_testing,
):  # pylint: disable=unused-argument
    """Verify a direct config value write (the course categories are saved this way) clears the catalogue"""
    assert _catalog_title() == 'Course 5 of ORG1'
    CourseOverview.objects.filter(id='course-v1:ORG1+5+5').update(display_name='Edited in Studio')
    assert _catalog_title() == 'Course 5 of ORG1'

    with patch(
        'futurex_openedx_extensions.helpers.tenants.get_config_access_control',
        return_value={'some_key': {'path': 'some_path'}},
    ):
        set_tenant_config_value(tenant_id=1, config_key='some_key', value='x')

    assert _catalog_title() == 'Edited in Studio'


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.learner_theme.get_course_units_count', return_value=0)
def test_invalidate_course_catalog(_, base_data, cache_testing):  # pylint: disable=unused-argument
    """Verify the catalogue of the course's tenants is cleared, and no other tenant's"""
    lt.get_catalog(_request(domain='s1.sample.com'))
    lt.get_catalog(_request(domain='s3.sample.com'))
    assert cache.get('fx_learner_theme_catalog_1') and cache.get('fx_learner_theme_catalog_3')

    lt.invalidate_course_catalog(CourseKey.from_string('course-v1:ORG1+5+5'))

    assert cache.get('fx_learner_theme_catalog_1') is None
    assert cache.get('fx_learner_theme_catalog_3')


@pytest.mark.django_db
@pytest.mark.parametrize('settings_override, expected_timeout', [
    ({}, 360),
    ({'FX_CACHE_TIMEOUT_LEARNER_THEME_CATALOG': 17}, 17),
])
@patch('futurex_openedx_extensions.helpers.learner_theme.get_course_units_count', return_value=0)
def test_get_tenant_catalog_timeout_setting(
    _, settings_override, expected_timeout, base_data, cache_testing,
):  # pylint: disable=unused-argument
    """Verify the catalogue is cached for FX_CACHE_TIMEOUT_LEARNER_THEME_CATALOG seconds"""
    with override_settings(**settings_override), patch(
        'futurex_openedx_extensions.helpers.caching.cache.set', wraps=cache.set,
    ) as mock_set:
        lt.get_tenant_catalog(1)

    timeouts = [call.args[2] for call in mock_set.call_args_list if call.args[0] == 'fx_learner_theme_catalog_1']
    assert timeouts == [expected_timeout]
