"""functions for getting statistics about learners"""
from __future__ import annotations

from typing import Dict

from common.djangoapps.student.models import CourseAccessRole, CourseEnrollment, UserSignupSource
from django.contrib.auth import get_user_model
from django.db.models import Count, Exists, OuterRef, Q, Subquery
from django.db.models.query import QuerySet

from futurex_openedx_extensions.helpers.permissions import get_tenant_limited_fx_permission_info
from futurex_openedx_extensions.helpers.querysets import get_base_queryset_courses
from futurex_openedx_extensions.helpers.tenants import get_course_org_filter_list, get_tenant_site


def get_learners_count_having_enrollment_per_org(
    fx_permission_info: dict, tenant_id: int, visible_courses_filter: bool = True, active_courses_filter: bool = None
) -> QuerySet:
    """
    TODO: Cache the result of this function
    Get the count of learners with enrollments per organization. Admins and staff are excluded from the count. This
    function takes one tenant ID for performance reasons.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param tenant_id: Tenant ID to get the count for
    :type tenant_id: int
    :param visible_courses_filter: Value to filter courses on catalog visibility. None means no filter.
    :type visible_courses_filter: bool
    :param active_courses_filter: Value to filter courses on active status. None means no filter.
    :type active_courses_filter: bool
    :return: QuerySet of learners count per organization
    :rtype: QuerySet
    """
    queryset = get_base_queryset_courses(
        get_tenant_limited_fx_permission_info(fx_permission_info, tenant_id),
        visible_filter=visible_courses_filter,
        active_filter=active_courses_filter,
    )

    return queryset.values('org').annotate(
        learners_count=Count(
            'courseenrollment__user_id',
            filter=~Exists(
                CourseAccessRole.objects.filter(
                    user_id=OuterRef('courseenrollment__user_id'),
                    org=OuterRef('org')
                )
            ) &
            Q(courseenrollment__user__is_superuser=False) &
            Q(courseenrollment__user__is_staff=False) &
            Q(courseenrollment__user__is_active=True),
            distinct=True
        )
    )


def get_learners_count_having_enrollment_for_tenant(
    fx_permission_info: dict, tenant_id: int, visible_courses_filter: bool = True, active_courses_filter: bool = None
) -> QuerySet:
    """
    TODO: Cache the result of this function
    Get the count of learners with enrollments per organization. Admins and staff are excluded from the count

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param tenant_id: Tenant ID to get the count for
    :type tenant_id: int
    :param visible_courses_filter: Value to filter courses on catalog visibility. None means no filter.
    :type visible_courses_filter: bool
    :param active_courses_filter: Value to filter courses on active status. None means no filter.
    :type active_courses_filter: bool
    :return: QuerySet of learners count per organization
    :rtype: QuerySet
    """
    return get_user_model().objects.filter(
        is_superuser=False,
        is_staff=False,
        is_active=True,
        courseenrollment__course_id__in=get_base_queryset_courses(
            get_tenant_limited_fx_permission_info(fx_permission_info, tenant_id),
            visible_filter=visible_courses_filter,
            active_filter=active_courses_filter,
        ),
    ).exclude(
        Exists(
            CourseAccessRole.objects.filter(
                user_id=OuterRef('id'),
                org=OuterRef('courseenrollment__course__org'),
            ).values('user_id')
        )
    ).values('id').distinct().count()


def get_learners_count_having_no_enrollment(
    fx_permission_info: dict, tenant_id: int, visible_courses_filter: bool = True, active_courses_filter: bool = None
) -> QuerySet:
    """
    TODO: Cache the result of this function
    TODO: maybe there is a duplicate unnecessary query here when excluding the users with course access roles
    Get the count of learners with no enrollments per organization. Admins and staff are excluded from the count.
    Since there is no enrollment, we'll use UserSignupSource

    The function returns the count for one tenant for performance reasons.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :param tenant_id: Tenant ID to get the count for
    :type tenant_id: int
    :param visible_courses_filter: Value to filter courses on catalog visibility. None means no filter.
    :type visible_courses_filter: bool
    :param active_courses_filter: Value to filter courses on active status. None means no filter.
    :type active_courses_filter: bool
    :return: QuerySet of learners count per organization
    :rtype: QuerySet
    """
    filtered_orgs = set(get_course_org_filter_list([tenant_id])['course_org_filter_list'])
    tenant_fx_permission_info = get_tenant_limited_fx_permission_info(fx_permission_info, tenant_id)
    if filtered_orgs - set(tenant_fx_permission_info['view_allowed_full_access_orgs']) != set():
        return 0

    tenant_site = get_tenant_site(tenant_id)

    return UserSignupSource.objects.filter(
        site=tenant_site
    ).exclude(
        user_id__in=Subquery(
            CourseEnrollment.objects.filter(
                user_id=OuterRef('user_id'),
                course_id__in=get_base_queryset_courses(
                    tenant_fx_permission_info,
                    visible_filter=visible_courses_filter,
                    active_filter=active_courses_filter,
                ),
                user__is_superuser=False,
                user__is_staff=False,
                user__is_active=True,
            ).exclude(
                Exists(
                    CourseAccessRole.objects.filter(
                        user_id=OuterRef('user_id'),
                        org=OuterRef('course__org'),
                    ).values('user_id').distinct()
                ),
            ).values('user_id')
        )
    ).exclude(
        user_id__in=Subquery(
            CourseAccessRole.objects.filter(
                org__in=tenant_fx_permission_info['view_allowed_full_access_orgs'],
            ).values('user_id').distinct()
        )
    ).values('user_id').distinct().count()


def get_learners_count(fx_permission_info: dict) -> Dict[int, Dict[str, int]]:
    """
    Get the count of learners in the given list of tenants. Admins and staff are excluded from the count.

    :param fx_permission_info: Dictionary containing permission information
    :type fx_permission_info: dict
    :return: Dictionary of tenant ID and the count of learners
    :rtype: Dict[int, Dict[str, int]]
    """
    result = {
        tenant_id: {
            'learners_count': get_learners_count_having_enrollment_for_tenant(fx_permission_info, tenant_id),
            'learners_count_no_enrollment': get_learners_count_having_no_enrollment(fx_permission_info, tenant_id),
            'learners_count_per_org': {},
        }
        for tenant_id in fx_permission_info['permitted_tenant_ids']
    }
    for tenant_id in fx_permission_info['permitted_tenant_ids']:
        result[tenant_id]['learners_count_per_org'] = {
            item['org']: item['learners_count']
            for item in get_learners_count_having_enrollment_per_org(fx_permission_info, tenant_id)
        }
    return result
