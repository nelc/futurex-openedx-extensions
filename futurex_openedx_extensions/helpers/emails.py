"""
Role-assigned e-mail: sent to a user who was given a role through the FX roles API.

The template folder of the message is `<APP_LABEL>/edx_ace/<lower-cased class name>/email/`, so `RoleAssigned`
lives in `helpers/templates/futurex_openedx_extensions/edx_ace/roleassigned/email/`. A theme overrides the e-mail by
shipping a file with the same path.

Per-tenant setting (lms_configs, read fresh on every send):
    ROLE_ASSIGNED_EMAIL_ENABLED   the e-mail is sent unless this is exactly `false`
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Dict, Generator, List
from urllib.parse import urlparse

from crum import CurrentRequestUserMiddleware, get_current_request
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.utils import translation
from django.utils.translation import pgettext_lazy
from edx_ace import ace
from edx_ace.recipient import Recipient
from edx_ace.signals import ACE_MESSAGE_SENT
from eox_tenant.constants import LMS_CONFIG_COLUMN
from eox_tenant.models import TenantConfig
from eox_tenant.signals import _update_settings, can_keep_settings
from openedx.core.djangoapps.ace_common.message import BaseMessageType
from openedx.core.djangoapps.ace_common.template_context import get_base_template_context
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from openedx.core.djangoapps.user_api.models import UserPreference
from openedx.core.lib.celery.task_utils import emulate_http_request

from futurex_openedx_extensions.helpers.tenants import fix_lms_base

log = logging.getLogger(__name__)

ROLE_ASSIGNED_EMAIL_ENABLED = 'ROLE_ASSIGNED_EMAIL_ENABLED'

# Languages the e-mail is written in; anything else falls through to the next source, English last
SUPPORTED_LANGUAGES = ('ar', 'en')
DEFAULT_LANGUAGE = 'en'

# Same wording as the FX dashboard role labels. The context keeps these msgids apart from the platform's own "Staff"
ROLE_NAMES = {
    'beta_testers': pgettext_lazy('fx role name', 'Beta Testers'),
    'ccx_coach': pgettext_lazy('fx role name', 'CCX Coach'),
    'data_researcher': pgettext_lazy('fx role name', 'Data Researcher'),
    'finance_admin': pgettext_lazy('fx role name', 'Finance Admin'),
    'instructor': pgettext_lazy('fx role name', 'Instructor'),
    'library_user': pgettext_lazy('fx role name', 'Library User'),
    'limit-staff': pgettext_lazy('fx role name', 'Limited Staff'),
    'org_course_creator_group': pgettext_lazy('fx role name', 'Organization Course Creator'),
    'staff': pgettext_lazy('fx role name', 'Staff'),
}


class RoleAssigned(BaseMessageType):  # pylint: disable=too-few-public-methods
    """The user was given one or more roles on a tenant through the FX roles API."""
    APP_LABEL = 'futurex_openedx_extensions'

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.options['transactional'] = True


def _supported(code: str | None) -> str | None:
    """Return the supported language for a code like "ar", "en-us" or "ar_SA", else None."""
    primary = (code or '').replace('_', '-').split('-')[0].lower()
    return primary if primary in SUPPORTED_LANGUAGES else None


def resolve_language(user_language: str | None, tenant_language: str | None) -> str:
    """The user's saved language, then the tenant/platform default, then English."""
    return _supported(user_language) or _supported(tenant_language) or DEFAULT_LANGUAGE


def is_role_assigned_email_enabled(lms_configs: dict) -> bool:
    """Default ON: only an explicit `false` turns the e-mail off for the tenant."""
    return lms_configs.get(ROLE_ASSIGNED_EMAIL_ENABLED, True) is not False


def _tenant_orgs(lms_configs: dict) -> List[str]:
    """Lower-cased orgs of the tenant (course_org_filter may be a string or a list)."""
    orgs = lms_configs.get('course_org_filter') or []
    if isinstance(orgs, str):
        orgs = [orgs]
    return [org.lower() for org in orgs if isinstance(org, str)]


def _tenant_root_url(lms_configs: dict) -> str:
    """LMS root URL of the tenant (LMS_ROOT_URL, else built from LMS_BASE)."""
    return (lms_configs.get('LMS_ROOT_URL') or '').strip() or fix_lms_base((lms_configs.get('LMS_BASE') or '').strip())


def _bind_tenant(domain: str) -> bool:
    """Make `django.conf.settings` carry the tenant values (logo, name, language, theme) for the e-mail."""
    if not can_keep_settings(domain):  # also resets what a previous tenant left in settings
        _update_settings(domain, LMS_CONFIG_COLUMN)
    return getattr(settings, 'EDNX_TENANT_DOMAIN', None) == domain


