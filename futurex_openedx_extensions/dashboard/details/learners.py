"""Learners details collectors"""
from __future__ import annotations

from typing import List

from common.djangoapps.student.models import CourseAccessRole
from django.contrib.auth import get_user_model
from django.db.models import Count, Exists, OuterRef, Q, Subquery
from django.db.models.query import QuerySet

from futurex_openedx_extensions.helpers.querysets import get_base_queryset_courses, get_has_site_login_queryset
from futurex_openedx_extensions.helpers.tenants import get_course_org_filter_list, get_tenants_sites


def get_courses_count_for_learner_queryset(
    course_org_filter_list: List[str],
    visible_courses_filter: bool = True,
    active_courses_filter: bool = None,
) -> QuerySet:
    """
    Get the courses count for the given learner.

    :param course_org_filter_list: List of course organizations to filter by
    :type course_org_filter_list: List[str]
    :param visible_courses_filter: Value to filter courses on catalog visibility. None means no filter.
    :type visible_courses_filter: bool
    :param active_courses_filter: Value to filter courses on active status. None means no filter.
    :type active_courses_filter: bool
    :return: QuerySet of learners
    :rtype: QuerySet
    """
    return Count(
        'courseenrollment',
        filter=(
            Q(courseenrollment__course_id__in=get_base_queryset_courses(
                course_org_filter_list,
                visible_filter=visible_courses_filter,
                active_filter=active_courses_filter,
            )) &
            ~Exists(
                CourseAccessRole.objects.filter(
                    user_id=OuterRef('id'),
                    org=OuterRef('courseenrollment__course__org')
                )
            )
        ),
        distinct=True
    )


def get_certificates_count_for_learner_queryset(
    course_org_filter_list: List[str],
    visible_courses_filter: bool = True,
    active_courses_filter: bool = None,
) -> QuerySet:
    """
    Annotate the given queryset with the certificate counts.

    :param course_org_filter_list: List of course organizations to filter by
    :type course_org_filter_list: List[str]
    :param visible_courses_filter: Value to filter courses on catalog visibility. None means no filter.
    :type visible_courses_filter: bool
    :param active_courses_filter: Value to filter courses on active status. None means no filter.
    :type active_courses_filter: bool
    :return: QuerySet of learners
    :rtype: QuerySet
    """
    return Count(
        'generatedcertificate',
        filter=(
            Q(generatedcertificate__course_id__in=Subquery(
                get_base_queryset_courses(
                    course_org_filter_list,
                    visible_filter=visible_courses_filter,
                    active_filter=active_courses_filter
                ).values_list('id', flat=True)
            )) &
            Q(generatedcertificate__status='downloadable')
        ),
        distinct=True
    )


def get_learners_queryset(
    tenant_ids: List, search_text: str = None, visible_courses_filter: bool = True, active_courses_filter: bool = None
) -> QuerySet:
    """
    Get the learners queryset for the given tenant IDs and search text.

    :param tenant_ids: List of tenant IDs to get the learners for
    :type tenant_ids: List
    :param search_text: Search text to filter the learners by
    :type search_text: str
    :param visible_courses_filter: Value to filter courses on catalog visibility. None means no filter
    :type visible_courses_filter: bool
    :param active_courses_filter: Value to filter courses on active status. None means no filter
    :type active_courses_filter: bool
    :return: QuerySet of learners
    :rtype: QuerySet
    """
    course_org_filter_list = get_course_org_filter_list(tenant_ids)['course_org_filter_list']
    tenant_sites = get_tenants_sites(tenant_ids)

    queryset = get_user_model().objects.filter(
        is_superuser=False,
        is_staff=False,
        is_active=True,
    )
    search_text = (search_text or '').strip()
    if search_text:
        queryset = queryset.filter(
            Q(username__icontains=search_text) |
            Q(email__icontains=search_text) |
            Q(profile__name__icontains=search_text)
        )

    queryset = queryset.annotate(
        courses_count=get_courses_count_for_learner_queryset(
            course_org_filter_list,
            visible_courses_filter=visible_courses_filter,
            active_courses_filter=active_courses_filter,
        )
    ).annotate(
        certificates_count=get_certificates_count_for_learner_queryset(
            course_org_filter_list,
            visible_courses_filter=visible_courses_filter,
            active_courses_filter=active_courses_filter,
        )
    ).annotate(
        has_site_login=get_has_site_login_queryset(tenant_sites)
    ).filter(
        Q(courses_count__gt=0) | Q(has_site_login=True)
    ).select_related('profile').order_by('id')

    return queryset


def get_learner_info_queryset(
    tenant_ids: List, user_id: int, visible_courses_filter: bool = True, active_courses_filter: bool = None
) -> QuerySet:
    """
    Get the learner queryset for the given user ID. This method assumes a valid user ID.

    :param tenant_ids: List of tenant IDs to get the learner for
    :type tenant_ids: List
    :param user_id: The user ID to get the learner for
    :type user_id: int
    :param visible_courses_filter: Value to filter courses on catalog visibility. None means no filter
    :type visible_courses_filter: bool
    :param active_courses_filter: Value to filter courses on active status. None means no filter
    :type active_courses_filter: bool
    :return: QuerySet of learners
    :rtype: QuerySet
    """
    course_org_filter_list = get_course_org_filter_list(tenant_ids)['course_org_filter_list']

    queryset = get_user_model().objects.filter(id=user_id).annotate(
        courses_count=get_courses_count_for_learner_queryset(
            course_org_filter_list,
            visible_courses_filter=visible_courses_filter,
            active_courses_filter=active_courses_filter,
        )
    ).annotate(
        certificates_count=get_certificates_count_for_learner_queryset(
            course_org_filter_list,
            visible_courses_filter=visible_courses_filter,
            active_courses_filter=active_courses_filter,
        )
    ).select_related('profile')

    return queryset
