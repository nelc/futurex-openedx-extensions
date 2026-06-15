"""Tests for the dashboard toggles module."""
import pytest
from waffle.testutils import override_flag

from futurex_openedx_extensions.dashboard.toggles import is_heavy_queries_enabled, is_learner_certificates_enabled


@pytest.mark.django_db
def test_is_heavy_queries_enabled_default_true(heavy_q):  # pylint: disable=unused-argument
    """Verify is_heavy_queries_enabled returns True when the waffle flag defaults to True."""
    assert is_heavy_queries_enabled() is True


@pytest.mark.django_db
@override_flag('fx_dashboard.enable_heavy_queries', active=False)
def test_is_heavy_queries_enabled_when_flag_disabled():
    """Verify is_heavy_queries_enabled returns False when the flag is explicitly disabled."""
    assert is_heavy_queries_enabled() is False


@pytest.mark.django_db
@override_flag('fx_dashboard.enable_heavy_queries', active=True)
def test_is_heavy_queries_enabled_when_flag_enabled():
    """Verify is_heavy_queries_enabled returns True when the flag is explicitly enabled."""
    assert is_heavy_queries_enabled() is True


@pytest.mark.django_db
def test_is_learner_certificates_enabled_default_false():
    """Verify is_learner_certificates_enabled returns False by default (flag inactive)."""
    assert is_learner_certificates_enabled() is False


@pytest.mark.django_db
@override_flag('fx_dashboard.enable_learner_certificates', active=False)
def test_is_learner_certificates_enabled_when_flag_disabled():
    """Verify is_learner_certificates_enabled returns False when the flag is explicitly disabled."""
    assert is_learner_certificates_enabled() is False


@pytest.mark.django_db
@override_flag('fx_dashboard.enable_learner_certificates', active=True)
def test_is_learner_certificates_enabled_when_flag_enabled():
    """Verify is_learner_certificates_enabled returns True when the flag is explicitly enabled."""
    assert is_learner_certificates_enabled() is True
