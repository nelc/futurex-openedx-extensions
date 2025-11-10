"""Tests for the course categories helper model."""
from unittest.mock import patch
import pytest
from eox_tenant.models import TenantConfig
from futurex_openedx_extensions.helpers.course_categories import CourseCategories

from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.course_categories.CourseCategories.reload')
def test_course_categories_init(mock_reload, base_data):  # pylint: disable=unused-argument
    """Verify that the CourseCategories helper initializes correctly."""
    course_categories_helper = CourseCategories(tenant_id=1)

    mock_reload.assert_called_once()
    assert course_categories_helper is not None
    assert course_categories_helper.tenant == TenantConfig.objects.get(id=1)


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.course_categories.CourseCategories.reload')
def test_course_categories_init_fail(mock_reload, base_data):  # pylint: disable=unused-argument
    """Verify that the CourseCategories helper initialize tenant must exist."""
    with pytest.raises(FXCodedException) as exc_info:
        CourseCategories(tenant_id=888)

    mock_reload.assert_not_called()
    assert str(exc_info.value) == "CourseCategories initialized with an invalid tenant_id: 888"
    assert exc_info.value.code == FXExceptionCodes.TENANT_NOT_FOUND.value
