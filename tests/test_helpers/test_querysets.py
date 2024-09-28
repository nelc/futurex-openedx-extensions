"""Tests for querysets helpers"""
import pytest
from common.djangoapps.student.models import CourseAccessRole, UserProfile
from django.contrib.auth import get_user_model
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers import querysets
from tests.fixture_helpers import get_tenants_orgs


@pytest.mark.django_db
def test_get_base_queryset_courses(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify get_base_queryset_courses function."""
    result = querysets.get_base_queryset_courses(fx_permission_info)
    assert result.count() == 12
    for course in result:
        assert course.catalog_visibility == 'both'


@pytest.mark.django_db
def test_get_base_queryset_courses_non_staff(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify get_base_queryset_courses function for non-staff user."""
    fx_permission_info.update({
        'user': get_user_model().objects.get(username='user4'),
        'is_system_staff_user': False,
        'view_allowed_roles': ['instructor'],
    })

    result = querysets.get_base_queryset_courses(fx_permission_info)
    assert result.count() == 12
    for course in result:
        assert course.catalog_visibility == 'both'


@pytest.mark.django_db
def test_get_base_queryset_courses_visible_filter(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify get_base_queryset_courses function with visible_filter."""
    course = CourseOverview.objects.filter(org='org1').first()
    assert course.catalog_visibility == 'both', 'Catalog visibility should be initialized as (both) for test courses'
    course.catalog_visibility = 'none'
    course.save()

    result = querysets.get_base_queryset_courses(fx_permission_info)
    assert result.count() == 11
    result = querysets.get_base_queryset_courses(fx_permission_info, visible_filter=False)
    assert result.count() == 1
    result = querysets.get_base_queryset_courses(fx_permission_info, visible_filter=None)
    assert result.count() == 12


@pytest.mark.django_db
def test_get_base_queryset_courses_active_filter(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify get_base_queryset_courses function with active_filter."""
    result = querysets.get_base_queryset_courses(fx_permission_info)
    assert result.count() == 12
    result = querysets.get_base_queryset_courses(fx_permission_info, active_filter=True)
    assert result.count() == 7
    result = querysets.get_base_queryset_courses(fx_permission_info, active_filter=False)
    assert result.count() == 5


@pytest.mark.django_db
def test_get_base_queryset_courses_limited_course_roles(
    base_data, fx_permission_info
):  # pylint: disable=unused-argument
    """Verify get_base_queryset_courses function with limited course roles."""
    fx_permission_info.update({
        'user': get_user_model().objects.get(username='user4'),
        'is_system_staff_user': False,
        'view_allowed_full_access_orgs': ['org2'],
        'view_allowed_course_access_orgs': [],
        'view_allowed_any_access_orgs': ['org2'],
        'view_allowed_roles': ['staff'],
    })
    course_id = 'course-v1:ORG2+2+2'
    assert CourseAccessRole.objects.filter(user_id=4, org='org2', role='staff').count() == 0
    assert CourseAccessRole.objects.filter(user_id=4, org='org2', course_id=course_id).count() == 0
    assert querysets.get_base_queryset_courses(fx_permission_info).count() == 0

    CourseAccessRole.objects.create(
        user_id=4, org='org2', role='instructor', course_id=course_id,
    )
    assert querysets.get_base_queryset_courses(fx_permission_info).count() == 0

    course_role = CourseAccessRole.objects.create(
        user_id=4, org='org2', role='staff', course_id=course_id,
    )
    result = querysets.get_base_queryset_courses(fx_permission_info)
    assert result.count() == 1
    assert result.first().org.lower() == course_role.org.lower()
    assert result.first().id == course_role.course_id


@pytest.mark.django_db
def test_get_base_queryset_courses_global_roles(base_data, fx_permission_info):  # pylint: disable=unused-argument
    """Verify get_base_queryset_courses function with global roles."""
    fx_permission_info.update({
        'user': get_user_model().objects.get(username='user4'),
        'is_system_staff_user': False,
        'view_allowed_full_access_orgs': ['org2'],
        'view_allowed_course_access_orgs': [],
        'view_allowed_any_access_orgs': ['org2'],
        'view_allowed_roles': ['staff', 'support'],
    })
    assert CourseAccessRole.objects.filter(user_id=4, org='org2', role__in=['staff', 'support']).count() == 0
    assert querysets.get_base_queryset_courses(fx_permission_info).count() == 0

    CourseAccessRole.objects.create(user_id=4, role='support')
    result = querysets.get_base_queryset_courses(fx_permission_info)
    org2_courses = [course.id for course in CourseOverview.objects.filter(org='org2')]
    assert result.count() == len(org2_courses)
    for course in result:
        assert course.id in org2_courses


@pytest.mark.django_db
@pytest.mark.parametrize('argument_name, bad_value, expected_error_msg', [
    ('ref_user_id', None, 'Invalid ref_user_id type (NoneType)'),
    ('ref_org', 0, 'Invalid ref_org type (int)'),
    ('ref_course_id', 0, 'Invalid ref_course_id type (int)'),
])
def test_check_staff_exist_queryset_invalid(argument_name, bad_value, expected_error_msg):
    """Verify check_staff_exist_queryset function with invalid input."""
    arguments = {
        'ref_user_id': 'user_id',
        'ref_org': 'org',
        'ref_course_id': 'course_id',
    }
    arguments.update({argument_name: bad_value})

    with pytest.raises(ValueError) as exc_info:
        querysets.check_staff_exist_queryset(**arguments)
    assert str(exc_info.value) == expected_error_msg


@pytest.mark.django_db
@pytest.mark.parametrize('search_text, expected_count', [
    (None, 64),
    ('user', 64),
    ('user4', 11),
    ('example', 64),
])
def test_get_learners_search_queryset(base_data, search_text, expected_count):  # pylint: disable=unused-argument
    """Verify that get_learners_search_queryset returns the correct QuerySet."""
    assert querysets.get_learners_search_queryset(search_text=search_text).count() == expected_count


@pytest.mark.django_db
def test_get_learners_search_queryset_name(base_data):  # pylint: disable=unused-argument
    """Verify that get_learners_search_queryset returns the correct QuerySet when searching in profile name."""
    assert querysets.get_learners_search_queryset(search_text='hn D').count() == 0
    UserProfile.objects.create(user_id=10, name='John Doe')
    assert querysets.get_learners_search_queryset(search_text='hn D').count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize('filter_name, true_count', [
    ('superuser_filter', 2),
    ('staff_filter', 2),
    ('active_filter', 67),
])
def test_get_learners_search_queryset_active_filter(
    base_data, filter_name, true_count
):  # pylint: disable=unused-argument
    """Verify that get_learners_search_queryset returns the correct QuerySet when active_filters is used"""
    kwargs = {
        'superuser_filter': None,
        'staff_filter': None,
        'active_filter': None,
    }
    assert querysets.get_learners_search_queryset(**kwargs).count() == 70, 'unexpected test data'
    kwargs[filter_name] = True
    assert querysets.get_learners_search_queryset(**kwargs).count() == true_count
    kwargs[filter_name] = False
    assert querysets.get_learners_search_queryset(**kwargs).count() == 70 - true_count


@pytest.mark.django_db
@pytest.mark.parametrize('full_access, partial_access, expected_with_staff, expected_without_staff', [
    ([7, 8], [], 26, 22),
    ([7], [8], 21, 18),
    ([8], [7], 16, 14),
    ([], [7, 8], 10, 9),
])
def test_get_permitted_learners_queryset(
    base_data, full_access, partial_access, expected_with_staff, expected_without_staff,
):  # pylint: disable=unused-argument
    """Verify get_permitted_learners_queryset function."""
    course_ids = {
        'org3': 'course-v1:ORG3+1+1',
        'org8': 'course-v1:ORG8+1+1',
    }
    assert CourseOverview.objects.filter(id__in=course_ids.values()).count() == len(course_ids), 'bad test data'

    queryset = get_user_model().objects.all()
    whatever_role_for_testing = 'instructor'
    role_to_ignore = 'staff'

    fx_permission_info = {
        'is_system_staff_user': False,
        'user_roles': {
            whatever_role_for_testing: {
                'course_limited_access': [course_ids[org] for org in get_tenants_orgs(partial_access)],
            },
            role_to_ignore: {'course_limited_access': ['course-v1:should_not_be_reached']},
        },
        'view_allowed_roles': [whatever_role_for_testing],
        'view_allowed_full_access_orgs': get_tenants_orgs(full_access),
        'view_allowed_course_access_orgs': get_tenants_orgs(partial_access),
        'view_allowed_any_access_orgs': get_tenants_orgs(full_access + partial_access),
        'view_allowed_tenant_ids_full_access': full_access,
        'view_allowed_tenant_ids_partial_access': partial_access,
    }

    result = querysets.get_permitted_learners_queryset(queryset, fx_permission_info)
    assert result.count() == expected_without_staff

    result = querysets.get_permitted_learners_queryset(queryset, fx_permission_info, include_staff=True)
    assert result.count() == expected_with_staff
