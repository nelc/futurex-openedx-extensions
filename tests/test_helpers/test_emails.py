"""Tests for the role-assigned e-mail"""
import logging
import sys
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from edx_ace.signals import ACE_MESSAGE_SENT
from eox_tenant.models import TenantConfig
from fake_models.models import UserProfile
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers import emails

EMAILS = 'futurex_openedx_extensions.helpers.emails'


@pytest.mark.parametrize('user_language, tenant_language, expected', [
    ('ar', 'en', 'ar'),
    ('en-us', 'ar', 'en'),
    ('ar_SA', None, 'ar'),
    ('fr', 'ar', 'ar'),
    (None, 'ar-sa', 'ar'),
    (None, None, 'en'),
    ('ur', 'fr', 'en'),
])
def test_resolve_language(user_language, tenant_language, expected):
    """Verify the language chain: user preference, tenant default, English"""
    assert emails.resolve_language(user_language, tenant_language) == expected


@pytest.mark.parametrize('lms_configs, expected', [
    ({}, True),
    ({'ROLE_ASSIGNED_EMAIL_ENABLED': True}, True),
    ({'ROLE_ASSIGNED_EMAIL_ENABLED': None}, True),
    ({'ROLE_ASSIGNED_EMAIL_ENABLED': 'false'}, True),
    ({'ROLE_ASSIGNED_EMAIL_ENABLED': 0}, True),
    ({'ROLE_ASSIGNED_EMAIL_ENABLED': False}, False),
])
def test_is_role_assigned_email_enabled(lms_configs, expected):
    """Verify that only an explicit false switches the e-mail off"""
    assert emails.is_role_assigned_email_enabled(lms_configs) is expected


@pytest.mark.parametrize('lms_configs, expected', [
    ({}, []),
    ({'course_org_filter': 'ORG1'}, ['org1']),
    ({'course_org_filter': ['ORG1', 'Org2', None]}, ['org1', 'org2']),
])
def test_tenant_orgs(lms_configs, expected):
    """Verify the tenant orgs are read from course_org_filter in both shapes"""
    assert emails._tenant_orgs(lms_configs) == expected  # pylint: disable=protected-access


@pytest.mark.parametrize('lms_configs, expected', [
    ({'LMS_ROOT_URL': ' https://t1.example.com ', 'LMS_BASE': 'ignored.example.com'}, 'https://t1.example.com'),
    ({'LMS_BASE': 't2.example.com'}, 'https://t2.example.com'),
    ({}, ''),
])
def test_tenant_root_url(lms_configs, expected):
    """Verify the tenant root URL is LMS_ROOT_URL, else built from LMS_BASE"""
    assert emails._tenant_root_url(lms_configs) == expected  # pylint: disable=protected-access


@pytest.mark.parametrize('can_keep, bound_domain, expected_update, expected', [
    (True, 't1.example.com', False, True),
    (False, 't1.example.com', True, True),
    (False, 'other.example.com', True, False),
])
def test_bind_tenant(can_keep, bound_domain, expected_update, expected):
    """Verify the tenant settings are bound only when needed, and the binding is checked"""
    with patch(f'{EMAILS}.can_keep_settings', return_value=can_keep), \
            patch(f'{EMAILS}._update_settings') as mock_update, \
            patch.object(settings, 'EDNX_TENANT_DOMAIN', bound_domain, create=True):
        assert emails._bind_tenant('t1.example.com') is expected  # pylint: disable=protected-access
    assert mock_update.called is expected_update
    if expected_update:
        mock_update.assert_called_once_with('t1.example.com', 'lms_configs')


@pytest.mark.parametrize('has_theme', [True, False])
def test_emulate_tenant_request(has_theme):
    """Verify the fake request carries the tenant site config, and fails when no theme was resolved"""
    request = SimpleNamespace(site_theme='indigo') if has_theme else SimpleNamespace()
    site = Site(domain='t1.example.com')
    with patch(f'{EMAILS}.emulate_http_request', return_value=nullcontext()) as mock_emulate, \
            patch(f'{EMAILS}.get_current_request', return_value=request), \
            patch.dict(sys.modules, {  # the real proxy model needs the platform's SiteConfiguration model
                'eox_tenant.tenant_wise': SimpleNamespace(),
                'eox_tenant.tenant_wise.proxies': SimpleNamespace(TenantSiteConfigProxy=lambda: 'proxy'),
            }):
        if has_theme:
            with emails._emulate_tenant_request(site, 'the-user'):  # pylint: disable=protected-access
                pass
        else:
            context = emails._emulate_tenant_request(site, 'the-user')  # pylint: disable=protected-access
            with pytest.raises(RuntimeError, match='tenant theme could not be resolved'):
                context.__enter__()
    assert site.configuration == 'proxy'  # pylint: disable=no-member
    assert mock_emulate.call_args.kwargs['site'] is site
    assert mock_emulate.call_args.kwargs['user'] == 'the-user'
    assert len(mock_emulate.call_args.kwargs['middleware_classes']) == 2


