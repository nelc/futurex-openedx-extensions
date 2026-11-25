"""Tests for the learner theme helpers"""
import copy
import datetime
import re
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from common.djangoapps.course_modes.models import CourseMode
from common.djangoapps.student.models import CourseEnrollment
from completion_aggregator.models import Aggregator
from custom_reg_form.models import ExtraInfo
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from eox_tenant.models import TenantConfig
from opaque_keys.edx.keys import CourseKey
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers import learner_theme as lt
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.models import CourseCertificateIssuance, CourseLearnerMeta

TENANT1_COURSES = {
    'course-v1:Org1+1+1',
    'course-v1:ORG1+2+2', 'course-v1:ORG1+3+3', 'course-v1:ORG1+4+4', 'course-v1:ORG1+5+5',
    'course-v1:ORG2+1+1', 'course-v1:ORG2+2+2', 'course-v1:ORG2+3+3', 'course-v1:ORG2+4+4',
    'course-v1:ORG2+5+5', 'course-v1:ORG2+6+6', 'course-v1:ORG2+7+7',
}

PROGRAM_KEYS = {
    'id', 'title', 'image_url', 'about_url', 'effort_hours', 'units', 'level', 'learning_mode', 'has_certificate',
    'category_ids', 'status', 'start_date', 'enrolled', 'price',
}


def _request(domain='s1.sample.com', user=None):
    """Return a request-like object for the helpers"""
    return Mock(site=Mock(domain=domain), user=user or AnonymousUser(), scheme='https')


def _set_lms_configs(tenant_id, **values):
    """Merge values into the tenant's lms_configs"""
    tenant = TenantConfig.objects.get(id=tenant_id)
    tenant.lms_configs.update(values)
    tenant.save()


@pytest.mark.django_db
@pytest.mark.parametrize('request_obj, expected', [
    (Mock(site=Mock(domain='s1.sample.com')), 1),
    (Mock(site=Mock(domain='s3.sample.com')), 3),
    (Mock(site=Mock(domain='unknown.sample.com')), None),
    (Mock(site=None), None),
    (Mock(spec=[]), None),
])
def test_get_request_tenant_id(request_obj, expected, base_data):  # pylint: disable=unused-argument
    """Verify the tenant is taken from the request's site"""
    assert lt.get_request_tenant_id(request_obj) == expected


@pytest.mark.parametrize('link, expected', [
    ({'page': 'home'}, '/'),
    ({'page': 'about-us'}, '/about'),
    ({'page': 'external_link', 'custom_url': 'https://x.sa'}, 'https://x.sa'),
    ({'page': 'external_link'}, None),
    ({'page': 'custom-page-1'}, '/p/my-page'),
    ({'page': 'custom_page_1'}, '/p/my-page'),
    ({'page': 'nothing'}, None),
    ({}, None),
    ('not a dict', None),
    (None, None),
])
def test_resolve_link(link, expected):
    """Verify links resolve like the theme's get_fx_link_sections"""
    assert lt.resolve_link(link, {'custom_page_1': 'my-page'}) == expected


FULL_THEME_CONFIG = {
    'PLATFORM_NAME': 'Platform',
    'logo_image_url': 'https://cdn.sample.com/logo.png',
    'THEME_OPTIONS': {'theme': {'name': 'fx-learner', 'parent': 'indigo'}},
    'theme_v2': {
        'learner_theme': {'allowed': True, 'enabled': True},
        'custom_pages': [{'key': 'custom_page_1', 'url_slug': 'guide'}, {'key': 'broken'}, 'bad'],
        'platform_settings': {
            'site_name': {'ar': 'منصة', 'en': ''},
            'language': {'languages': ['ar', 'en'], 'default_language': 'ar'},
        },
        'entity_identity': {
            'short_name': {'ar': 'هيئة', 'en': 'Authority'},
            'parent_org': {'ar': 'وزارة'},
            'site_label': {'ar': 'الموقع', 'en': 'Website'},
            'site_url': 'https://entity.sa',
            'help_link': {'page': 'custom-page-1'},
        },
        'header': {'sections': [
            {'page': 'courses', 'link_title': {'ar': 'البرامج', 'en': 'Programs'}, 'new_tab': False},
            {'page': 'invalid', 'link_title': {'en': 'Gone'}},
            {'page': 'external_link', 'custom_url': 'https://x.sa', 'link_title': {'en': 'X'}, 'new_tab': True},
        ]},
        'footer': {
            'sections': [{'page': 'terms', 'link_title': {'en': 'Terms'}}],
            'social_media_links': [{'provider': 'x', 'value': 'https://x.com/a'}, {'provider': 'facebook'}, 'bad'],
            'copyrights_text': {'ar': 'حقوق', 'en': 'Rights'},
        },
    },
}


