"""Tests for theme helpers."""
import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from futurex_openedx_extensions.helpers import theme


@pytest.fixture
def mocked_request(db, base_data):  # pylint: disable=unused-argument
    """Mocked request"""
    factory = RequestFactory()
    request = factory.get('/some-path')
    request.site = type('Site', (), {})()
    request.site.name = 's2.sample.com'
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