@contextmanager
def _emulate_tenant_request(site: Site, user: Any) -> Generator[None, None, None]:
    """
    Fake request for a Celery worker: the tenant Site and the tenant's OWN theme (eox-theming resolves it from the
    tenant settings bound by _bind_tenant). Without it a worker renders with the global site theme.
    """
    # Imported on use: eox-theming's middleware reads LMS-only settings when it is imported, and eox-tenant's proxy
    # model needs the platform's site configuration app
    from eox_tenant.tenant_wise.proxies import TenantSiteConfigProxy  # pylint: disable=import-outside-toplevel
    from eox_theming.theming.middleware import EoxThemeMiddleware  # pylint: disable=import-outside-toplevel

    site.configuration = TenantSiteConfigProxy()  # what eox-tenant sets on a real request
    with emulate_http_request(
        site=site, user=user, middleware_classes=[CurrentRequestUserMiddleware, EoxThemeMiddleware],
    ):
        if not hasattr(get_current_request(), 'site_theme'):
            raise RuntimeError('The tenant theme could not be resolved for the e-mail')
        yield


def _send_and_confirm(message: Any) -> bool:
    """Send the ACE message; True only if ACE reports it delivered (ace.send swallows template/channel errors)."""
    delivered = []

    def _on_sent(sender: Any, message: Any, **kwargs: Any) -> None:  # pylint: disable=unused-argument
        delivered.append(message['uuid'])

    ACE_MESSAGE_SENT.connect(_on_sent, weak=False)
    try:
        ace.send(message)
    finally:
        ACE_MESSAGE_SENT.disconnect(_on_sent)

    return str(message.uuid) in delivered


def _build_assignments(assignments: List[Dict[str, Any]], orgs: List[str], language: str) -> List[Dict[str, Any]]:
    """
    Template rows of the assignments that belong to the tenant: role name in the e-mail language, and either
    all courses (tenant-wide) or the display names of the tenant's own courses of that assignment.
    """
    course_ids = {course_id for item in assignments for course_id in (item.get('course_ids') or [])}
    names = {
        str(course_id): display_name for course_id, display_name in CourseOverview.objects.filter(
            id__in=list(course_ids),
        ).values_list('id', 'display_name')
    } if course_ids else {}

    rows = []
    with translation.override(language):
        for item in assignments:
            course_names = []
            if not item['tenant_wide']:
                course_names = [
                    names.get(course_id) or course_id for course_id in sorted(item.get('course_ids') or [])
                    if course_id.split(':')[-1].split('+')[0].lower() in orgs
                ]
                if not course_names:
                    continue
            rows.append({
                'role': item['role'],
                'role_name': str(ROLE_NAMES.get(item['role'], item['role'])),
                'all_courses': bool(item['tenant_wide']),
                'course_names': course_names,
            })
    return rows


def deliver_role_assigned_email(user_id: int, tenant_id: int, assignments: List[Dict[str, Any]]) -> None:
    """
    Send the role-assigned e-mail of one user on one tenant. Skips (with an INFO line) when the tenant switched it
    off, the user is inactive, or none of the assignments belongs to the tenant; raises on anything that should
    have worked, so the task logs the failure line.

    :param user_id: The user who was given the role(s)
    :param tenant_id: The tenant the e-mail is branded for
    :param assignments: [{'role': str, 'tenant_wide': bool, 'course_ids': [str]}]
    """
    lms_configs = TenantConfig.objects.filter(id=tenant_id).values_list(LMS_CONFIG_COLUMN, flat=True).first()
    if lms_configs is None:
        raise ValueError(f'Tenant {tenant_id} not found')

    if not is_role_assigned_email_enabled(lms_configs):
        log.info('role_assigned_email skipped, switched off user_id=%s tenant_id=%s', user_id, tenant_id)
        return

    user = get_user_model().objects.select_related('profile').get(id=user_id)
    if not user.is_active:
        log.info('role_assigned_email skipped, inactive user user_id=%s tenant_id=%s', user_id, tenant_id)
        return

    root_url = _tenant_root_url(lms_configs)
    domain = urlparse(root_url).hostname
    if not domain or not _bind_tenant(domain):
        raise ValueError(f'Tenant {tenant_id} could not be bound (domain={domain})')

    language = resolve_language(UserPreference.get_value(user, 'pref-lang'), settings.LANGUAGE_CODE)
    rows = _build_assignments(assignments, _tenant_orgs(lms_configs), language)
    if not rows:
        log.info('role_assigned_email skipped, nothing on this tenant user_id=%s tenant_id=%s', user_id, tenant_id)
        return

    context = {
        'full_name': getattr(getattr(user, 'profile', None), 'name', '') or '',  # blank: the templates greet without
        'tenant_name': (
            (lms_configs.get('PLATFORM_NAME') or '').strip() or (lms_configs.get('platform_name') or '').strip()
        ),
        'sign_in_url': root_url,
        'assignments': rows,
    }
    site = Site.objects.get(domain=domain)
    with _emulate_tenant_request(site, user):
        context = {**get_base_template_context(site), **context}
        context['tenant_name'] = context['tenant_name'] or context.get('platform_name') or ''
        message = RoleAssigned().personalize(
            Recipient(lms_user_id=user.id, email_address=user.email), language, context,
        )
        if not _send_and_confirm(message):
            raise RuntimeError('ACE did not report the delivery')

    log.info('role_assigned_email sent user_id=%s tenant_id=%s language=%s', user_id, tenant_id, language)
