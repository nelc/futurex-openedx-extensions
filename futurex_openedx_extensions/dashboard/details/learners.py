"""Learners details collectors"""
from __future__ import annotations

from typing import List

from common.djangoapps.student.models import CourseAccessRole, UserSignupSource
from django.contrib.auth import get_user_model
from django.db.models import Count, Exists, OuterRef, Q, Subquery
from django.db.models.query import QuerySet
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers.tenants import get_course_org_filter_list, get_tenant_site


def get_learners_queryset(tenant_ids: List, search_text: str = None) -> QuerySet:
    """
    Get the learners queryset for the given tenant IDs and search text.

    :param tenant_ids: List of tenant IDs to get the learners for
    :type tenant_ids: List
    :param search_text: Search text to filter the learners by
    :type search_text: str
    """
    course_org_filter_list = get_course_org_filter_list(tenant_ids)['course_org_filter_list']
    tenant_sites = []
    for tenant_id in tenant_ids:
        if site := get_tenant_site(tenant_id):
            tenant_sites.append(site)

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
        courses_count=Count(
            'courseenrollment',
            filter=(
                Q(courseenrollment__course__org__in=course_org_filter_list) &
                ~Exists(
                    CourseAccessRole.objects.filter(
                        user_id=OuterRef('id'),
                        org=OuterRef('courseenrollment__course__org')
                    )
                )
            ),
            distinct=True
        )
    ).annotate(
        certificates_count=Count(
            'generatedcertificate',
            filter=(
                Q(generatedcertificate__course_id__in=Subquery(
                    CourseOverview.objects.filter(
                        org__in=course_org_filter_list
                    ).values_list('id', flat=True)
                )) &
                Q(generatedcertificate__status='downloadable')
            ),
            distinct=True
        )
    ).annotate(
        has_site_login=Exists(
            UserSignupSource.objects.filter(
                user_id=OuterRef('id'),
                site__in=tenant_sites
            )
        )
    ).filter(
        Q(courses_count__gt=0) | Q(has_site_login=True)
    ).select_related('profile').order_by('id')

    return queryset