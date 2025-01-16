"""functions for getting statistics about certificates"""
from __future__ import annotations

import logging
from typing import Dict

from django.conf import settings
from django.db.models import BooleanField, Count, OuterRef, Q, Subquery, Value
from django.db.models.functions import Lower
from lms.djangoapps.certificates.models import GeneratedCertificate
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.querysets import check_staff_exist_queryset, get_base_queryset_courses

log = logging.getLogger(__name__)


def get_certificates_count(
    fx_permission_info: dict,
    visible_courses_filter: bool | None = True,
    active_courses_filter: bool | None = None,
    include_staff: bool | None = None
) -> Dict[str, int]:
    """
    Get the count of issued certificates in the given tenants. The count is grouped by organization. Certificates
    for admins, staff, and superusers are also included.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param visible_courses_filter: Value to filter courses on catalog visibility. None means no filter.
    :type visible_courses_filter: bool | None
    :param active_courses_filter: Value to filter courses on active status. None means no filter.
    :type active_courses_filter: bool | None
    :return: Count of certificates per organization
    :rtype: Dict[str, int]
    """
    if include_staff:
        is_staff_queryset = Q(Value(False, output_field=BooleanField()))
    else:
        is_staff_queryset = check_staff_exist_queryset(
            ref_user_id='user_id', ref_org='course_org', ref_course_id='course_id',
        )

    result = list(
        GeneratedCertificate.objects.filter(
            status='downloadable',
            course_id__in=get_base_queryset_courses(
                fx_permission_info,
                visible_filter=visible_courses_filter,
                active_filter=active_courses_filter,
            ),
        )
        .annotate(
            course_org=Subquery(
                CourseOverview.objects.filter(
                    id=OuterRef('course_id')
                ).values(org_lower_case=Lower('org'))
            )
        )
        .filter(~is_staff_queryset)
        .values('course_org').annotate(certificates_count=Count('id')).values_list('course_org', 'certificates_count')
    )

    return dict(result)


def get_learning_hours_count(
    fx_permission_info: dict,
    visible_courses_filter: bool | None = True,
    active_courses_filter: bool | None = None,
    include_staff: bool | None = None,
) -> int:
    """
    Get the count of learning hours in the given tenants. The count is grouped by course_effort. Certificates
    for admins, staff, and superusers are also included.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param visible_courses_filter: Value to filter courses on catalog visibility. None means no filter.
    :type visible_courses_filter: bool | None
    :param active_courses_filter: Value to filter courses on active status. None means no filter.
    :type active_courses_filter: bool | None
    :param include_staff: Include staff members in the count
    :type include_staff: bool | None
    :return: Count of certificates per organization
    :rtype: Dict[str, int]
    """

    def parse_course_effort(effort: str, course_id: str) -> float:
        """Parses course effort in HH:MM format and returns total hours as a float."""
        try:
            if not effort:
                raise FXCodedException(
                    FXExceptionCodes.COURSE_EFFORT_NOT_FOUND,
                    f'Course effort not found for course {course_id}'
                )

            parts = effort.split(':')
            hours = int(parts[0])
            minutes = int(parts[1]) if len(parts) > 1 else 0

            if hours < 0 or minutes < 0:
                raise ValueError('Hours and minutes must be non-negative values.')
            if minutes >= 60:
                raise ValueError('Minutes cannot be 60 or more.')

            total_hours = hours + minutes / 60

            if total_hours < 0.5:
                raise ValueError('course effort value is too small')

            return round(total_hours, 1)

        except FXCodedException:
            return settings.FX_DEFAULT_COURSE_EFFORT

        except (ValueError, IndexError) as exc:
            log.exception(
                'Invalid course-effort for course %s. Assuming default value (%s hours). Error: %s',
                course_id, settings.FX_DEFAULT_COURSE_EFFORT, str(exc)
            )
            return settings.FX_DEFAULT_COURSE_EFFORT

    queryset = GeneratedCertificate.objects.filter(
        status='downloadable',
        course_id__in=get_base_queryset_courses(
            fx_permission_info,
            visible_filter=visible_courses_filter,
            active_filter=active_courses_filter,
        ),
    )

    if not include_staff:
        queryset = queryset.annotate(
            course_org=Subquery(
                CourseOverview.objects.filter(id=OuterRef('course_id')).values('org')
            )
        ).filter(
            ~check_staff_exist_queryset(
                ref_user_id='user_id', ref_org='course_org', ref_course_id='course_id',
            )
        )

    result = list(
        queryset.annotate(
            course_effort=Subquery(
                CourseOverview.objects.filter(
                    id=OuterRef('course_id')
                ).values('effort')
            )
        ).annotate(
            certificates_count=Count('id')
        ).values('course_effort', 'certificates_count', 'course_id')
    )

    return sum(
        parse_course_effort(
            entry.get('course_effort', settings.FX_DEFAULT_COURSE_EFFORT),
            entry.get('course_id')
        ) * entry.get('certificates_count', 0)
        for entry in result
    )