@pytest.mark.django_db
def test_get_learner_theme_shell_full(base_data):  # pylint: disable=unused-argument
    """Verify the shell shape built from published values"""
    _set_lms_configs(1, **FULL_THEME_CONFIG)

    assert lt.get_learner_theme_shell(1) == {
        'active': True,
        'logo_url': 'https://cdn.sample.com/logo.png',
        'site_name': {'ar': 'منصة', 'en': 'Platform'},
        'short_name': {'ar': 'هيئة', 'en': 'Authority'},
        'parent_org': {'ar': 'وزارة', 'en': ''},
        'nav': [
            {'title': {'ar': 'البرامج', 'en': 'Programs'}, 'url': '/courses', 'new_tab': False},
            {'title': {'ar': '', 'en': 'X'}, 'url': 'https://x.sa', 'new_tab': True},
        ],
        'footer': {
            'links': [{'title': {'ar': '', 'en': 'Terms'}, 'url': '/tos', 'new_tab': False}],
            'social': [{'provider': 'x', 'value': 'https://x.com/a'}],
            'copyright': {'ar': 'حقوق', 'en': 'Rights'},
            'site_label': {'ar': 'الموقع', 'en': 'Website'},
            'site_url': 'https://entity.sa',
        },
        'help_url': '/p/guide',
        'languages': ['ar', 'en'],
        'default_language': 'ar',
        'urls': {
            'home': '/', 'catalog': '/courses', 'about': '/about', 'my': '/learner/my',
            'certificates': '/learner/certificates', 'profile': '/learner/profile', 'login': '/login',
            'logout': '/logout',
        },
    }
    assert lt.is_learner_theme_active(1) is True


@pytest.mark.django_db
@pytest.mark.parametrize('short_name, expected', [
    (None, {'ar': 'منصة', 'en': 'Platform'}),
    ({'ar': '', 'en': ''}, {'ar': 'منصة', 'en': 'Platform'}),
    ({'ar': 'هيئة'}, {'ar': 'هيئة', 'en': 'Platform'}),
    ({'en': 'Authority'}, {'ar': 'منصة', 'en': 'Authority'}),
])
def test_get_learner_theme_shell_short_name_fallback(
    short_name, expected, base_data,
):  # pylint: disable=unused-argument
    """Verify an empty short name falls back to the site name per language, so the brand is never empty"""
    config = copy.deepcopy(FULL_THEME_CONFIG)
    config['theme_v2']['entity_identity'] = {'short_name': short_name} if short_name is not None else {}
    _set_lms_configs(1, **config)

    shell = lt.get_learner_theme_shell(1)

    assert shell['short_name'] == expected
    assert shell['help_url'] == '/faq'


@pytest.mark.django_db
def test_get_learner_theme_shell_defaults(base_data):  # pylint: disable=unused-argument
    """Verify the shell of a tenant with none of the theme keys"""
    shell = lt.get_learner_theme_shell(2)

    assert shell['active'] is False
    assert shell['logo_url'] is None
    assert shell['site_name'] == {'ar': '', 'en': ''}
    assert shell['nav'] == []
    assert shell['footer'] == {
        'links': [], 'social': [], 'copyright': {'ar': '', 'en': ''}, 'site_label': {'ar': '', 'en': ''},
        'site_url': None,
    }
    assert shell['short_name'] == {'ar': '', 'en': ''}
    assert shell['help_url'] == '/faq'
    assert (shell['languages'], shell['default_language']) == (['en'], 'en')
    assert lt.is_learner_theme_active(2) is False


