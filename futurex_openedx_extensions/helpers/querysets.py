"""Helper functions for working with Django querysets."""
from __future__ import annotations

from typing import List

from common.djangoapps.student.models import CourseAccessRole, UserSignupSource
from django.db.models import BooleanField, Case, Exists, OuterRef, Q, Value, When
from django.db.models.query import QuerySet
from django.utils.timezone import now
from opaque_keys.edx.django.models import CourseKeyField
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers.converters import get_allowed_roles


def check_staff_exist_queryset(
    ref_user_id: str | Value,
    ref_org: str | Value | List | None,
    ref_course_id: str | Value | None,
    roles_filter: List[str] | None = None,
) -> Exists:
    """
    Get the queryset of users who are staff.

    :param ref_user_id: Reference to the user ID
    :type ref_user_id: str | Value
    :param ref_org: Reference to the organization
    :type ref_org: str | Value | List | None
    :param ref_course_id: Reference to the course ID
    :type ref_course_id: str | Value | None
    :param roles_filter: List of allowed roles
    :type roles_filter: List[str] | None
    :return: QuerySet of users
    :rtype: Exists
    """
    if isinstance(ref_user_id, str):
        ref_user_id = OuterRef(ref_user_id)
    elif not isinstance(ref_user_id, Value):
        raise ValueError(f'Invalid ref_user_id type ({type(ref_user_id).__name__})')

    if isinstance(ref_org, str):
        org_query = Q(org=OuterRef(ref_org))
    elif isinstance(ref_org, list):
        org_query = Q(org__in=ref_org)
    else:
        raise ValueError(f'Invalid ref_org type ({type(ref_org).__name__})')

    if isinstance(ref_course_id, str):
        course_query = Q(course_id=OuterRef(ref_course_id))
        course_empty_query = Q(course_id=CourseKeyField.Empty)
    elif isinstance(ref_course_id, Value):
        course_query = Q(course_id=ref_course_id)
        course_empty_query = Q(course_id=CourseKeyField.Empty)
    elif ref_course_id is None:
        course_query = Q(Value(True, output_field=BooleanField()))
        course_empty_query = course_query
    else:
        raise ValueError(f'Invalid ref_course_id type ({type(ref_course_id).__name__})')

    allowed_roles = get_allowed_roles(roles_filter)

    return Exists(
        CourseAccessRole.objects.filter(
            user_id=ref_user_id,
        ).filter(
            Q(role__in=allowed_roles['global']) |
            (
                Q(role__in=allowed_roles['tenant_only']) &
                org_query
            ) |
            (
                Q(role__in=allowed_roles['course_only']) &
                org_query & course_query
            ) |
            (
                Q(role__in=allowed_roles['tenant_or_course']) &
                org_query &
                (course_query | course_empty_query)
            ),
        ),
    )


def get_base_queryset_courses(
    fx_permission_info: dict,
    visible_filter: bool | None = True,
    active_filter: bool | None = None,
) -> QuerySet:
    """
    Get the default course queryset for the given filters.

    include_staff flag is not needed, because we're dealing with courses here, not users.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param visible_filter: Value to filter courses on catalog visibility. None means no filter.
    :type visible_filter: bool | None
    :param active_filter: Value to filter courses on active status. None means no filter.
    :type active_filter: bool | None
    :return: QuerySet of courses
    :rtype: QuerySet
    """
    now_time = now()
    course_is_active_queryset = (
        (Q(start__isnull=True) | Q(start__lte=now_time)) &
        (Q(end__isnull=True) | Q(end__gte=now_time))
    )

    course_is_visible_queryset = Q(catalog_visibility__in=['about', 'both']) & Q(visible_to_staff_only=False)

    orgs = fx_permission_info['view_allowed_full_access_orgs'] + fx_permission_info['view_allowed_course_access_orgs']
    q_set = CourseOverview.objects.filter(org__in=orgs)

    if not fx_permission_info['is_system_staff_user']:
        q_set = q_set.filter(check_staff_exist_queryset(
            ref_user_id=Value(fx_permission_info['user'].id),
            ref_org='org',
            ref_course_id='id',
            roles_filter=fx_permission_info['view_allowed_roles'],
        ))

    q_set = q_set.annotate(
        course_is_active=Case(
            When(course_is_active_queryset, then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        ),
    ).annotate(
        course_is_visible=Case(
            When(course_is_visible_queryset, then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        ),
    )

    if active_filter is not None:
        q_set = q_set.filter(course_is_active=active_filter)

    if visible_filter is not None:
        q_set = q_set.filter(course_is_visible=visible_filter)

    return q_set


def get_has_site_login_queryset(tenant_sites: List[str]) -> Exists:
    """
    Get the queryset of users who have logged in to any of the given tenant sites.

    :param tenant_sites: List of tenant sites to check for
    :type tenant_sites: List[str]
    :return: QuerySet of users
    :rtype: Exists
    """
    return Exists(
        UserSignupSource.objects.filter(
            user_id=OuterRef('id'),
            site__in=tenant_sites
        )
    )