@pytest.mark.parametrize('delivered', [True, False])
def test_send_and_confirm(delivered):
    """Verify the send counts only when ACE reports the delivery of THIS message"""
    message = SimpleNamespace(uuid='uuid-1')

    def _send(msg):
        ACE_MESSAGE_SENT.send(sender=None, message={'uuid': 'uuid-1' if delivered else 'uuid-2'})
        assert msg is message

    with patch(f'{EMAILS}.ace.send', side_effect=_send):
        assert emails._send_and_confirm(message) is delivered  # pylint: disable=protected-access
    assert not ACE_MESSAGE_SENT.receivers


@pytest.mark.django_db
def test_build_assignments(base_data):  # pylint: disable=unused-argument
    """Verify role names, all-courses rows, and that only the tenant's own courses are listed"""
    course = CourseOverview.objects.filter(org__iexact='org1').first()
    course_id = str(course.id)
    rows = emails._build_assignments([  # pylint: disable=protected-access
        {'role': 'staff', 'tenant_wide': True, 'course_ids': []},
        {'role': 'instructor', 'tenant_wide': False, 'course_ids': [course_id, 'course-v1:ORG1+missing+1']},
        {'role': 'beta_testers', 'tenant_wide': False, 'course_ids': ['course-v1:ORG3+1+1']},
        {'role': 'unknown_role', 'tenant_wide': True},
    ], ['org1', 'org2'], 'en')

    names = {course_id: course.display_name or course_id, 'course-v1:ORG1+missing+1': 'course-v1:ORG1+missing+1'}
    assert rows == [
        {'role': 'staff', 'role_name': 'Staff', 'all_courses': True, 'course_names': []},
        {
            'role': 'instructor', 'role_name': 'Instructor', 'all_courses': False,
            'course_names': [names[key] for key in sorted(names)],
        },
        {'role': 'unknown_role', 'role_name': 'unknown_role', 'all_courses': True, 'course_names': []},
    ]


@pytest.mark.django_db
def test_build_assignments_no_courses():
    """Verify that no course query runs when every assignment is tenant-wide"""
    with patch(f'{EMAILS}.CourseOverview.objects.filter') as mock_filter:
        rows = emails._build_assignments(  # pylint: disable=protected-access
            [{'role': 'staff', 'tenant_wide': True, 'course_ids': []}], ['org1'], 'ar',
        )
    mock_filter.assert_not_called()
    assert rows[0]['role'] == 'staff'


ASSIGNMENTS = [{'role': 'staff', 'tenant_wide': True, 'course_ids': []}]


@pytest.fixture(name='tenant1_ready')
def fixture_tenant1_ready(base_data):  # pylint: disable=unused-argument
    """Tenant 1 with a root URL, a name, a Site row, and user 3 with a profile name"""
    tenant = TenantConfig.objects.get(id=1)
    tenant.lms_configs['LMS_ROOT_URL'] = 'https://s1.sample.com'
    tenant.lms_configs['PLATFORM_NAME'] = 'Tenant One'
    tenant.save()
    Site.objects.get_or_create(domain='s1.sample.com')
    user = get_user_model().objects.get(id=3)
    UserProfile.objects.update_or_create(user=user, defaults={'name': 'User Three'})
    return tenant


@pytest.mark.django_db
def test_deliver_tenant_not_found(base_data):  # pylint: disable=unused-argument
    """Verify an unknown tenant is an error (logged by the task)"""
    with pytest.raises(ValueError, match='Tenant 9999 not found'):
        emails.deliver_role_assigned_email(3, 9999, ASSIGNMENTS)


@pytest.mark.django_db
def test_deliver_switched_off(tenant1_ready, caplog):
    """Verify the tenant switch stops the e-mail before anything else is read"""
    tenant1_ready.lms_configs['ROLE_ASSIGNED_EMAIL_ENABLED'] = False
    tenant1_ready.save()
    caplog.set_level(logging.INFO)
    with patch(f'{EMAILS}._bind_tenant') as mock_bind:
        emails.deliver_role_assigned_email(3, 1, ASSIGNMENTS)
    mock_bind.assert_not_called()
    assert 'role_assigned_email skipped, switched off user_id=3 tenant_id=1' in caplog.text


@pytest.mark.django_db
def test_deliver_inactive_user(tenant1_ready, caplog):  # pylint: disable=unused-argument
    """Verify an inactive user gets nothing"""
    get_user_model().objects.filter(id=3).update(is_active=False)
    caplog.set_level(logging.INFO)
    with patch(f'{EMAILS}._bind_tenant') as mock_bind:
        emails.deliver_role_assigned_email(3, 1, ASSIGNMENTS)
    mock_bind.assert_not_called()
    assert 'role_assigned_email skipped, inactive user user_id=3 tenant_id=1' in caplog.text