@pytest.mark.django_db
@pytest.mark.parametrize('theme_name, switch', [
    ('indigo', {'allowed': True, 'enabled': True}),
    ('fx-learner', {'allowed': True, 'enabled': False}),
    ('fx-learner', {'allowed': False, 'enabled': True}),
])
def test_get_learner_theme_shell_not_active(theme_name, switch, base_data):  # pylint: disable=unused-argument
    """Verify `active` needs allowed AND enabled AND the fx-learner theme"""
    _set_lms_configs(1, THEME_OPTIONS={'theme': {'name': theme_name}}, theme_v2={'learner_theme': switch})
    assert lt.get_learner_theme_shell(1)['active'] is False


@pytest.mark.django_db
def test_get_learner_theme_shell_unknown_tenant(base_data):  # pylint: disable=unused-argument
    """Verify an unknown tenant gives an empty shell"""
    assert not lt.get_learner_theme_shell(9999)
    assert lt.is_learner_theme_active(9999) is False


@pytest.mark.django_db
def test_get_learner_theme_shell_bad_default_language(base_data):  # pylint: disable=unused-argument
    """Verify a default language outside the languages list falls back to the first language"""
    _set_lms_configs(1, theme_v2={'platform_settings': {'language': {'languages': ['ar'], 'default_language': 'fr'}}})
    assert lt.get_learner_theme_shell(1)['default_language'] == 'ar'


@pytest.mark.django_db
def test_get_tenant_catalog_queryset(base_data):  # pylint: disable=unused-argument
    """Verify the catalogue rule: visible, and enrollment open OR not ended; other tenants' courses never show"""
    past = timezone.now() - datetime.timedelta(days=2)
    future = timezone.now() + datetime.timedelta(days=2)
    CourseOverview.objects.filter(id='course-v1:ORG1+2+2').update(enrollment_end=past, end=past)
    CourseOverview.objects.filter(id='course-v1:ORG1+3+3').update(enrollment_end=past, end=future)
    CourseOverview.objects.filter(id='course-v1:ORG1+4+4').update(catalog_visibility='none')
    CourseOverview.objects.filter(id='course-v1:ORG1+5+5').update(visible_to_staff_only=True)
    CourseOverview.objects.filter(id='course-v1:ORG2+1+1').update(enrollment_start=future)

    result = {str(course.id) for course in lt.get_tenant_catalog_queryset(1)}

    assert result == TENANT1_COURSES - {'course-v1:ORG1+2+2', 'course-v1:ORG1+4+4', 'course-v1:ORG1+5+5'}
    assert {str(course.id) for course in lt.get_tenant_courses_queryset(1)} == TENANT1_COURSES


@pytest.mark.parametrize('effort, expected', [
    ('40', 40), (' 4 ', 4), ('1.5', 1.5), ('02:30', 2.5), ('3:00', 3), ('0:20', 0.33),
    ('about a week', None), ('', None), (None, None), ('1:75', None),
])
def test_parse_effort_hours(effort, expected):
    """Verify the course effort is parsed to hours"""
    assert lt.parse_effort_hours(effort) == expected


def test_parse_effort_hours_uses_eox_nelp_patterns():
    """Verify eox-nelp's patterns are used when eox-nelp is installed"""
    fake_effort = SimpleNamespace(
        HH_MM=re.compile(r'^(\d+)h(\d\d)$'), INTEGER=re.compile(r'^\d+$'), DECIMAL=re.compile(r'^\d+\.\d+$'),
    )
    with patch.dict(sys.modules, {'eox_nelp.effort': fake_effort}):
        assert lt.parse_effort_hours('2h30') == 2.5
        assert lt.parse_effort_hours('02:30') is None


@pytest.mark.parametrize('sections, expected', [
    ([], 0),
    ([SimpleNamespace(visibility=SimpleNamespace(visible_to_staff_only=False))] * 3, 3),
    ([
        SimpleNamespace(visibility=SimpleNamespace(visible_to_staff_only=False)),
        SimpleNamespace(visibility=SimpleNamespace(visible_to_staff_only=True)),
        SimpleNamespace(),
    ], 2),
])
def test_get_course_units_count(sections, expected):
    """Verify units = chapters that are not staff-only"""
    with patch(
        'futurex_openedx_extensions.helpers.learner_theme.get_course_outline',
        return_value=SimpleNamespace(sections=sections),
    ):
        assert lt.get_course_units_count(CourseKey.from_string('course-v1:ORG1+1+1')) == expected


