"""
Learner theme (fx-learner) helpers: the data behind the learner theme's Mako templates and its REST endpoints.

Everything here is scoped to ONE tenant: the tenant of the request's site (`request.site.domain`), the same way
`get_config_current_request` finds it. Courses belong to the tenant through its `course_org_filter`.
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

from common.djangoapps.course_modes.models import CourseMode
from common.djangoapps.student.models import CourseEnrollment
from completion_aggregator.models import Aggregator
from django.core.cache import cache
from django.db.models import Count, Q, QuerySet
from django.utils.timezone import now
from eox_tenant.models import TenantConfig
from lms.djangoapps.certificates.api import get_certificates_for_user_by_course_keys
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from openedx.core.djangoapps.content.learning_sequences.api import get_course_outline

from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers.caching import cache_dict
from futurex_openedx_extensions.helpers.converters import relative_url_to_absolute_url
from futurex_openedx_extensions.helpers.course_categories import CourseCategories
from futurex_openedx_extensions.helpers.exceptions import FXCodedException
from futurex_openedx_extensions.helpers.extractors import (
    dot_separated_path_get_value,
    extract_arabic_name_from_user,
    extract_full_name_from_user,
)
from futurex_openedx_extensions.helpers.models import CourseCertificateIssuance, CourseLearnerMeta
from futurex_openedx_extensions.helpers.tenants import (  # pylint: disable=unused-import
    apply_learner_theme,
    get_all_tenants_info,
    get_course_org_filter_list,
)
from futurex_openedx_extensions.helpers.upload import rewrite_legacy_cloudfront_asset_urls

logger = logging.getLogger(__name__)

PROGRAM_STATUS_OPEN = 'open'
PROGRAM_STATUS_UPCOMING = 'upcoming'
PROGRAM_STATUS_FULL = 'full'
PROGRAM_STATUS_CLOSED = 'closed'

UNITS_CACHE_TIMEOUT = 3600

# catalog_visibility: `both` = listed in the catalogue + About page, `about` = About page by link only, `none` = hidden
CATALOG_VISIBILITY_LISTED = 'both'
CATALOG_VISIBILITY_ABOUT_PAGE = ['about', 'both']

# Same accepted forms as eox_nelp.effort (HH:MM, a whole number, a decimal); used when eox-nelp is not installed
EFFORT_HH_MM = re.compile(r'^(\d+):([0-5]\d)$')
EFFORT_INTEGER = re.compile(r'^\d+$')
EFFORT_DECIMAL = re.compile(r'^\d+\.\d+$')

# The link targets the learner pages may print in an href, and the colour form the theme accepts
SAFE_URL_SCHEMES = ('http', 'https', 'mailto', 'tel')
SCHEMELESS_HOST_URL = re.compile(
    r'^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+'
    r'(?::[0-9]{1,5})?(?:[/?#].*)?$'
)
HEX_COLOR = re.compile(r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$')
BRAND_COLOR_TYPE = 'primary_color'

# The theme's page names (fx_static_content.html get_all_fx_page_names) and their paths
FX_PAGE_PATHS = {
    'home': '',
    'courses': 'courses',
    'about-us': 'about',
    'contact-us': 'contact',
    'blog': 'blog',
    'donate': 'donate',
    'terms': 'tos',
    'privacy': 'privacy',
    'help': 'help',
    'faq': 'faq',
    'jobs': 'jobs',
    'news': 'news',
    'press': 'press',
    'media-kit': 'media-kit',
}

LEARNER_THEME_URLS = {
    'home': '/',
    'catalog': '/courses',
    'about': '/about',
    'my': cs.LEARNER_THEME_MFE_URLS['LEARNER_HOME_MICROFRONTEND_URL'],
    'certificates': '/learner/certificates',
    'profile': cs.LEARNER_THEME_MFE_URLS['ACCOUNT_MICROFRONTEND_URL'],
    'login': '/login',
    'logout': '/logout',
}


def get_request_tenant_id(request: Any) -> int | None:
    """
    Return the tenant of the request's site, or None.

    :param request: The request
    :type request: Any
    :return: The tenant ID
    :rtype: int | None
    """
    domain = getattr(getattr(request, 'site', None), 'domain', None)
    if not domain:
        return None
    return get_all_tenants_info()['tenant_by_site'].get(domain)


def _authenticated_user(request: Any) -> Any:
    """Return the request's user when authenticated, else None."""
    user = getattr(request, 'user', None)
    return user if user is not None and user.is_authenticated else None