@pytest.mark.django_db
@pytest.mark.parametrize('root_url, bound', [('', True), ('https://s1.sample.com', False)])
def test_deliver_tenant_not_bound(tenant1_ready, root_url, bound):
    """Verify a tenant that cannot be bound is an error, never an unbranded e-mail"""
    tenant1_ready.lms_configs['LMS_ROOT_URL'] = root_url
    tenant1_ready.lms_configs['LMS_BASE'] = ''
    tenant1_ready.save()
    with patch(f'{EMAILS}._bind_tenant', return_value=bound), patch(f'{EMAILS}.ace.send') as mock_send:
        with pytest.raises(ValueError, match='could not be bound'):
            emails.deliver_role_assigned_email(3, 1, ASSIGNMENTS)
    mock_send.assert_not_called()


@pytest.mark.django_db
def test_deliver_nothing_on_tenant(tenant1_ready, caplog):  # pylint: disable=unused-argument
    """Verify no e-mail when none of the courses belongs to the tenant"""
    caplog.set_level(logging.INFO)
    with patch(f'{EMAILS}._bind_tenant', return_value=True), patch(f'{EMAILS}._send_and_confirm') as mock_send:
        emails.deliver_role_assigned_email(3, 1, [
            {'role': 'instructor', 'tenant_wide': False, 'course_ids': ['course-v1:ORG3+1+1']},
        ])
    mock_send.assert_not_called()
    assert 'role_assigned_email skipped, nothing on this tenant user_id=3 tenant_id=1' in caplog.text


@pytest.mark.django_db
@pytest.mark.parametrize('user_pref, tenant_name, expected_language, expected_tenant_name', [
    ('ar', 'Tenant One', 'ar', 'Tenant One'),
    (None, '', 'en', 'base platform name'),
])
def test_deliver_success(
    tenant1_ready, caplog, user_pref, tenant_name, expected_language, expected_tenant_name,
):  # pylint: disable=too-many-arguments
    """Verify the message, its language and its context"""
    tenant1_ready.lms_configs['PLATFORM_NAME'] = tenant_name
    tenant1_ready.lms_configs['platform_name'] = tenant_name
    tenant1_ready.save()
    caplog.set_level(logging.INFO)
    with patch(f'{EMAILS}._bind_tenant', return_value=True) as mock_bind, \
            patch(f'{EMAILS}._emulate_tenant_request', return_value=nullcontext()) as mock_emulate, \
            patch(f'{EMAILS}.UserPreference.get_value', return_value=user_pref), \
            patch(f'{EMAILS}._send_and_confirm', return_value=True) as mock_send:
        emails.deliver_role_assigned_email(3, 1, ASSIGNMENTS)

    mock_bind.assert_called_once_with('s1.sample.com')
    assert mock_emulate.call_args.args[0].domain == 's1.sample.com'
    message = mock_send.call_args.args[0]
    assert message.app_label == 'futurex_openedx_extensions'
    assert message.name == 'roleassigned'
    assert message.options['transactional'] is True
    assert message.language == expected_language
    assert message.recipient.lms_user_id == 3
    assert message.recipient.email_address == 'user3@example.com'
    assert message.context['full_name'] == 'User Three'
    assert message.context['tenant_name'] == expected_tenant_name
    assert message.context['sign_in_url'] == 'https://s1.sample.com'
    assert message.context['assignments'] == [
        {'role': 'staff', 'role_name': 'Staff', 'all_courses': True, 'course_names': []},
    ]
    assert message.context['logo_url'] == 'https://example.com/logo.png'
    assert 'course_ids' not in message.context
    assert f'role_assigned_email sent user_id=3 tenant_id=1 language={expected_language}' in caplog.text


@pytest.mark.django_db
def test_deliver_not_delivered(tenant1_ready):  # pylint: disable=unused-argument
    """Verify an e-mail ACE did not deliver is an error"""
    with patch(f'{EMAILS}._bind_tenant', return_value=True), \
            patch(f'{EMAILS}._emulate_tenant_request', return_value=nullcontext()), \
            patch(f'{EMAILS}._send_and_confirm', return_value=False):
        with pytest.raises(RuntimeError, match='ACE did not report the delivery'):
            emails.deliver_role_assigned_email(3, 1, ASSIGNMENTS)


@pytest.mark.django_db
def test_deliver_user_without_profile(tenant1_ready):  # pylint: disable=unused-argument
    """Verify a user with no profile is greeted without a name"""
    UserProfile.objects.filter(user_id=3).delete()
    with patch(f'{EMAILS}._bind_tenant', return_value=True), \
            patch(f'{EMAILS}._emulate_tenant_request', return_value=nullcontext()), \
            patch(f'{EMAILS}._send_and_confirm', return_value=True) as mock_send:
        emails.deliver_role_assigned_email(3, 1, ASSIGNMENTS)
    assert mock_send.call_args.args[0].context['full_name'] == ''


def test_role_names_cover_every_editable_role():
    """Verify every role the API can assign has a display name"""
    assert set(cs.COURSE_ACCESS_ROLES_SUPPORTED_EDIT) <= set(emails.ROLE_NAMES)
