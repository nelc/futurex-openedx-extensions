"""Courses details collectors"""
from __future__ import annotations

from typing import List

from common.djangoapps.student.models import CourseAccessRole
from django.db.models import Count, Exists, IntegerField, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.db.models.query import QuerySet
from eox_nelp.course_experience.models import FeedbackCourse
from lms.djangoapps.certificates.models import GeneratedCertificate
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers.tenants import get_course_org_filter_list, get_tenant_site


def get_courses_queryset(tenant_ids: List, search_text: str = None) -> QuerySet:
    """
    Get the courses queryset for the given tenant IDs and search text.

    :param tenant_ids: List of tenant IDs to get the courses for
    :type tenant_ids: List
    :param search_text: Search text to filter the courses by
    :type search_text: str
    """
    course_org_filter_list = get_course_org_filter_list(tenant_ids)['course_org_filter_list']
    tenant_sites = []
    for tenant_id in tenant_ids:
        if site := get_tenant_site(tenant_id):
            tenant_sites.append(site)

    queryset = CourseOverview.objects.filter(
        org__in=course_org_filter_list,
    )
    search_text = (search_text or '').strip()
    if search_text:
        queryset = queryset.filter(
            Q(display_name__icontains=search_text) |
            Q(id__icontains=search_text),
        )
    queryset = queryset.annotate(
        rating_count=Coalesce(Subquery(
            FeedbackCourse.objects.filter(
                course_id=OuterRef('id'),
                rating_content__isnull=False,
                rating_content__gt=0,
            ).values('course_id').annotate(count=Count('id')).values('count'),
            output_field=IntegerField(),
        ), 0),
    ).annotate(
        rating_total=Coalesce(Subquery(
            FeedbackCourse.objects.filter(
                course_id=OuterRef('id'),
                rating_content__isnull=False,
                rating_content__gt=0,
            ).values('course_id').annotate(total=Sum('rating_content')).values('total'),
        ), 0),
    ).annotate(
        enrolled_count=Count(
            'courseenrollment',
            filter=(
                Q(courseenrollment__is_active=True) &
                Q(courseenrollment__user__is_active=True) &
                Q(courseenrollment__user__is_staff=False) &
                Q(courseenrollment__user__is_superuser=False) &
                ~Exists(
                    CourseAccessRole.objects.filter(
                        user_id=OuterRef('courseenrollment__user_id'),
                        org=OuterRef('org'),
                    ),
                )
            ),
        )
    ).annotate(
        active_count=Count(
            'courseenrollment',
            filter=(
                Q(courseenrollment__is_active=True) &
                Q(courseenrollment__user__is_active=True) &
                Q(courseenrollment__user__is_staff=False) &
                Q(courseenrollment__user__is_superuser=False) &
                ~Exists(
                    CourseAccessRole.objects.filter(
                        user_id=OuterRef('courseenrollment__user_id'),
                        org=OuterRef('org'),
                    ),
                )
            ),
        )
    ).annotate(
        certificates_count=Coalesce(Subquery(
            GeneratedCertificate.objects.filter(
                course_id=OuterRef('id'),
                status='downloadable'
            ).values('course_id').annotate(count=Count('id')).values('count'),
            output_field=IntegerField(),
        ), 0),
    )

    return queryset
