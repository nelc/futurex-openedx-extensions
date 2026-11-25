"""Tests for middlewares."""
from unittest.mock import Mock, patch

import pytest
from django.test import RequestFactory
from eox_theming.configuration import ThemingConfiguration

from futurex_openedx_extensions.dashboard import middlewares
from futurex_openedx_extensions.dashboard.middlewares import FutureXThemePreviewMiddleware
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.models import ConfigAccessControl, DraftConfig


@pytest.fixture
def request_factory():
    return RequestFactory()


@pytest.fixture
def middleware():
    return FutureXThemePreviewMiddleware(get_response=lambda request: None)


def test_process_request_with_theme_preview_cookie(
    request_factory, middleware,
):  # pylint: disable=redefined-outer-name
    """Verify that the middleware sets the site_theme when the theme-preview cookie is set to `yes`."""
    request = request_factory.get('/')
    request.COOKIES['theme-preview'] = 'yes'
    request.user = Mock(is_authenticated=True)
    assert not hasattr(request, 'site_theme')

    middleware.process_request(request)

    assert hasattr(request, 'site_theme')
    assert request.site_theme.site_id == 1
    assert request.site_theme.theme_dir_name == 'indigo'
    assert request.fx_preview_theme == {'name': 'indigo'}


def test_process_request_without_theme_preview_cookie(
    request_factory, middleware,
):  # pylint: disable=redefined-outer-name
    """Verify that the middleware does not set the site_theme when the theme-preview cookie is not set."""
    request = request_factory.get('/')

    middleware.process_request(request)

    assert not hasattr(request, 'site_theme')
    assert not hasattr(request, 'fx_preview_theme')


@pytest.mark.parametrize('user', [Mock(is_authenticated=False), None])
def test_process_request_anonymous_with_cookie_is_not_a_preview(
    request_factory, middleware, user,
):  # pylint: disable=redefined-outer-name
    """Verify an anonymous request (or one without a user) is never previewed: its response may be cached publicly."""
    request = request_factory.get('/')
    request.COOKIES['theme-preview'] = 'yes'
    if user is not None:
        request.user = user

    middleware.process_request(request)

    assert not hasattr(request, 'site_theme')
    assert not hasattr(request, 'fx_preview_theme')


@pytest.mark.django_db
@pytest.mark.parametrize('draft_values, expected_theme, expected_options', [
    (
        {'learner_theme_allowed': True, 'learner_theme_enabled': True},
        'fx-learner', {'name': 'fx-learner', 'parent': 'indigo'},
    ),
    ({'learner_theme_allowed': True, 'learner_theme_enabled': False}, 'indigo', {'name': 'indigo'}),
    ({'learner_theme_allowed': None, 'learner_theme_enabled': True}, 'indigo', {'name': 'indigo'}),
    ({}, 'indigo', {'name': 'indigo'}),
])
def test_process_request_preview_learner_theme(
    request_factory, middleware, draft_values, expected_theme, expected_options, base_data,
):  # pylint: disable=redefined-outer-name, unused-argument, too-many-arguments
    """Verify the preview uses fx-learner only when the draft-overlaid config allows and enables it."""
    request = request_factory.get('/')
    request.COOKIES['theme-preview'] = 'yes'
    request.user = Mock(is_authenticated=True)
    request.site = Mock(domain='s1.sample.com')

    with patch(
        'futurex_openedx_extensions.dashboard.middlewares.get_tenant_config',
        return_value={'values': draft_values},
    ) as mock_get_config:
        middleware.process_request(request)

    mock_get_config.assert_called_once_with(
        tenant_id=1, keys=['learner_theme_allowed', 'learner_theme_enabled'], published_only=False,
    )
    assert request.site_theme.theme_dir_name == expected_theme
    assert request.fx_preview_theme == expected_options


@pytest.mark.django_db
@pytest.mark.parametrize('site', [None, Mock(domain=''), Mock(domain='unknown.sample.com')])
def test_process_request_preview_without_tenant(
    request_factory, middleware, site, base_data,
):  # pylint: disable=redefined-outer-name, unused-argument
    """Verify the preview keeps indigo when the request has no tenant."""
    request = request_factory.get('/')
    request.COOKIES['theme-preview'] = 'yes'
    request.user = Mock(is_authenticated=True)
    if site is not None:
        request.site = site

    with patch('futurex_openedx_extensions.dashboard.middlewares.get_tenant_config') as mock_get_config:
        middleware.process_request(request)

    mock_get_config.assert_not_called()
    assert request.site_theme.theme_dir_name == 'indigo'


@pytest.mark.django_db
def test_process_request_preview_config_error(request_factory, middleware, base_data):  # pylint: disable=W0621,W0613
    """Verify the preview keeps indigo when the tenant config cannot be read."""
    request = request_factory.get('/')
    request.COOKIES['theme-preview'] = 'yes'
    request.user = Mock(is_authenticated=True)
    request.site = Mock(domain='s1.sample.com')

    with patch(
        'futurex_openedx_extensions.dashboard.middlewares.get_tenant_config',
        side_effect=FXCodedException(code=FXExceptionCodes.TENANT_NOT_FOUND, message='gone'),
    ):
        middleware.process_request(request)

    assert request.site_theme.theme_dir_name == 'indigo'