def test_get_course_units_count_no_outline():
    """Verify a course without an outline has 0 units"""
    with patch(
        'futurex_openedx_extensions.helpers.learner_theme.get_course_outline', side_effect=ValueError('no outline'),
    ):
        assert lt.get_course_units_count(CourseKey.from_string('course-v1:ORG1+1+1')) == 0


def test_get_course_units_count_cached():
    """Verify the cached value is used"""
    with patch('futurex_openedx_extensions.helpers.learner_theme.cache') as mock_cache, patch(
        'futurex_openedx_extensions.helpers.learner_theme.get_course_outline',
    ) as mock_outline:
        mock_cache.get.return_value = 7
        assert lt.get_course_units_count(CourseKey.from_string('course-v1:ORG1+1+1')) == 7
    mock_outline.assert_not_called()


NOW = timezone.now()
DAY = datetime.timedelta(days=1)


@pytest.mark.parametrize('fields, active_enrollments, expected', [
    ({}, 0, 'open'),
    ({'enrollment_end': NOW - DAY}, 0, 'closed'),
    ({'end': NOW - DAY}, 0, 'closed'),
    ({'enrollment_start': NOW + DAY}, 0, 'upcoming'),
    ({'enrollment_start': NOW - DAY, 'enrollment_end': NOW + DAY, 'end': NOW + DAY}, 0, 'open'),
    ({'max_student_enrollments_allowed': 5}, 5, 'full'),
    ({'max_student_enrollments_allowed': 5}, 4, 'open'),
    ({'max_student_enrollments_allowed': 0}, 9, 'open'),
])
def test_get_program_status(fields, active_enrollments, expected):
    """Verify the enrollment status of a course"""
    course = SimpleNamespace(**{
        'enrollment_start': None, 'enrollment_end': None, 'end': None, 'max_student_enrollments_allowed': None,
        **fields,
    })
    assert lt.get_program_status(course, active_enrollments, NOW) == expected


@pytest.mark.django_db
def test_get_course_category_ids(base_data):  # pylint: disable=unused-argument
    """Verify course categories come from the existing course categories feature, in its order"""
    _set_lms_configs(1, theme_v2={'course_categories': {
        'categories': {
            'category_1': {'label': {'ar': 'أ', 'en': 'A'}, 'courses': ['course-v1:ORG1+2+2']},
            'category_2': {'label': {'en': 'B'}, 'courses': ['course-v1:ORG1+2+2', 'course-v1:ORG2+3+3']},
        },
        'sorting': ['category_2', 'category_1'],
    }})
    with patch(
        'futurex_openedx_extensions.helpers.course_categories.get_tenant_config_value',
        return_value=TenantConfig.objects.get(id=1).lms_configs['theme_v2']['course_categories'],
    ):
        course_categories, categories = lt.get_course_category_ids(1)

    assert categories == [
        {'id': 'category_2', 'name': {'ar': '', 'en': 'B'}},
        {'id': 'category_1', 'name': {'ar': 'أ', 'en': 'A'}},
    ]
    assert course_categories == {
        'course-v1:ORG1+2+2': ['category_2', 'category_1'],
        'course-v1:ORG2+3+3': ['category_2'],
    }