def _i18n(value: Any) -> Dict[str, str]:
    """Return a {ar, en} dict from a config value (missing languages are empty strings)."""
    value = value if isinstance(value, dict) else {}
    return {'ar': value.get('ar') or '', 'en': value.get('en') or ''}


def _config_value(lms_configs: Dict[str, Any], path: str, default: Any) -> Any:
    """Return the value at the dot-separated path, or the default when it is missing or of another type."""
    _, value = dot_separated_path_get_value(lms_configs, path)
    return value if isinstance(value, type(default)) else default


def safe_url(url: Any) -> str | None:
    """
    Return the URL when it is a link target the learner pages may print in an href: a site-relative path, an
    #anchor, http(s), mailto or tel. A value without a scheme that looks like a host (`www.example.sa/page`) gets
    `https://` in front. Anything else (javascript:, data:, protocol-relative, control characters, not a string)
    gives None. Same rule as the fx-learner theme's `safe_url`.

    :param url: The URL from the tenant config
    :type url: Any
    :return: The URL, or None when it is not safe
    :rtype: str | None
    """
    if not isinstance(url, str):
        return None
    url = url.strip()
    if not url or any(ord(char) < 32 or ord(char) == 127 for char in url) or url.startswith(('//', '/\\')):
        return None
    if url.startswith(('/', '#')):
        return url
    if SCHEMELESS_HOST_URL.match(url):
        return None if any(char.isspace() for char in url) else f'https://{url}'
    try:
        scheme = urlparse(url).scheme.lower()
    except ValueError:
        return None
    return url if scheme in SAFE_URL_SCHEMES else None


def get_brand_color(visual_identity: Any) -> str | None:
    """
    Return the tenant's primary colour (`visual_identity.colors[]` with color_type `primary_color`) as a hex string,
    or None when it is missing or not a hex colour. Same reading as the theme's head-extra.

    :param visual_identity: The tenant's `theme_v2.visual_identity` value
    :type visual_identity: Any
    :return: The hex colour or None
    :rtype: str | None
    """
    colors = visual_identity.get('colors') if isinstance(visual_identity, dict) else None
    brand_color = None
    for color in colors if isinstance(colors, list) else []:
        if not isinstance(color, dict) or color.get('color_type') != BRAND_COLOR_TYPE:
            continue
        value = color.get('hex')
        if isinstance(value, str) and HEX_COLOR.match(value):
            brand_color = value
    return brand_color


def resolve_link(link: Any, custom_pages: Dict[str, str]) -> str | None:
    """
    Resolve a theme link section ({page, custom_url}) to a URL, the same way the theme's get_fx_link_sections does.
    An external link that is not a safe link target (see `safe_url`) is invalid.

    :param link: The link section
    :type link: Any
    :param custom_pages: Custom page keys mapped to their url slugs
    :type custom_pages: Dict[str, str]
    :return: The URL, or None when the link is invalid
    :rtype: str | None
    """
    if not isinstance(link, dict):
        return None
    page = link.get('page') or ''
    if page in FX_PAGE_PATHS:
        return f'/{FX_PAGE_PATHS[page]}'
    if page == 'external_link':
        return safe_url(link.get('custom_url'))
    if page.replace('-', '_') in custom_pages:
        return f'/p/{custom_pages[page.replace("-", "_")]}'
    return None


def _link_items(sections: Any, custom_pages: Dict[str, str]) -> List[Dict[str, Any]]:
    """Return the valid link sections as [{title, url, new_tab}]."""
    result = []
    for section in sections if isinstance(sections, list) else []:
        url = resolve_link(section, custom_pages)
        if url:
            result.append({
                'title': _i18n(section.get('link_title')),
                'url': url,
                'new_tab': bool(section.get('new_tab')),
            })
    return result


def cache_name_learner_theme_shell(tenant_id: int) -> str:
    """Return the cache name of the tenant's learner theme shell."""
    return f'{cs.CACHE_NAME_LEARNER_THEME_SHELL}_{tenant_id}'


