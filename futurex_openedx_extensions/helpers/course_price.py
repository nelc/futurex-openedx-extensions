"""Helpers for pricing a course for the Zeitlabs payments checkout"""
from __future__ import annotations

import logging
import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List

from common.djangoapps.course_modes.models import CourseMode
from django.db import transaction
from django.utils.timezone import now
from eox_tenant.models import TenantConfig
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from zeitlabs_payments.models import CatalogueItem

from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.payments import PAYMENTS_CURRENCY, get_tenant_payment_status
from futurex_openedx_extensions.helpers.tenants import get_tenants_by_org

log = logging.getLogger(__name__)

PAID_MODE_SLUG = 'no-id-professional'
PAID_MODE_DISPLAY_NAME = 'Professional'
PAID_COURSE_ITEM_TYPE = 'paid_course'
SKU_PATTERN = re.compile(r'^[A-Za-z0-9._-]{1,50}$')
MAX_PRICE = 1000000


class CoursePriceConflict(Exception):
    """The requested sku cannot be used for this course."""


def get_course_overview(course_id: str) -> CourseOverview | None:
    """
    Return the course overview, or None when the id is invalid or the course does not exist.

    :param course_id: The course ID
    :type course_id: str
    :return: The course overview
    :rtype: CourseOverview | None
    """
    try:
        return CourseOverview.objects.filter(id=CourseKey.from_string(course_id)).first()
    except InvalidKeyError:
        return None


def get_course_payment_tenants(course: CourseOverview) -> Dict[str, List[int]]:
    """
    Return the tenants of the course's org, and those of them where payments are active.

    :param course: The course
    :type course: CourseOverview
    :return: tenant_ids and active_tenant_ids
    :rtype: Dict[str, List[int]]
    """
    tenant_ids = get_tenants_by_org(course.org)
    configs = dict(TenantConfig.objects.filter(id__in=tenant_ids).values_list('id', 'lms_configs'))
    return {
        'tenant_ids': tenant_ids,
        'active_tenant_ids': [
            tenant_id for tenant_id in tenant_ids
            if get_tenant_payment_status(configs.get(tenant_id) or {})['active']
        ],
    }


def get_course_price_info(course: CourseOverview) -> Dict[str, Any]:
    """
    Return the course's price and a readiness report saying whether a learner can pay for it.

    :param course: The course
    :type course: CourseOverview
    :return: Price info with `ready` and the list of checks
    :rtype: Dict[str, Any]
    """
    tenants = get_course_payment_tenants(course)
    modes = CourseMode.objects.filter(course_id=course.id)
    paid_mode = modes.filter(mode_slug=PAID_MODE_SLUG).first()
    item = CatalogueItem.objects.filter(sku=paid_mode.sku).first() if paid_mode and paid_mode.sku else None
    current_time = now()

    checks = {
        'tenant_payments_active': bool(tenants['active_tenant_ids']),
        'paid_mode_exists': bool(paid_mode and paid_mode.sku),
        'catalogue_item_exists': item is not None,
        'catalogue_item_is_paid_course': bool(item and item.type == PAID_COURSE_ITEM_TYPE),
        'catalogue_item_course_matches': bool(item and item.item_ref_id == str(course.id)),
        'price_matches': bool(item and item.price is not None and item.price == paid_mode.min_price),
        'currency_matches': bool(item and (item.currency or '').upper() == (paid_mode.currency or '').upper()),
        'enrollment_open': (
            (course.end is None or course.end > current_time) and
            (course.enrollment_end is None or course.enrollment_end > current_time)
        ),
        'single_paid_mode': not modes.exclude(mode_slug=PAID_MODE_SLUG).filter(min_price__gt=0).exists(),
    }
    return {
        'course_id': str(course.id),
        'tenant_ids': tenants['tenant_ids'],
        'active_tenant_ids': tenants['active_tenant_ids'],
        'mode': PAID_MODE_SLUG if paid_mode else None,
        'sku': paid_mode.sku if paid_mode else None,
        'price': float(item.price) if item and item.price is not None else None,
        'currency': item.currency if item else None,
        'ready': all(checks.values()),
        'checks': [{'name': name, 'passed': passed} for name, passed in checks.items()],
    }