def test_get_course_category_ids_invalid_settings():
    """Verify broken category settings give no categories instead of failing the page"""
    with patch(
        'futurex_openedx_extensions.helpers.learner_theme.CourseCategories',
        side_effect=FXCodedException(code=FXExceptionCodes.COURSE_CATEGORY_INVALID_SETTINGS, message='bad'),
    ):
        assert lt.get_course_category_ids(1) == ({}, [])


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.learner_theme.get_course_units_count', return_value=4)
def test_build_programs(_, base_data):  # pylint: disable=unused-argument
    """Verify the program dict of each course"""
    user = get_user_model().objects.get(id=3)
    start = timezone.now() - DAY
    CourseOverview.objects.filter(id='course-v1:ORG1+5+5').update(
        effort='10:30', course_image_url='/asset/img.png', start=start, has_any_active_web_certificate=True,
        max_student_enrollments_allowed=7,
    )
    CourseOverview.objects.filter(id='course-v1:ORG1+2+2').update(
        has_any_active_web_certificate=True, max_student_enrollments_allowed=50,
    )
    course5 = CourseKey.from_string('course-v1:ORG1+5+5')
    course2 = CourseKey.from_string('course-v1:ORG1+2+2')
    CourseLearnerMeta.set_meta(course5, level='basic', learning_mode='blended', user=user)
    CourseCertificateIssuance.set_issuance_enabled(course2, False, user)
    CourseMode.objects.create(course_id=course5, mode_slug='no-id-professional', mode_display_name='P', min_price=250)
    CourseMode.objects.create(course_id=course2, mode_slug='honor', mode_display_name='H', min_price=100)

    courses = list(CourseOverview.objects.filter(id__in=[course5, course2]).order_by('id'))
    programs = {program['id']: program for program in lt.build_programs(
        1, courses, user, course_categories={'course-v1:ORG1+5+5': ['category_1']},
    )}

    assert programs['course-v1:ORG1+5+5'] == {
        'id': 'course-v1:ORG1+5+5',
        'title': 'Course 5 of ORG1',
        'image_url': '/asset/img.png',
        'about_url': '/courses/course-v1:ORG1+5+5/about',
        'effort_hours': 10.5,
        'units': 4,
        'level': 'basic',
        'learning_mode': 'blended',
        'has_certificate': True,
        'category_ids': ['category_1'],
        'status': 'full',
        'start_date': start.isoformat(),
        'enrolled': True,
        'price': 250,
    }
    assert programs['course-v1:ORG1+2+2'] == {
        'id': 'course-v1:ORG1+2+2',
        'title': 'Course 2 of ORG1',
        'image_url': None,
        'about_url': '/courses/course-v1:ORG1+2+2/about',
        'effort_hours': None,
        'units': 4,
        'level': None,
        'learning_mode': None,
        'has_certificate': False,
        'category_ids': [],
        'status': 'open',
        'start_date': programs['course-v1:ORG1+2+2']['start_date'],
        'enrolled': True,
        'price': None,
    }
    assert set(programs['course-v1:ORG1+2+2']) == PROGRAM_KEYS


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.learner_theme.get_course_units_count', return_value=0)
def test_build_programs_anonymous(_, base_data):  # pylint: disable=unused-argument
    """Verify an anonymous visitor is never `enrolled`, and the categories are loaded when not given"""
    courses = list(CourseOverview.objects.filter(id='course-v1:ORG1+5+5'))
    with patch(
        'futurex_openedx_extensions.helpers.learner_theme.get_course_category_ids', return_value=({}, []),
    ) as mock_categories:
        programs = lt.build_programs(1, courses, None)

    mock_categories.assert_called_once_with(1)
    assert programs[0]['enrolled'] is False
    assert not lt.build_programs(1, [], None)


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.learner_theme.get_course_units_count', return_value=0)
def test_get_catalog(_, base_data):  # pylint: disable=unused-argument
    """Verify the catalogue of the request's tenant only"""
    with patch(
        'futurex_openedx_extensions.helpers.learner_theme.get_course_category_ids',
        return_value=({}, [{'id': 'category_1', 'name': {'ar': '', 'en': 'A'}}]),
    ):
        catalog = lt.get_catalog(_request())
        programs = lt.get_learner_theme_catalog(_request(domain='s3.sample.com'))

    assert {program['id'] for program in catalog['results']} == TENANT1_COURSES
    assert catalog['categories'] == [{'id': 'category_1', 'name': {'ar': '', 'en': 'A'}}]
    assert {program['id'] for program in programs} == {'course-v1:ORG4+1+1'}
    assert lt.get_catalog(_request(domain='unknown.sample.com')) == {'results': [], 'categories': []}


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.learner_theme.get_course_units_count', return_value=0)
def test_get_learner_theme_program(_, base_data):  # pylint: disable=unused-argument
    """Verify one program of the request's tenant; other tenants' and invalid courses give None"""
    CourseOverview.objects.filter(id='course-v1:ORG1+4+4').update(catalog_visibility='none')

    program = lt.get_learner_theme_program(_request(), 'course-v1:ORG1+4+4')
    assert program['id'] == 'course-v1:ORG1+4+4'
    assert lt.get_learner_theme_program(_request(), CourseKey.from_string('course-v1:ORG1+4+4'))['id'] == program['id']
    assert lt.get_learner_theme_program(_request(), 'course-v1:ORG4+1+1') is None
    assert lt.get_learner_theme_program(_request(), 'not-a-key') is None
    assert lt.get_learner_theme_program(_request(domain='unknown.sample.com'), 'course-v1:ORG1+4+4') is None