def is_learner_theme_switched_on(lms_configs: Dict[str, Any]) -> bool:
    """Return True when the learner theme is both allowed and enabled in the given config."""
    _, allowed = dot_separated_path_get_value(lms_configs, cs.LEARNER_THEME_ALLOWED_PATH)
    _, enabled = dot_separated_path_get_value(lms_configs, cs.LEARNER_THEME_ENABLED_PATH)
    return allowed is True and enabled is True


@cache_dict(
    timeout='FX_CACHE_TIMEOUT_CONFIG_ACCESS_CONTROL',
    key_generator_or_name=cache_name_learner_theme_shell,
)
def get_learner_theme_shell(tenant_id: int) -> Dict[str, Any]:
    """
    Return the header/footer shell of the tenant's learner pages, from PUBLISHED values only. Cached per tenant and
    cleared together with the tenant's readable config cache.

    The brand is never empty: `site_name` falls back to the platform name and `short_name` to `site_name`, per
    language. `help_url` is the tenant's `entity_identity.help_link`, else its FAQ page. `brand_color` is the
    tenant's visual_identity primary colour (hex) or None. URLs taken from the tenant config are sanitised
    (`safe_url`): an unsafe nav/footer link is omitted, an unsafe `site_url` is None.

    :param tenant_id: The tenant ID
    :type tenant_id: int
    :return: The shell, or an empty dict when the tenant does not exist
    :rtype: Dict[str, Any]
    """
    lms_configs = TenantConfig.objects.filter(id=tenant_id).values_list('lms_configs', flat=True).first()
    if not isinstance(lms_configs, dict):
        return {}

    theme_name = _config_value(lms_configs, 'THEME_OPTIONS.theme.name', '')
    identity = _config_value(lms_configs, 'theme_v2.entity_identity', {})
    header = _config_value(lms_configs, 'theme_v2.header', {})
    footer = _config_value(lms_configs, 'theme_v2.footer', {})
    language = _config_value(lms_configs, 'theme_v2.platform_settings.language', {})
    custom_pages = {
        page['key']: page['url_slug']
        for page in _config_value(lms_configs, 'theme_v2.custom_pages', [])
        if isinstance(page, dict) and page.get('key') and page.get('url_slug')
    }
    platform_name = lms_configs.get('PLATFORM_NAME') or lms_configs.get('platform_name') or ''
    site_name = {
        lang: name or platform_name
        for lang, name in _i18n(_config_value(lms_configs, 'theme_v2.platform_settings.site_name', {})).items()
    }
    languages = language.get('languages') if isinstance(language.get('languages'), list) else []
    languages = languages or ['en']
    default_language = language.get('default_language')

    return {
        'active': is_learner_theme_switched_on(lms_configs) and theme_name == cs.LEARNER_THEME_NAME,
        'logo_url': rewrite_legacy_cloudfront_asset_urls(lms_configs.get('logo_image_url') or None),
        'brand_color': get_brand_color(_config_value(lms_configs, 'theme_v2.visual_identity', {})),
        'site_name': site_name,
        'short_name': {lang: name or site_name[lang] for lang, name in _i18n(identity.get('short_name')).items()},
        'parent_org': _i18n(identity.get('parent_org')),
        'nav': _link_items(header.get('sections'), custom_pages),
        'footer': {
            'links': _link_items(footer.get('sections'), custom_pages),
            'social': [
                {'provider': link['provider'], 'value': link['value']}
                for link in footer.get('social_media_links') or []
                if isinstance(link, dict) and link.get('provider') and link.get('value')
            ],
            'copyright': _i18n(footer.get('copyrights_text')),
            'site_label': _i18n(identity.get('site_label')),
            'site_url': safe_url(identity.get('site_url')),
        },
        'help_url': resolve_link(identity.get('help_link'), custom_pages) or f'/{FX_PAGE_PATHS["faq"]}',
        'languages': languages,
        'default_language': default_language if default_language in languages else languages[0],
        'urls': dict(LEARNER_THEME_URLS),
    }