@pytest.mark.django_db
def test_process_request_preview_real_config(request_factory, middleware, base_data):  # pylint: disable=W0621,W0613
    """Verify the preview reads the DRAFT values of the seeded keys end to end."""
    ConfigAccessControl.objects.create(
        key_name='learner_theme_allowed', path='theme_v2.learner_theme.allowed', key_type='boolean',
        writable=True, staff_only=True,
    )
    ConfigAccessControl.objects.create(
        key_name='learner_theme_enabled', path='theme_v2.learner_theme.enabled', key_type='boolean', writable=True,
    )
    for path in ('theme_v2.learner_theme.allowed', 'theme_v2.learner_theme.enabled'):
        DraftConfig.objects.create(
            tenant_id=1, config_path=path, config_value=True, created_by_id=1, updated_by_id=1,
        )
    request = request_factory.get('/')
    request.COOKIES['theme-preview'] = 'yes'
    request.user = Mock(is_authenticated=True)
    request.site = Mock(domain='s1.sample.com')

    middleware.process_request(request)

    assert request.site_theme.theme_dir_name == 'fx-learner'


@pytest.fixture
def theming_sources():
    """Isolate eox-theming's source list: a 'published' source answering from a THEME_OPTIONS dict"""
    published = {'theme': {}}

    def published_source(*args):
        value = published
        for arg in args:
            if not isinstance(value, dict) or arg not in value:
                return None
            value = value[arg]
        return value

    original = ThemingConfiguration.source_functions
    ThemingConfiguration.source_functions = [published_source]
    yield published
    ThemingConfiguration.source_functions = original


def _theme_chain():
    """Return (name, parent, grandparent) as eox-theming resolves them"""
    return tuple(
        ThemingConfiguration.options('theme', key, default=None) for key in ('name', 'parent', 'grandparent')
    )


def test_install_theme_preview_config_source(theming_sources):  # pylint: disable=redefined-outer-name, W0613
    """Verify the source is put first, once, and the middleware installs it"""
    assert middlewares.install_theme_preview_config_source() is True
    assert middlewares.install_theme_preview_config_source() is True
    assert ThemingConfiguration.source_functions[0] is middlewares.theme_preview_config_source
    assert len(ThemingConfiguration.source_functions) == 2

    ThemingConfiguration.source_functions.pop(0)
    FutureXThemePreviewMiddleware(get_response=lambda request: None)
    assert ThemingConfiguration.source_functions[0] is middlewares.theme_preview_config_source


def test_install_theme_preview_config_source_not_a_list(theming_sources):  # pylint: disable=W0621,W0613
    """Verify nothing is installed when eox-theming's sources are not a list"""
    ThemingConfiguration.source_functions = (middlewares.theme_preview_config_source,)
    assert middlewares.install_theme_preview_config_source() is False


def test_install_theme_preview_config_source_import_error():
    """Verify nothing is installed when eox-theming's configuration module is not importable"""
    with patch.dict('sys.modules', {'eox_theming.configuration': None}):
        assert middlewares.install_theme_preview_config_source() is False


@pytest.mark.parametrize('args, preview, expected', [
    (('theme', 'name'), {'name': 'fx-learner', 'parent': 'indigo'}, 'fx-learner'),
    (('theme', 'parent'), {'name': 'fx-learner', 'parent': 'indigo'}, 'indigo'),
    (('theme', 'grandparent'), {'name': 'fx-learner', 'parent': 'indigo'}, ''),
    (('theme', 'parent'), {'name': 'indigo'}, ''),
    (('theme', 'logo'), {'name': 'indigo'}, None),
    (('theme',), {'name': 'indigo'}, None),
    (('template_dir',), {'name': 'indigo'}, None),
    (('theme', 'name'), None, None),
])
def test_theme_preview_config_source(args, preview, expected):
    """Verify the source answers the theme chain of a preview request only"""
    request = Mock(spec=['fx_preview_theme'], fx_preview_theme=preview) if preview else Mock(spec=[])
    with patch('futurex_openedx_extensions.dashboard.middlewares.get_current_request', return_value=request):
        assert middlewares.theme_preview_config_source(*args) == expected


def test_theme_preview_config_source_no_request():
    """Verify the source falls through outside a request (management commands, celery)"""
    with patch('futurex_openedx_extensions.dashboard.middlewares.get_current_request', return_value=None):
        assert middlewares.theme_preview_config_source('theme', 'name') is None


@pytest.mark.parametrize('published, preview_theme, expected_chain', [
    ({'name': 'indigo'}, 'fx-learner', ('fx-learner', 'indigo', None)),
    ({'name': 'indigo', 'parent': 'bragi', 'grandparent': 'old'}, 'fx-learner', ('fx-learner', 'indigo', None)),
    ({'name': 'fx-learner', 'parent': 'indigo'}, 'indigo', ('indigo', None, None)),
    ({'name': 'fx-learner', 'parent': 'indigo'}, 'fx-learner', ('fx-learner', 'indigo', None)),
])
def test_preview_theme_chain(
    theming_sources, request_factory, middleware, published, preview_theme, expected_chain,
):  # pylint: disable=redefined-outer-name, too-many-arguments
    """
    Verify a preview request resolves the theme chain publishing would produce, whatever the published one is:
    fx-learner with parent indigo, or plain indigo whose unset parent resolves to EOX_THEMING_DEFAULT_THEME_NAME.
    A request without the preview cookie keeps the published chain.
    """
    theming_sources['theme'] = published
    request = request_factory.get('/')
    request.COOKIES['theme-preview'] = 'yes'
    request.user = Mock(is_authenticated=True)
    with patch(
        'futurex_openedx_extensions.dashboard.middlewares.get_preview_theme_name', return_value=preview_theme,
    ):
        middleware.process_request(request)

    with patch('futurex_openedx_extensions.dashboard.middlewares.get_current_request', return_value=request):
        assert tuple(value or None for value in _theme_chain()) == expected_chain

    plain_request = request_factory.get('/')
    middleware.process_request(plain_request)
    with patch('futurex_openedx_extensions.dashboard.middlewares.get_current_request', return_value=plain_request):
        assert _theme_chain() == tuple(published.get(key) for key in ('name', 'parent', 'grandparent'))
