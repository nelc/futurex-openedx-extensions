"""Pending course invitations (CourseEnrollmentAllowed rows) collectors"""
from __future__ import annotations

from datetime import datetime
from datetime import timezone as dt_timezone
from typing import Any, Iterable

from common.djangoapps.student.models import CourseEnrollment, CourseEnrollmentAllowed
from django.contrib.auth import get_user_model
from django.db.models import Exists, OuterRef
from django.db.models.query import QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.querysets import get_course_search_queryset

INVITATION_STATUSES = ('pending', 'all')


def _invalid(message: str) -> FXCodedException:
    """Build the INVALID_INPUT error used for every bad parameter of this module"""
    return FXCodedException(code=FXExceptionCodes.INVALID_INPUT, message=message)


def parse_bool_param(name: str, value: str | None) -> bool | None:
    """Parse an optional '1'/'0' query parameter; None means the filter is not requested"""
    if value in (None, ''):
        return None
    if value not in ('0', '1'):
        raise _invalid(f'{name} must be 1 or 0')
    return value == '1'


def parse_datetime_param(name: str, value: str | None) -> datetime | None:
    """Parse an optional ISO-8601 datetime query parameter (naive values are taken as UTC)"""
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        raise _invalid(f'{name} must be an ISO-8601 datetime')
    return timezone.make_aware(parsed, dt_timezone.utc) if timezone.is_naive(parsed) else parsed


def get_pending_invitations_queryset(  # pylint: disable=too-many-arguments
    fx_permission_info: dict,
    course_id: str | None = None,
    search_text: str | None = None,
    status: str = 'pending',
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    has_account: bool | None = None,
    enrolled: bool | None = None,
) -> QuerySet:
    """
    Get the course invitations visible to the caller. Only courses reachable through the caller's tenants and
    roles are ever included, whatever the other parameters are.

    :param fx_permission_info: Dictionary containing permission information
    :param course_id: Limit to one course
    :param search_text: Email prefix; anywhere in the email when a single course is requested
    :param status: 'pending' (no linked user, the platform definition) or 'all'
    :param created_from: Invitations created at or after this time
    :param created_to: Invitations created at or before this time
    :param has_account: Keep rows whose email has (True) or has not (False) an account. Single course only.
    :param enrolled: Keep rows whose email is (True) or is not (False) actively enrolled. Single course only.
    :return: QuerySet of CourseEnrollmentAllowed, newest first, then by id
    """
    if status not in INVITATION_STATUSES:
        raise _invalid(f'status must be one of: {", ".join(INVITATION_STATUSES)}')
    if created_from and created_to and created_from > created_to:
        raise _invalid('created_from cannot be after created_to')
    if not course_id and (has_account is not None or enrolled is not None):
        raise _invalid('has_account and enrolled filters require a single course_id')

    courses = get_course_search_queryset(fx_permission_info, course_ids=[course_id] if course_id else None)
    queryset = CourseEnrollmentAllowed.objects.filter(course_id__in=courses.values('id'))

    if status == 'pending':
        queryset = queryset.filter(user__isnull=True)
    if created_from:
        queryset = queryset.filter(created__gte=created_from)
    if created_to:
        queryset = queryset.filter(created__lte=created_to)

    search_text = (search_text or '').strip()
    if search_text:
        # prefix only across courses: a leading wildcard would scan the whole table
        queryset = queryset.filter(**{'email__icontains' if course_id else 'email__istartswith': search_text})

    account = get_user_model().objects.filter(email=OuterRef('email'))
    if has_account is not None:
        queryset = queryset.filter(Exists(account) if has_account else ~Exists(account))
    if enrolled is not None:
        active = CourseEnrollment.objects.filter(
            user__email=OuterRef('email'), course_id=OuterRef('course_id'), is_active=True,
        )
        queryset = queryset.filter(Exists(active) if enrolled else ~Exists(active))

    # MySQL and SQLite both put NULLs last on a descending sort, so old rows without a date end up last
    # without an `IS NULL` sort expression (which would stop the sort from using the `created` index)
    return queryset.order_by('-created', 'id')


def get_invitation_flags(invitations: Iterable[Any]) -> dict:
    """
    Work out has_account / enrolled for the given rows only (one page), in two queries whatever the size.

    :return: {'accounts': set of lower-cased emails with an account,
              'enrolled': set of (lower-cased email, course id) with an active enrollment}
    """
    invitations = list(invitations)
    flags: dict = {'accounts': set(), 'enrolled': set()}
    if not invitations:
        return flags

    emails = {invitation.email for invitation in invitations}
    # both spellings: the production collation is case-insensitive, other databases are not
    users = dict(get_user_model().objects.filter(
        email__in=emails | {email.lower() for email in emails},
    ).values_list('id', 'email'))
    flags['accounts'] = {email.lower() for email in users.values()}

    enrollments = CourseEnrollment.objects.filter(
        user_id__in=users, course_id__in={invitation.course_id for invitation in invitations}, is_active=True,
    ).values_list('user_id', 'course_id')
    flags['enrolled'] = {(users[user_id].lower(), str(course_id)) for user_id, course_id in enrollments}
    return flags
