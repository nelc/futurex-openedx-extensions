"""functions for getting statistics about learners"""
from __future__ import annotations

from typing import Dict, List

from common.djangoapps.student.models import CourseAccessRole, CourseEnrollment, UserSignupSource
from django.contrib.auth import get_user_model
from django.db.models import Count, Exists, OuterRef, Q, Subquery
from django.db.models.query import QuerySet
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers.tenants import get_course_org_filter_list, get_tenant_site


def get_learners_count_having_enrollment_per_org(tenant_id) -> QuerySet:
    """
    TODO: Cache the result of this function
    Get the count of learners with enrollments per organization. Admins and staff are excluded from the count. This
    function takes one tenant ID for performance reasons.


    SELECT coc.org, COUNT(DISTINCT au.id)
    FROM edxapp.auth_user au
    INNER JOIN edxapp.student_courseenrollment sc ON
        au.id = sc.user_id
    INNER JOIN edxapp.course_overviews_courseoverview coc ON
        sc.course_id = coc.id AND
        coc.org IN ('ORG1', 'ORG2')  -- course_org_filter_list
    WHERE au.id NOT IN (
            SELECT DISTINCT cr.user_id
            FROM edxapp.student_courseaccessrole cr
            WHERE cr.org = coc.org
        ) AND
        au.is_superuser = 0 AND
        au.is_staff = 0 AND
        au.is_active = 1
    GROUP BY coc.org


    :return: QuerySet of learners count per organization
    :rtype: QuerySet
    """
    course_org_filter_list = get_course_org_filter_list([tenant_id])['course_org_filter_list']

    return CourseOverview.objects.filter(
        org__in=course_org_filter_list
    ).values('org').annotate(
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


def get_learners_count_having_enrollment_for_tenant(tenant_id) -> QuerySet:
    """
    TODO: Cache the result of this function
    Get the count of learners with enrollments per organization. Admins and staff are excluded from the count


    SELECT COUNT(DISTINCT au.id)
    FROM edxapp.auth_user au
    INNER JOIN edxapp.student_courseenrollment sc ON
        au.id = sc.user_id
    INNER JOIN edxapp.course_overviews_courseoverview coc ON
        sc.course_id = coc.id AND
        coc.org IN ('ORG1', 'ORG2')  -- course_org_filter_list
    WHERE au.id NOT IN (
            SELECT DISTINCT cr.user_id
            FROM edxapp.student_courseaccessrole cr
            WHERE cr.org = coc.org
        ) AND
        au.is_superuser = 0 AND
        au.is_staff = 0 AND
        au.is_active = 1


    :return: QuerySet of learners count per organization
    :rtype: QuerySet
    """
    course_org_filter_list = get_course_org_filter_list([tenant_id])['course_org_filter_list']

    return get_user_model().objects.filter(
        is_superuser=False,
        is_staff=False,
        is_active=True,
        courseenrollment__course__org__in=course_org_filter_list,
    ).exclude(
        Exists(
            CourseAccessRole.objects.filter(
                user_id=OuterRef('id'),
                org=OuterRef('courseenrollment__course__org'),
            ).values('user_id')
        )
    ).values('id').distinct().count()


def get_learners_count_having_no_enrollment(tenant_id) -> QuerySet:
    """
    TODO: Cache the result of this function
    Get the count of learners with no enrollments per organization. Admins and staff are excluded from the count.
    Since there is no enrollment, we'll use UserSignupSource

    The function returns the count for one tenant for performance reasons.

    SELECT COUNT(distinct su.id)
    FROM edxapp.student_usersignupsource su
    WHERE su.site = 'demo.example.com' -- tenant_site
        AND su.user_id not in (
            SELECT distinct au.id
            FROM edxapp.auth_user au
            INNER JOIN edxapp.student_courseenrollment sc ON
                au.id = sc.user_id
            INNER JOIN edxapp.course_overviews_courseoverview coc ON
                sc.course_id = coc.id AND
                coc.org IN ('ORG1', 'ORG2') -- course_org_filter_list
            WHERE au.id NOT IN (
                    SELECT DISTINCT cr.user_id
                    FROM edxapp.student_courseaccessrole cr
                    WHERE cr.org = coc.org
                ) AND
                au.is_superuser = 0 AND
                au.is_staff = 0 AND
                au.is_active = 1 AND
        ) AND su.user_id NOT IN (
            SELECT DISTINCT cr.user_id
            FROM edxapp.student_courseaccessrole cr
            WHERE cr.org IN ('ORG1', 'ORG2') -- course_org_filter_list
        )

    """
    course_org_filter_list = get_course_org_filter_list([tenant_id])['course_org_filter_list']
    tenant_site = get_tenant_site(tenant_id)

    return UserSignupSource.objects.filter(
        site=tenant_site
    ).exclude(
        user_id__in=Subquery(
            CourseEnrollment.objects.filter(
                user_id=OuterRef('user_id'),
                course__org__in=course_org_filter_list,
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
                org__in=course_org_filter_list,
            ).values('user_id').distinct()
        )
    ).values('user_id').distinct().count()


def get_learners_count(tenant_ids: List[int]) -> Dict[int, Dict[str, int]]:
    """
    Get the count of learners in the given list of tenants. Admins and staff are excluded from the count.

    :param tenant_ids: List of tenant IDs to get the count for
    :type tenant_ids: List[int]
    :return: Dictionary of tenant ID and the count of learners
    :rtype: Dict[int, Dict[str, int]]
    """
    result = {
        tenant_id: {
            'learners_count': get_learners_count_having_enrollment_for_tenant(tenant_id),
            'learners_count_no_enrollment': get_learners_count_having_no_enrollment(tenant_id),
            'learners_count_per_org': {},
        }
        for tenant_id in tenant_ids
    }
    for tenant_id in tenant_ids:
        result[tenant_id]['learners_count_per_org'] = {
            item['org']: item['learners_count']
            for item in get_learners_count_having_enrollment_per_org(tenant_id)
        }
    return result