def is_learner_theme_active(tenant_id: int) -> bool:
    """
    Return True when the learner theme is live for the tenant: allowed AND enabled (published) AND the tenant's theme
    is fx-learner (the publish hook did switch it).

    :param tenant_id: The tenant ID
    :type tenant_id: int
    :return: True if active
    :rtype: bool
    """
    return get_learner_theme_shell(tenant_id).get('active', False) is True


def get_tenant_courses_queryset(tenant_id: int) -> QuerySet:
    """
    Return the courses of the tenant (by its course_org_filter), with no visibility filter.

    :param tenant_id: The tenant ID
    :type tenant_id: int
    :return: CourseOverview queryset
    :rtype: QuerySet
    """
    orgs = get_course_org_filter_list([tenant_id], ignore_invalid_tenant_ids=True)['course_org_filter_list']
    return CourseOverview.objects.filter(org__in=orgs)


def get_tenant_catalog_queryset(tenant_id: int) -> QuerySet:
    """
    Return the tenant's catalogue: courses listed in the catalogue (catalog_visibility `both`, not staff-only)
    whose enrollment is open OR that have not ended. A course with catalog_visibility `about` is reachable by its
    About link only and is never listed. This is the theme's /courses rule (decision dc17-open-or-not-ended); the
    home page rule (open AND not ended) is the subset with status `open`, `full` or `upcoming` that has not ended.

    :param tenant_id: The tenant ID
    :type tenant_id: int
    :return: CourseOverview queryset
    :rtype: QuerySet
    """
    now_time = now()
    enrollment_open = (
        (Q(enrollment_start__isnull=True) | Q(enrollment_start__lte=now_time)) &
        (Q(enrollment_end__isnull=True) | Q(enrollment_end__gt=now_time))
    )
    not_ended = Q(end__isnull=True) | Q(end__gt=now_time)
    return get_tenant_courses_queryset(tenant_id).filter(
        catalog_visibility=CATALOG_VISIBILITY_LISTED,
        visible_to_staff_only=False,
    ).filter(enrollment_open | not_ended).order_by('-start', 'id')


def _effort_patterns() -> Tuple[Any, Any, Any]:
    """Return eox-nelp's effort patterns when eox-nelp is installed, else the local copies."""
    try:
        from eox_nelp import effort  # pylint: disable=import-outside-toplevel
        return effort.HH_MM, effort.INTEGER, effort.DECIMAL
    except (ImportError, AttributeError):
        return EFFORT_HH_MM, EFFORT_INTEGER, EFFORT_DECIMAL


def parse_effort_hours(effort: Any) -> float | int | None:
    """
    Return the course Effort as a number of hours, or None when it is blank or not a number. Accepted forms are
    eox-nelp's: "HH:MM", a whole number of hours, a decimal.

    :param effort: The course Effort text
    :type effort: Any
    :return: Hours
    :rtype: float | int | None
    """
    text = '' if effort is None else str(effort).strip()
    hh_mm, integer, decimal = _effort_patterns()
    result: float | int | None = None
    match = hh_mm.match(text)
    if match:
        hours, minutes = int(match.group(1)), int(match.group(2))
        result = hours if not minutes else round(hours + minutes / 60, 2)
    elif integer.match(text):
        result = int(text)
    elif decimal.match(text):
        result = float(text)
    return result


def get_course_units_count(course_key: Any) -> int:
    """
    Return the number of chapters (sections) of the course that are not staff-only, from the learning_sequences
    outline (a cheap DB read). Cached per course for an hour; 0 when the course has no outline.

    :param course_key: The course key
    :type course_key: Any
    :return: Number of units
    :rtype: int
    """
    cache_key = f'fx_learner_theme_units_{course_key}'
    units = cache.get(cache_key)
    if units is None:
        try:
            outline = get_course_outline(course_key)
            units = len([
                section for section in outline.sections
                if not getattr(getattr(section, 'visibility', None), 'visible_to_staff_only', False)
            ])
        except Exception as exc:
            logger.info('learner theme: no outline for course %s (%s)', course_key, exc)
            units = 0
        cache.set(cache_key, units, UNITS_CACHE_TIMEOUT)
    return units


