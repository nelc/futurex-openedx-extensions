"""Tests for the course price helpers"""
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from common.djangoapps.course_modes.models import CourseMode
from django.utils.timezone import now
from eox_tenant.models import TenantConfig
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from zeitlabs_payments.models import CatalogueItem

from futurex_openedx_extensions.helpers import course_price
from futurex_openedx_extensions.helpers.exceptions import FXCodedException
from tests.test_helpers.test_payments import _configured

COURSE_ID = 'course-v1:ORG4+1+1'  # org of tenant 3 only


def _activate_tenant(tenant_id=3):
    """Switch payments on for a tenant"""
    tenant = TenantConfig.objects.get(id=tenant_id)
    tenant.lms_configs.update(_configured())
    tenant.save()


def _checks(info):
    """Return the checks as a dict"""
    return {check['name']: check['passed'] for check in info['checks']}


@pytest.mark.django_db
@pytest.mark.parametrize('course_id, found', [
    (COURSE_ID, True),
    ('course-v1:ORG4+99+99', False),
    ('invalid-course-id', False),
])
def test_get_course_overview(base_data, course_id, found):  # pylint: disable=unused-argument
    """Verify the course lookup"""
    assert (course_price.get_course_overview(course_id) is not None) is found


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.course_price.get_tenants_by_org', return_value=[1, 4])
def test_get_course_payment_tenants(_, base_data):  # pylint: disable=unused-argument
    """Verify the tenants of the course org and the active ones"""
    _activate_tenant(1)
    course = CourseOverview.objects.get(id='course-v1:ORG1+3+3')
    assert course_price.get_course_payment_tenants(course) == {'tenant_ids': [1, 4], 'active_tenant_ids': [1]}


@pytest.mark.django_db
def test_get_course_price_info_nothing_set(base_data):  # pylint: disable=unused-argument
    """Verify the report of a free course on a tenant without payments"""
    info = course_price.get_course_price_info(CourseOverview.objects.get(id=COURSE_ID))
    assert info['ready'] is False
    assert info['mode'] is None
    assert info['sku'] is None
    assert info['price'] is None
    checks = _checks(info)
    assert checks['tenant_payments_active'] is False
    assert checks['paid_mode_exists'] is False
    assert checks['enrollment_open'] is True
    assert checks['single_paid_mode'] is True


@pytest.mark.django_db
@patch('futurex_openedx_extensions.helpers.course_price.log')
def test_set_course_price_creates_both_records(mock_log, base_data):  # pylint: disable=unused-argument
    """Verify that setting a price creates the paid mode and the catalogue item, ready to pay"""
    _activate_tenant()
    course = CourseOverview.objects.get(id=COURSE_ID)
    info = course_price.set_course_price(course, 500, None, Mock(id=2))

    mode = CourseMode.objects.get(course_id=course.id, mode_slug=course_price.PAID_MODE_SLUG)
    item = CatalogueItem.objects.get(sku=mode.sku)
    assert mode.sku.startswith('fx-')
    assert mode.min_price == 500
    assert mode.currency == 'sar'
    assert (item.type, item.item_ref_id, item.price, item.currency) == ('paid_course', COURSE_ID, 500, 'SAR')
    assert item.title == 'Course 1 of ORG4'
    assert info['ready'] is True, info['checks']
    assert info['price'] == 500.0
    assert mock_log.info.call_args[0][1:] == (2, COURSE_ID, mode.sku, None, 500)


@pytest.mark.django_db
def test_set_course_price_updates_and_keeps_title(base_data):  # pylint: disable=unused-argument
    """Verify that a second call keeps the sku and the item title"""
    _activate_tenant()
    course = CourseOverview.objects.get(id=COURSE_ID)
    course_price.set_course_price(course, 100, 'Pay101', None)
    CatalogueItem.objects.filter(sku='Pay101').update(title='Old title', currency='USD')
    info = course_price.set_course_price(course, 200, None, None)
    assert info['sku'] == 'Pay101'
    assert CatalogueItem.objects.get(sku='Pay101').title == 'Old title'
    assert info['price'] == 200.0
    assert info['ready'] is True


