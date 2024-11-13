"""Tests for theme helpers."""
import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from futurex_openedx_extensions.helpers import theme


@pytest.fixture
def mocked_request(db, base_data):  # pylint: disable=unused-argument
    """Mocked request"""
    factory = RequestFactory()
    request = factory.get('/some-path')
    request.site = type('Site', (), {})()
    request.site.domain = 's2.sample.com'
    return request


@pytest.mark.django_db
@pytest.mark.parametrize('user_id, expected_url, error_message', [
    (1, 'http://dashboard.example.com/en/2', 'Wrong URL returned, user has system staff access.'),
    (4, 'http://dashboard.example.com/en/2', 'Wrong URL returned, user has required role acces.'),
    (3, None, 'Expected None as returned URL, user has acces to other tenants and not to the current one.'),
    (5, None, 'Expected None as returned URL, user does not have any tenant access.'),
])
def test_get_fx_dashboard_url(
    user_id, expected_url, error_message, mocked_request
):  # pylint: disable=redefined-outer-name
    """Verify _get_fx_dashboard_url reurns correct address"""
    mocked_request.LANGUAGE_CODE = 'en'
    mocked_request.user = get_user_model().objects.get(id=user_id)
    url = theme.get_fx_dashboard_url(mocked_request)
    assert url == expected_url, error_message


@pytest.mark.django_db
@pytest.mark.parametrize('lang, expected_lang', [
    ('en', 'en'),
    ('ar', 'ar'),
    ('fr', 'ar'),
    ('', 'ar'),
    (None, 'ar'),
])
def test_get_fx_dashboard_url_for_language(
    lang, expected_lang, mocked_request
):  # pylint: disable=redefined-outer-name
    """Verify _get_fx_dashboard_url for default language code"""
    mocked_request.LANGUAGE_CODE = lang
    mocked_request.user = get_user_model().objects.get(id=4)
    url = theme.get_fx_dashboard_url(mocked_request)
    expected_url = f'http://dashboard.example.com/{expected_lang}/2'
    assert url == expected_url


def test_get_fx_dashboard_url_no_site(mocked_request):  # pylint: disable=redefined-outer-name
    """Verify _get_fx_dashboard_url returns None if site is not set"""
    mocked_request.LANGUAGE_CODE = 'en'
    mocked_request.user = get_user_model().objects.get(id=4)
    assert theme.get_fx_dashboard_url(mocked_request) is not None

    delattr(mocked_request, 'site')  # pylint: disable=literal-used-as-attribute
    assert theme.get_fx_dashboard_url(mocked_request) is None


def test_get_fx_dashboard_url_no_domain(mocked_request):  # pylint: disable=redefined-outer-name
    """Verify _get_fx_dashboard_url returns None if domain is not set"""
    mocked_request.LANGUAGE_CODE = 'en'
    mocked_request.user = get_user_model().objects.get(id=4)
    assert theme.get_fx_dashboard_url(mocked_request) is not None

    delattr(mocked_request.site, 'domain')  # pylint: disable=literal-used-as-attribute
    assert theme.get_fx_dashboard_url(mocked_request) is None


def test_get_fx_dashboard_url_no_dashboard_base(mocked_request):  # pylint: disable=redefined-outer-name
    """Verify _get_fx_dashboard_url returns None if NELC_DASHBOARD_BASE is not set"""
    mocked_request.LANGUAGE_CODE = 'en'
    mocked_request.user = get_user_model().objects.get(id=4)
    assert theme.get_fx_dashboard_url(mocked_request) is not None

    delattr(settings, 'NELC_DASHBOARD_BASE')  # pylint: disable=literal-used-as-attribute
    assert theme.get_fx_dashboard_url(mocked_request) is None