@pytest.mark.parametrize('email, expected', [
    ('ali@example.com', 'al***@example.com'),
    ('a@example.com', 'a***@example.com'),
    ('', ''),
    (None, ''),
    ('no-at-sign', ''),
])
def test_mask_email(email, expected):
    """Verify the email masking"""
    assert lt.mask_email(email) == expected


@pytest.mark.parametrize('grade, expected', [('0.85', 85), ('1', 100), ('', None), (None, None), ('A', None)])
def test_grade_percent(grade, expected):
    """Verify the certificate grade conversion"""
    assert lt._grade_percent(grade) == expected  # pylint: disable=protected-access


def _cert(  # pylint: disable=too-many-arguments
    course_id, created, download_url='/certificates/abc', status='downloadable', grade='0.9', uuid='abc',
):
    """Return a certificates API record"""
    return {
        'course_key': CourseKey.from_string(course_id), 'status': status, 'grade': grade, 'created': created,
        'download_url': download_url, 'uuid': uuid,
    }


@pytest.mark.django_db
def test_get_learner_certificates_data(base_data):  # pylint: disable=unused-argument
    """Verify only downloadable certificates of the tenant's courses are kept"""
    user = get_user_model().objects.get(id=15)
    created = timezone.now()
    with patch(
        'futurex_openedx_extensions.helpers.learner_theme.get_certificates_for_user_by_course_keys',
        return_value={
            CourseKey.from_string('course-v1:ORG1+5+5'): _cert('course-v1:ORG1+5+5', created),
            CourseKey.from_string('course-v1:ORG2+7+7'): _cert('course-v1:ORG2+7+7', created, status='notpassing'),
            CourseKey.from_string('course-v1:ORG2+3+3'): None,
        },
    ) as mock_api:
        result = lt.get_learner_certificates_data(1, user)

    assert list(result) == ['course-v1:ORG1+5+5']
    assert {str(key) for key in mock_api.call_args.args[1]} == {'course-v1:ORG1+5+5', 'course-v1:ORG2+7+7'}

    with patch(
        'futurex_openedx_extensions.helpers.learner_theme.get_certificates_for_user_by_course_keys',
    ) as mock_api:
        assert lt.get_learner_certificates_data(2, user) == {}
    mock_api.assert_not_called()


@pytest.mark.django_db
def test_get_learner_programs(base_data):  # pylint: disable=unused-argument
    """Verify the learner's own programs in the request's tenant, with stats and the course to resume"""
    user = get_user_model().objects.get(id=15)
    CourseOverview.objects.filter(id='course-v1:ORG2+7+7').update(lowest_passing_grade=0.6)
    old = timezone.now() - datetime.timedelta(days=3)
    Aggregator.objects.create(
        user=user, course_key='course-v1:ORG2+7+7', aggregation_name='course', percent=0.426,
    )
    Aggregator.objects.filter(course_key='course-v1:ORG2+7+7').update(modified=old)
    Aggregator.objects.create(user=user, course_key='course-v1:ORG4+1+1', aggregation_name='course', percent=0.9)
    CourseEnrollment.objects.filter(user=user, course_id='course-v1:ORG1+5+5').update(created=old)
    with patch(
        'futurex_openedx_extensions.helpers.learner_theme.get_learner_certificates_data',
        return_value={'course-v1:ORG1+5+5': _cert('course-v1:ORG1+5+5', old)},
    ):
        result = lt.get_learner_programs(_request(user=user))

    assert result['user'] == {
        'full_name': '', 'first_name': '', 'arabic_name': None, 'masked_email': 'us***@example.com',
    }
    assert result['stats'] == {'in_progress': 1, 'completed': 1, 'certificates': 1}
    assert result['resume'] == {
        'title': 'Course 7 of ORG2',
        'progress_percent': 43,
        'resume_url': '/courses/course-v1:ORG2+7+7/courseware',
    }
    assert sorted(result['results'], key=lambda item: item['course_id']) == [
        {
            'course_id': 'course-v1:ORG1+5+5',
            'title': 'Course 5 of ORG1',
            'image_url': None,
            'progress_percent': 0,
            'next_step': None,
            'pass_grade_percent': None,
            'resume_url': '/courses/course-v1:ORG1+5+5/courseware',
            'completed': True,
            'certificate_url': 'https://s1.sample.com/certificates/abc',
        },
        {
            'course_id': 'course-v1:ORG2+7+7',
            'title': 'Course 7 of ORG2',
            'image_url': None,
            'progress_percent': 43,
            'next_step': None,
            'pass_grade_percent': 60,
            'resume_url': '/courses/course-v1:ORG2+7+7/courseware',
            'completed': False,
            'certificate_url': None,
        },
    ]