@pytest.mark.django_db
@pytest.mark.parametrize('price', ['abc', 0, -5, 10.5, 1000001, True, None])
def test_set_course_price_invalid_price(base_data, price):  # pylint: disable=unused-argument
    """Verify that an invalid price is refused"""
    _activate_tenant()
    with pytest.raises(FXCodedException):
        course_price.set_course_price(CourseOverview.objects.get(id=COURSE_ID), price, None, None)


@pytest.mark.django_db
@pytest.mark.parametrize('sku', ['has space', 'x' * 51, 5, ''])
def test_set_course_price_invalid_sku(base_data, sku):  # pylint: disable=unused-argument
    """Verify that an invalid sku is refused"""
    _activate_tenant()
    with pytest.raises(FXCodedException):
        course_price.set_course_price(CourseOverview.objects.get(id=COURSE_ID), 100, sku, None)


@pytest.mark.django_db
def test_set_course_price_inactive_tenant(base_data):  # pylint: disable=unused-argument
    """Verify that pricing a course of a tenant without active payments is refused"""
    with pytest.raises(FXCodedException) as exc_info:
        course_price.set_course_price(CourseOverview.objects.get(id=COURSE_ID), 100, None, None)
    assert 'Payments are not active' in str(exc_info.value)


@pytest.mark.django_db
def test_set_course_price_sku_change_refused(base_data):  # pylint: disable=unused-argument
    """Verify that the sku of an existing paid mode cannot be changed"""
    _activate_tenant()
    course = CourseOverview.objects.get(id=COURSE_ID)
    course_price.set_course_price(course, 100, 'Pay101', None)
    with pytest.raises(course_price.CoursePriceConflict):
        course_price.set_course_price(course, 100, 'Pay102', None)


@pytest.mark.django_db
@pytest.mark.parametrize('owner', ['mode', 'item'])
def test_set_course_price_sku_of_another_course(base_data, owner):  # pylint: disable=unused-argument
    """Verify that a sku used by another course is refused"""
    _activate_tenant()
    if owner == 'mode':
        CourseMode.objects.create(
            course_id='course-v1:ORG3+1+1', mode_slug='verified', mode_display_name='V', sku='Taken1',
        )
    else:
        CatalogueItem.objects.create(sku='Taken1', type='paid_course', title='t', item_ref_id='course-v1:ORG3+1+1')
    with pytest.raises(course_price.CoursePriceConflict):
        course_price.set_course_price(CourseOverview.objects.get(id=COURSE_ID), 100, 'Taken1', None)


@pytest.mark.django_db
def test_get_course_price_info_mismatches(base_data):  # pylint: disable=unused-argument
    """Verify that each mismatch fails its own check"""
    _activate_tenant()
    course = CourseOverview.objects.get(id=COURSE_ID)
    course.end = now() - timedelta(days=1)
    course.save()
    CourseMode.objects.create(
        course_id=course.id, mode_slug=course_price.PAID_MODE_SLUG, mode_display_name='P',
        min_price=100, currency='usd', sku='Mis1',
    )
    CourseMode.objects.create(course_id=course.id, mode_slug='verified', mode_display_name='V', min_price=50)
    CatalogueItem.objects.create(
        sku='Mis1', type='bulk_course', title='t', item_ref_id='course-v1:ORG4+2+2', price=90, currency='SAR',
    )
    checks = _checks(course_price.get_course_price_info(course))
    assert checks == {
        'tenant_payments_active': True,
        'paid_mode_exists': True,
        'catalogue_item_exists': True,
        'catalogue_item_is_paid_course': False,
        'catalogue_item_course_matches': False,
        'price_matches': False,
        'currency_matches': False,
        'enrollment_open': False,
        'single_paid_mode': False,
    }


@pytest.mark.django_db
def test_get_course_price_info_orphan_mode(base_data):  # pylint: disable=unused-argument
    """Verify the report when the paid mode's sku has no catalogue item"""
    _activate_tenant()
    course = CourseOverview.objects.get(id=COURSE_ID)
    course.enrollment_end = now() - timedelta(days=1)
    course.save()
    CourseMode.objects.create(
        course_id=course.id, mode_slug=course_price.PAID_MODE_SLUG, mode_display_name='P', min_price=100, sku='Orph',
    )
    info = course_price.get_course_price_info(course)
    checks = _checks(info)
    assert checks['catalogue_item_exists'] is False
    assert checks['price_matches'] is False
    assert checks['enrollment_open'] is False
    assert info['currency'] is None