def get_program_status(course: CourseOverview, active_enrollments: int, now_time: Any = None) -> str:
    """
    Return the enrollment status of the course: closed (enrollment ended or course ended), upcoming (enrollment not
    started), full (max_student_enrollments_allowed reached), else open.

    :param course: The course
    :type course: CourseOverview
    :param active_enrollments: Number of active enrollments of the course
    :type active_enrollments: int
    :param now_time: The time to compare to (default: now)
    :type now_time: Any
    :return: The status
    :rtype: str
    """
    now_time = now_time or now()
    if (course.enrollment_end and course.enrollment_end <= now_time) or (course.end and course.end <= now_time):
        return PROGRAM_STATUS_CLOSED
    if course.enrollment_start and course.enrollment_start > now_time:
        return PROGRAM_STATUS_UPCOMING
    max_allowed = course.max_student_enrollments_allowed
    if max_allowed and active_enrollments >= max_allowed:
        return PROGRAM_STATUS_FULL
    return PROGRAM_STATUS_OPEN


def get_course_category_ids(tenant_id: int) -> Tuple[Dict[str, List[str]], List[Dict[str, Any]]]:
    """
    Return the tenant's course categories: {course_id: [category ids]} and the ordered [{id, name: {ar, en}}].

    :param tenant_id: The tenant ID
    :type tenant_id: int
    :return: (course categories, categories)
    :rtype: Tuple[Dict[str, List[str]], List[Dict[str, Any]]]
    """
    try:
        category_manager = CourseCategories(tenant_id)
    except FXCodedException as exc:
        logger.warning('learner theme: unable to read the course categories of tenant %s (%s)', tenant_id, exc)
        return {}, []

    course_categories: Dict[str, List[str]] = {}
    categories = []
    for category_id in category_manager.sorting:
        category = category_manager.categories.get(category_id) or {}
        categories.append({'id': category_id, 'name': _i18n(category.get('label'))})
        for course_id in category.get('courses') or []:
            course_categories.setdefault(course_id, []).append(category_id)
    return course_categories, categories


def get_course_prices(course_ids: List[Any]) -> Dict[str, Tuple[int, str | None]]:
    """
    Return the price of each paid course: the lowest price among its paid modes (any mode with a price above zero
    that has not expired) and the currency of that mode (upper case), as {course_id: (price, currency)}. A course
    with no paid mode is not in the result.

    :param course_ids: The course keys
    :type course_ids: List[Any]
    :return: {course_id: (price, currency)}
    :rtype: Dict[str, Tuple[int, str | None]]
    """
    paid_modes = CourseMode.objects.filter(course_id__in=course_ids, min_price__gt=0).filter(
        Q(_expiration_datetime__isnull=True) | Q(_expiration_datetime__gt=now()),
    ).order_by('min_price', 'id').values_list('course_id', 'min_price', 'currency')
    result: Dict[str, Tuple[int, str | None]] = {}
    for course_id, price, currency in paid_modes:
        result.setdefault(str(course_id), (price, (currency or '').upper() or None))
    return result


def _iso(value: Any) -> str | None:
    """Return the datetime as ISO text, or None."""
    return value.isoformat() if value else None


