"""Helper functions for working with Django querysets."""
from __future__ import annotations

from typing import List

from common.djangoapps.student.models import CourseAccessRole, CourseEnrollment, UserSignupSource
from django.contrib.auth import get_user_model
from django.db.models import BooleanField, Case, Exists, OuterRef, Q, Value, When
from django.db.models.query import QuerySet
from django.utils.timezone import now
from opaque_keys.edx.django.models import CourseKeyField
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers.converters import get_allowed_roles
from futurex_openedx_extensions.helpers.exceptions import FXCodedException, FXExceptionCodes
from futurex_openedx_extensions.helpers.extractors import get_partial_access_course_ids
from futurex_openedx_extensions.helpers.tenants import get_tenants_sites
from futurex_openedx_extensions.helpers.users import get_user_by_key


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

    q_set = CourseOverview.objects.filter(org__in=fx_permission_info['view_allowed_any_access_orgs'])

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


def get_learners_search_queryset(
    search_text: str | None = None,
    superuser_filter: bool | None = False,
    staff_filter: bool | None = False,
    active_filter: bool | None = True
) -> QuerySet:
    """
    Get the learners queryset for the given search text.

    :param search_text: Search text to filter the learners by
    :type search_text: str | None
    :param superuser_filter: Value to filter superusers. None means no filter
    :type superuser_filter: bool | None
    :param staff_filter: Value to filter staff users. None means no filter
    :type staff_filter: bool | None
    :param active_filter: Value to filter active users. None means no filter
    :type active_filter: bool | None
    :return: QuerySet of learners
    :rtype: QuerySet
    """
    queryset = get_user_model().objects.all()

    if superuser_filter is not None:
        queryset = queryset.filter(is_superuser=superuser_filter)
    if staff_filter is not None:
        queryset = queryset.filter(is_staff=staff_filter)
    if active_filter is not None:
        queryset = queryset.filter(is_active=active_filter)

    search_text = (search_text or '').strip()
    if search_text:
        queryset = queryset.filter(
            Q(username__icontains=search_text) |
            Q(email__icontains=search_text) |
            Q(profile__name__icontains=search_text)
        )

    return queryset


def get_permitted_learners_queryset(
    queryset: QuerySet,
    fx_permission_info: dict,
    include_staff: bool = False,
) -> QuerySet:
    """
    Get the learners queryset after applying permissions from fx_permission_info.

    :param queryset: QuerySet of learners
    :type queryset: QuerySet
    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param include_staff: flag to include staff users
    :type include_staff: bool
    :return: QuerySet of learners
    :rtype: QuerySet
    """
    tenant_sites = get_tenants_sites(fx_permission_info['view_allowed_tenant_ids_full_access'])

    if not include_staff:
        queryset = queryset.exclude(
            check_staff_exist_queryset(
                ref_user_id='id',
                ref_org=fx_permission_info['view_allowed_any_access_orgs'],
                ref_course_id=None
            )
        )

    users_filter = Exists(
        UserSignupSource.objects.filter(user_id=OuterRef('id'), site__in=tenant_sites)
    )
    if fx_permission_info['view_allowed_tenant_ids_partial_access']:
        users_filter |= Exists(
            CourseEnrollment.objects.filter(
                user_id=OuterRef('id'),
                course_id__in=get_partial_access_course_ids(fx_permission_info),
            )
        )

    queryset = queryset.filter(users_filter)

    return queryset


def get_one_user_queryset(
    fx_permission_info: dict, user_key: get_user_model | int | str, include_staff: bool = False,
) -> QuerySet:
    """
    Get the queryset of one user by the given user key.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param user_key: User key to get the user by
    :type user_key: get_user_model | int | str
    :param include_staff: flag to include staff users
    :type include_staff: bool
    :return: QuerySet of users (filtered on one user)
    :rtype: QuerySet
    """
    user_key_info = get_user_by_key(user_key, fail_if_inactive=True)
    user: get_user_model = user_key_info['user']
    if user_key_info['error_code'] is not None:
        raise FXCodedException(user_key_info['error_code'], str(user_key_info['error_message']))

    queryset = get_permitted_learners_queryset(
        queryset=get_user_model().objects.filter(id=user.id),
        fx_permission_info=fx_permission_info,
        include_staff=include_staff,
    )

    if not queryset.exists():
        raise FXCodedException(
            code=FXExceptionCodes.USER_QUERY_NOT_PERMITTED,
            message=(
                f'Caller ({fx_permission_info["user"].username}) is not permitted to query user '
                f'({user.username}).'
            )
        )

    return queryset