@pytest.mark.django_db
def test_get_learner_programs_resume_most_recent(base_data):  # pylint: disable=unused-argument
    """Verify the resume course is the most recently active one, falling back to the enrollment date"""
    user = get_user_model().objects.get(id=4)
    Aggregator.objects.create(user=user, course_key='course-v1:ORG1+4+4', aggregation_name='course', percent=1.0)
    CourseEnrollment.objects.filter(user=user).update(created=timezone.now() - datetime.timedelta(days=5))
    CourseEnrollment.objects.filter(user=user, course_id='course-v1:ORG2+4+4').update(created=timezone.now())
    with patch(
        'futurex_openedx_extensions.helpers.learner_theme.get_learner_certificates_data', return_value={},
    ):
        result = lt.get_learner_programs(_request(user=user))

    assert result['resume']['title'] == 'Course 4 of ORG2'
    assert [item['course_id'] for item in result['results'] if item['completed']] == ['course-v1:ORG1+4+4']


@pytest.mark.django_db
def test_get_learner_programs_all_completed(base_data):  # pylint: disable=unused-argument
    """Verify there is nothing to resume when every program is completed"""
    user = get_user_model().objects.get(id=3)
    for course_id in ('course-v1:ORG1+2+2', 'course-v1:ORG1+5+5', 'course-v1:ORG2+3+3'):
        Aggregator.objects.create(user=user, course_key=course_id, aggregation_name='course', percent=1.0)
    with patch(
        'futurex_openedx_extensions.helpers.learner_theme.get_learner_certificates_data', return_value={},
    ):
        result = lt.get_learner_programs(_request(user=user))

    assert result['resume'] is None
    assert result['stats'] == {'in_progress': 0, 'completed': 3, 'certificates': 0}


@pytest.mark.django_db
@pytest.mark.parametrize('domain, user_id', [
    ('unknown.sample.com', 15),
    ('s1.sample.com', None),
    ('s8.sample.com', 15),
])
def test_get_learner_programs_empty(domain, user_id, base_data):  # pylint: disable=unused-argument
    """Verify no tenant, no user or no enrollment in the tenant gives the empty answer"""
    user = get_user_model().objects.get(id=user_id) if user_id else None
    with patch(
        'futurex_openedx_extensions.helpers.learner_theme.get_learner_certificates_data', return_value={},
    ):
        result = lt.get_learner_programs(_request(domain=domain, user=user))
    assert result == {
        'user': lt.get_learner_user_info(user) if user else None,
        'stats': {'in_progress': 0, 'completed': 0, 'certificates': 0},
        'resume': None,
        'results': [],
    }


@pytest.mark.django_db
def test_get_learner_certificates(base_data):  # pylint: disable=unused-argument
    """Verify the learner's certificates, newest first, with absolute URLs on the request's site"""
    user = get_user_model().objects.get(id=15)
    older = timezone.now() - datetime.timedelta(days=3)
    newer = timezone.now()
    with patch(
        'futurex_openedx_extensions.helpers.learner_theme.get_learner_certificates_data',
        return_value={
            'course-v1:ORG1+5+5': _cert('course-v1:ORG1+5+5', older, grade='0.755', uuid='u1'),
            'course-v1:ORG2+7+7': _cert(
                'course-v1:ORG2+7+7', newer, download_url='https://pdf.sample.com/c.pdf', grade='', uuid='',
            ),
        },
    ):
        result = lt.get_learner_certificates(_request(user=user))

    assert result == [
        {
            'course_id': 'course-v1:ORG2+7+7',
            'title': 'Course 7 of ORG2',
            'issuer': 's1 platform name',
            'issued_at': newer.isoformat(),
            'grade_percent': None,
            'verify_code': None,
            'preview_url': 'https://pdf.sample.com/c.pdf',
            'download_url': 'https://pdf.sample.com/c.pdf',
            'verify_url': 'https://pdf.sample.com/c.pdf',
        },
        {
            'course_id': 'course-v1:ORG1+5+5',
            'title': 'Course 5 of ORG1',
            'issuer': 's1 platform name',
            'issued_at': older.isoformat(),
            'grade_percent': 76,
            'verify_code': 'u1',
            'preview_url': 'https://s1.sample.com/certificates/abc',
            'download_url': 'https://s1.sample.com/certificates/abc',
            'verify_url': 'https://s1.sample.com/certificates/abc',
        },
    ]