def build_programs(  # pylint: disable=too-many-locals
    tenant_id: int, courses: List[CourseOverview], user: Any, course_categories: Dict[str, List[str]] | None = None,
) -> List[Dict[str, Any]]:
    """
    Return the program dicts of the given courses (one query per data source, not per course).

    :param tenant_id: The tenant ID (for the course categories)
    :type tenant_id: int
    :param courses: The courses
    :type courses: List[CourseOverview]
    :param user: The authenticated user (for `enrolled`), or None
    :type user: Any
    :param course_categories: Pre-loaded {course_id: [category ids]}; loaded from the tenant when None
    :type course_categories: Dict[str, List[str]] | None
    :return: Program dicts
    :rtype: List[Dict[str, Any]]
    """
    if not courses:
        return []
    if course_categories is None:
        course_categories, _ = get_course_category_ids(tenant_id)

    course_ids = [course.id for course in courses]
    meta = CourseLearnerMeta.get_meta_for_courses(course_ids)
    disabled_issuance = {
        str(key) for key in CourseCertificateIssuance.objects.filter(
            course_key__in=course_ids, issuance_enabled=False,
        ).values_list('course_key', flat=True)
    }
    prices = get_course_prices(course_ids)
    limited_ids = [course.id for course in courses if course.max_student_enrollments_allowed]
    enrollment_counts = {
        str(row['course_id']): row['count'] for row in CourseEnrollment.objects.filter(
            course_id__in=limited_ids, is_active=True,
        ).values('course_id').annotate(count=Count('id'))
    } if limited_ids else {}
    enrolled_ids = {
        str(course_id) for course_id in CourseEnrollment.objects.filter(
            user_id=user.id, course_id__in=course_ids, is_active=True,
        ).values_list('course_id', flat=True)
    } if user else set()

    now_time = now()
    result = []
    for course in courses:
        course_id = str(course.id)
        course_meta = meta.get(course_id, {})
        price, currency = prices.get(course_id, (None, None))
        result.append({
            'id': course_id,
            'title': course.display_name,
            'image_url': course.course_image_url or None,
            'about_url': f'/courses/{course_id}/about',
            'effort_hours': parse_effort_hours(course.effort),
            'units': get_course_units_count(course.id),
            'level': course_meta.get('level'),
            'learning_mode': course_meta.get('learning_mode'),
            'has_certificate': bool(course.has_any_active_web_certificate) and course_id not in disabled_issuance,
            'category_ids': course_categories.get(course_id, []),
            'status': get_program_status(course, enrollment_counts.get(course_id, 0), now_time),
            'start_date': _iso(course.start),
            'enrolled': course_id in enrolled_ids,
            'price': price,
            'currency': currency,
        })
    return result


def get_catalog(request: Any) -> Dict[str, Any]:
    """
    Return the catalogue of the request's tenant: {results: [program dict], categories: [{id, name}]}.

    :param request: The request
    :type request: Any
    :return: The catalogue
    :rtype: Dict[str, Any]
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        return {'results': [], 'categories': []}

    course_categories, categories = get_course_category_ids(tenant_id)
    return {
        'results': build_programs(
            tenant_id,
            list(get_tenant_catalog_queryset(tenant_id)),
            _authenticated_user(request),
            course_categories=course_categories,
        ),
        'categories': categories,
    }


def get_learner_theme_catalog(request: Any) -> List[Dict[str, Any]]:
    """
    Mako helper: the program dicts of the request's tenant catalogue.

    :param request: The request
    :type request: Any
    :return: Program dicts
    :rtype: List[Dict[str, Any]]
    """
    return get_catalog(request)['results']


def get_learner_theme_categories(request: Any) -> List[Dict[str, Any]]:
    """
    Mako helper: the ordered course categories of the request's tenant, [{id, name: {ar, en}}]. The same list the
    catalogue endpoint returns as `categories`, in the id space of the program dicts' `category_ids`.

    :param request: The request
    :type request: Any
    :return: The categories
    :rtype: List[Dict[str, Any]]
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        return []
    return get_course_category_ids(tenant_id)[1]


def get_learner_theme_program(request: Any, course_key: Any) -> Dict[str, Any] | None:
    """
    Mako helper: the program dict of one course of the request's tenant that has an About page (catalog_visibility
    `about` or `both`, whatever its dates, so the About page of a closed course still renders), or None when the
    course is not in the tenant or is hidden (catalog_visibility `none`).

    :param request: The request
    :type request: Any
    :param course_key: The course key (CourseKey or string)
    :type course_key: Any
    :return: The program dict or None
    :rtype: Dict[str, Any] | None
    """
    tenant_id = get_request_tenant_id(request)
    if not tenant_id:
        return None
    try:
        course_key = CourseKey.from_string(str(course_key))
    except InvalidKeyError:
        return None

    course = get_tenant_courses_queryset(tenant_id).filter(
        id=course_key, catalog_visibility__in=CATALOG_VISIBILITY_ABOUT_PAGE,
    ).first()
    if not course:
        return None
    return build_programs(tenant_id, [course], _authenticated_user(request))[0]


def mask_email(email: str) -> str:
    """
    Mask the local part of an email: the first two characters are kept ("al***@example.com").

    :param email: The email
    :type email: str
    :return: The masked email ('' when blank)
    :rtype: str
    """
    if not email or '@' not in email:
        return ''
    local, domain = email.split('@', 1)
    return f'{local[:2]}***@{domain}'