def _validate_price(price: Any) -> int:
    """Return the price as a whole number of SAR, or raise for an invalid price"""
    try:
        value = Decimal(str(price))
    except (InvalidOperation, ValueError) as exc:
        raise FXCodedException(code=FXExceptionCodes.INVALID_INPUT, message='price must be a number.') from exc
    if isinstance(price, bool) or value != value.to_integral_value() or not 0 < value <= MAX_PRICE:
        raise FXCodedException(
            code=FXExceptionCodes.INVALID_INPUT,
            message=f'price must be a whole number of {PAYMENTS_CURRENCY} between 1 and {MAX_PRICE}.',
        )
    return int(value)


def set_course_price(course: CourseOverview, price: Any, sku: Any, user: Any) -> Dict[str, Any]:
    """
    Create or update the paid course mode and its catalogue item together, with one sku and one price.

    :param course: The course
    :type course: CourseOverview
    :param price: The price in SAR
    :type price: Any
    :param sku: The sku to use for a new paid mode (optional)
    :type sku: Any
    :param user: The user making the change (for the audit log)
    :type user: Any
    :return: The course's price info after the change
    :rtype: Dict[str, Any]
    """
    price = _validate_price(price)
    if sku is not None and (not isinstance(sku, str) or not SKU_PATTERN.match(sku)):
        raise FXCodedException(
            code=FXExceptionCodes.INVALID_INPUT,
            message='sku must be 1 to 50 characters of letters, digits, dot, underscore, or hyphen.',
        )
    if not get_course_payment_tenants(course)['active_tenant_ids']:
        raise FXCodedException(
            code=FXExceptionCodes.INVALID_INPUT,
            message=f'Payments are not active on any tenant of the course org ({course.org}).',
        )

    course_id = str(course.id)
    with transaction.atomic():
        paid_mode = CourseMode.objects.select_for_update().filter(
            course_id=course.id, mode_slug=PAID_MODE_SLUG,
        ).first()
        if paid_mode and paid_mode.sku and sku and sku != paid_mode.sku:
            raise CoursePriceConflict(f'The course already has the sku ({paid_mode.sku}); it cannot be changed.')
        sku = (paid_mode.sku if paid_mode and paid_mode.sku else None) or sku or f'fx-{uuid.uuid4().hex[:12]}'
        if (
            CourseMode.objects.filter(sku=sku).exclude(course_id=course.id).exists() or
            CatalogueItem.objects.filter(sku=sku).exclude(item_ref_id=course_id).exists()
        ):
            raise CoursePriceConflict(f'The sku ({sku}) already belongs to another course.')

        old_price = paid_mode.min_price if paid_mode else None
        if paid_mode is None:
            paid_mode = CourseMode(
                course_id=course.id, mode_slug=PAID_MODE_SLUG, mode_display_name=PAID_MODE_DISPLAY_NAME,
            )
        paid_mode.min_price = price
        paid_mode.currency = PAYMENTS_CURRENCY.lower()
        paid_mode.sku = sku
        paid_mode.save()

        item, created = CatalogueItem.objects.get_or_create(
            sku=sku,
            defaults={
                'type': PAID_COURSE_ITEM_TYPE,
                'item_ref_id': course_id,
                'title': course.display_name or course_id,
                'price': price,
                'currency': PAYMENTS_CURRENCY,
            },
        )
        if not created:
            item.type = PAID_COURSE_ITEM_TYPE
            item.item_ref_id = course_id
            item.price = price
            item.currency = PAYMENTS_CURRENCY
            item.save()

    log.info(
        'fx.payments.course_price_changed user=%s course=%s sku=%s price=%s->%s',
        getattr(user, 'id', None), course_id, sku, old_price, price,
    )
    return get_course_price_info(course)