@pytest.mark.django_db
def test_get_learner_certificates_empty(base_data):  # pylint: disable=unused-argument
    """Verify no tenant, no user or no certificate gives an empty list"""
    user = get_user_model().objects.get(id=15)
    assert not lt.get_learner_certificates(_request(domain='unknown.sample.com', user=user))
    assert not lt.get_learner_certificates(_request())
    with patch(
        'futurex_openedx_extensions.helpers.learner_theme.get_learner_certificates_data', return_value={},
    ):
        assert not lt.get_learner_certificates(_request(user=user))


@pytest.mark.django_db
def test_get_learner_theme_menu(base_data):  # pylint: disable=unused-argument
    """Verify the learner menu; anonymous users get None"""
    user = get_user_model().objects.get(id=15)
    user.first_name, user.last_name = 'Ali', 'Saleh'
    user.save()
    programs = {
        'stats': {'in_progress': 1, 'completed': 1, 'certificates': 1},
        'resume': {'title': 'T', 'progress_percent': 10, 'resume_url': '/r'},
        'results': [{}, {}],
    }
    with patch('futurex_openedx_extensions.helpers.learner_theme.get_learner_programs', return_value=programs):
        assert lt.get_learner_theme_menu(_request(user=user)) == {
            'full_name': 'Ali Saleh',
            'first_name': 'Ali',
            'arabic_name': None,
            'masked_email': 'us***@example.com',
            'programs_count': 2,
            'certificates_count': 1,
            'resume': {'title': 'T', 'progress_percent': 10, 'resume_url': '/r'},
        }
        user.first_name = user.last_name = ''
        user.save()
        menu = lt.get_learner_theme_menu(_request(user=user))
        assert (menu['full_name'], menu['first_name']) == ('', '')
        assert 'user15' not in str(menu)

    assert lt.get_learner_theme_menu(_request()) is None


def test_get_learner_theme_menu_blank_name():
    """Verify a blank name gives a blank first name"""
    user = Mock(is_authenticated=True, username=' ', email='')
    with patch('futurex_openedx_extensions.helpers.learner_theme.get_learner_programs', return_value={
        'stats': {'certificates': 0}, 'resume': None, 'results': [],
    }), patch('futurex_openedx_extensions.helpers.learner_theme.extract_full_name_from_user', return_value=''):
        assert lt.get_learner_theme_menu(_request(user=user))['first_name'] == ''


@pytest.mark.django_db
def test_get_learner_user_info(base_data):  # pylint: disable=unused-argument
    """Verify the user info carries the Arabic name of the custom registration form, and never the username"""
    user = get_user_model().objects.get(id=15)
    user.first_name, user.last_name = 'Ali', 'Saleh'
    user.save()
    ExtraInfo.objects.create(user=user, arabic_name=' علي صالح ')
    user = get_user_model().objects.get(id=15)

    assert lt.get_learner_user_info(user) == {
        'full_name': 'Ali Saleh',
        'first_name': 'Ali',
        'arabic_name': 'علي صالح',
        'masked_email': 'us***@example.com',
    }


def test_get_learner_user_info_without_custom_reg_form():
    """Verify arabic_name is None when the user has no ExtraInfo (custom_reg_form not installed or no row)"""
    user = Mock(spec=['first_name', 'last_name', 'email'], first_name='Ali', last_name='', email='')
    assert lt.get_learner_user_info(user) == {
        'full_name': 'Ali', 'first_name': 'Ali', 'arabic_name': None, 'masked_email': '',
    }


def test_absolute_url_without_site():
    """Verify a relative URL stays relative when the request has no site"""
    assert lt._absolute('/x', Mock(site=None)) == '/x'  # pylint: disable=protected-access
    assert lt._absolute(None, Mock()) is None  # pylint: disable=protected-access