def get_learner_user_info(user: Any) -> Dict[str, Any]:
    """
    Return the display data of the user for the learner pages: {full_name, first_name, arabic_name, masked_email}.
    The username and the unmasked email are never included. `arabic_name` comes from the custom registration form
    (`custom_reg_form` ExtraInfo), and is None when that app is not installed or the user has none.

    :param user: The user
    :type user: Any
    :return: The user info
    :rtype: Dict[str, Any]
    """
    full_name = extract_full_name_from_user(user)
    return {
        'full_name': full_name,
        'first_name': full_name.split()[0] if full_name.split() else '',
        'arabic_name': extract_arabic_name_from_user(user) or None,
        'masked_email': mask_email(user.email),
    }


def _percent(value: Any) -> int:
    """Return a 0-1 fraction as a whole percent."""
    return int(round((value or 0) * 100))


def _grade_percent(grade: Any) -> int | None:
    """Return the certificate grade ("0.85") as a whole percent, or None."""
    try:
        return int(round(Decimal(str(grade)) * 100))
    except (InvalidOperation, ValueError):
        return None


def _absolute(url: str | None, request: Any) -> str | None:
    """Return a relative URL made absolute on the request's site; absolute URLs and None unchanged."""
    if url and url.startswith('/'):
        return relative_url_to_absolute_url(url, request) or url
    return url or None


def _resume_url(course_id: str) -> str:
    """Return the courseware URL of the course (the learning MFE opens the last visited unit)."""
    return f'/courses/{course_id}/courseware'


def get_learner_enrollments(tenant_id: int, user: Any) -> List[Tuple[CourseEnrollment, CourseOverview]]:
    """
    Return the user's active enrollments in the tenant's courses, newest first.

    :param tenant_id: The tenant ID
    :type tenant_id: int
    :param user: The user
    :type user: Any
    :return: (enrollment, course) pairs
    :rtype: List[Tuple[CourseEnrollment, CourseOverview]]
    """
    courses = {
        str(course.id): course
        for course in get_tenant_courses_queryset(tenant_id).filter(
            id__in=CourseEnrollment.objects.filter(user_id=user.id, is_active=True).values('course_id'),
        )
    }
    enrollments = CourseEnrollment.objects.filter(
        user_id=user.id, is_active=True, course_id__in=list(courses.keys()),
    ).order_by('-created', '-id')
    return [(enrollment, courses[str(enrollment.course_id)]) for enrollment in enrollments]


def get_learner_certificates_data(tenant_id: int, user: Any) -> Dict[str, Dict[str, Any]]:
    """
    Return the user's downloadable certificates in the tenant's courses, keyed by course id string.

    :param tenant_id: The tenant ID
    :type tenant_id: int
    :param user: The user
    :type user: Any
    :return: {course_id: certificate data from the certificates API}
    :rtype: Dict[str, Dict[str, Any]]
    """
    course_keys = list(get_tenant_courses_queryset(tenant_id).filter(
        id__in=CourseEnrollment.objects.filter(user_id=user.id).values('course_id'),
    ).values_list('id', flat=True))
    if not course_keys:
        return {}

    certificates = get_certificates_for_user_by_course_keys(user, course_keys)
    return {
        str(course_key): data for course_key, data in certificates.items()
        if data and data.get('status') == 'downloadable' and data.get('download_url')
    }


def get_learner_programs(request: Any) -> Dict[str, Any]:  # pylint: disable=too-many-locals
    """
    Return the request user's programs in the request's tenant:
    {user: {full_name, first_name, arabic_name, masked_email} | None, stats: {in_progress, completed, certificates},
    resume: {title, progress_percent, resume_url} | None, results: [...]}.

    `completed` = the learner holds a downloadable certificate or the course completion is 100%. `resume` is the
    not-completed program with the latest activity, None when every program is completed (or there is none).

    :param request: The request (authenticated)
    :type request: Any
    :return: The learner's programs
    :rtype: Dict[str, Any]
    """
    tenant_id = get_request_tenant_id(request)
    user = _authenticated_user(request)
    empty: Dict[str, Any] = {
        'user': get_learner_user_info(user) if user else None,
        'stats': {'in_progress': 0, 'completed': 0, 'certificates': 0},
        'resume': None,
        'results': [],
    }
    if not tenant_id or not user:
        return empty

    enrollments = get_learner_enrollments(tenant_id, user)
    if not enrollments:
        return empty

    course_ids = [course.id for _, course in enrollments]
    completion = {
        str(row['course_key']): row for row in Aggregator.objects.filter(
            user_id=user.id, aggregation_name='course', course_key__in=course_ids,
        ).values('course_key', 'percent', 'modified')
    }
    certificates = get_learner_certificates_data(tenant_id, user)

    results = []
    resume_candidates = []
    for enrollment, course in enrollments:
        course_id = str(course.id)
        percent = (completion.get(course_id) or {}).get('percent') or 0
        certificate = certificates.get(course_id)
        completed = bool(certificate) or percent >= 1
        item = {
            'course_id': course_id,
            'title': course.display_name,
            'image_url': course.course_image_url or None,
            'progress_percent': _percent(percent),
            'next_step': None,
            'pass_grade_percent': (
                _percent(float(course.lowest_passing_grade)) if course.lowest_passing_grade is not None else None
            ),
            'resume_url': _resume_url(course_id),
            'completed': completed,
            'certificate_url': _absolute(certificate['download_url'], request) if certificate else None,
        }
        results.append(item)
        if not completed:
            last_activity = (completion.get(course_id) or {}).get('modified') or enrollment.created
            resume_candidates.append((last_activity, item))

    resume = None
    if resume_candidates:
        _, latest = max(resume_candidates, key=lambda candidate: candidate[0])
        resume = {
            'title': latest['title'],
            'progress_percent': latest['progress_percent'],
            'resume_url': latest['resume_url'],
        }

    completed_count = len([item for item in results if item['completed']])
    return {
        'user': empty['user'],
        'stats': {
            'in_progress': len(results) - completed_count,
            'completed': completed_count,
            'certificates': len(certificates),
        },
        'resume': resume,
        'results': results,
    }


def get_learner_certificates(request: Any) -> List[Dict[str, Any]]:
    """
    Return the request user's downloadable certificates in the request's tenant.

    The certificate URL is the platform's own (the HTML certificate page `/certificates/<verify uuid>` when HTML
    certificates are enabled for the course, else the PDF `download_url`); it is the public, verifiable page, so
    preview, download and verify all point at it.

    :param request: The request (authenticated)
    :type request: Any
    :return: The learner's certificates
    :rtype: List[Dict[str, Any]]
    """
    tenant_id = get_request_tenant_id(request)
    user = _authenticated_user(request)
    if not tenant_id or not user:
        return []

    certificates = get_learner_certificates_data(tenant_id, user)
    if not certificates:
        return []

    titles = dict(
        (str(course_id), title) for course_id, title in CourseOverview.objects.filter(
            id__in=[CourseKey.from_string(course_id) for course_id in certificates],
        ).values_list('id', 'display_name')
    )
    issuer = (get_all_tenants_info()['info'].get(tenant_id) or {}).get('platform_name') or ''
    result = []
    for course_id, certificate in sorted(
        certificates.items(), key=lambda item: item[1].get('created') or now(), reverse=True,
    ):
        url = _absolute(certificate['download_url'], request)
        result.append({
            'course_id': course_id,
            'title': titles.get(course_id, ''),
            'issuer': issuer,
            'issued_at': _iso(certificate.get('created')),
            'grade_percent': _grade_percent(certificate.get('grade')),
            'verify_code': certificate.get('uuid') or None,
            'preview_url': url,
            'download_url': url,
            'verify_url': url,
        })
    return result


def get_learner_theme_menu(request: Any) -> Dict[str, Any] | None:
    """
    Mako helper: the user menu of the learner header. None for anonymous users.

    :param request: The request
    :type request: Any
    :return: {full_name, first_name, arabic_name, masked_email, programs_count, certificates_count,
        resume: {title, progress_percent, resume_url} | None}
    :rtype: Dict[str, Any] | None
    """
    user = _authenticated_user(request)
    if not user:
        return None

    programs = get_learner_programs(request)
    return {
        **get_learner_user_info(user),
        'programs_count': len(programs['results']),
        'certificates_count': programs['stats']['certificates'],
        'resume': programs['resume'],
    }
