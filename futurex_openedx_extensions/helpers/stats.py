"""Helpers for computing and caching course statistics."""
from __future__ import annotations

from django.db import transaction
from django.db.models import Count, OuterRef, Subquery
from django.utils import timezone
from lms.djangoapps.certificates.models import GeneratedCertificate
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers.models import CourseStat
from futurex_openedx_extensions.helpers.querysets import check_staff_exist_queryset


def sync_course_stats(commit: bool = True) -> int:
    """
    Refresh the cached downloadable-certificate counts for every course.

    Two counts are cached per course so callers stay backward compatible with the live
    queries: ``certificate_count_all`` mirrors the ``include_staff=True`` count and
    ``certificate_count_non_staff`` mirrors the ``include_staff=False`` count. Both only
    consider active users.

    The counts are aggregated with grouped queries and written with a single bulk upsert
    in one atomic transaction: existing rows are updated and missing rows are created.

    :param commit: When True (the default), write the computed counts to the database.
        When False, the counts are only computed (dry run) and nothing is written.
    :type commit: bool
    :return: The number of courses that have downloadable certificates.
    :rtype: int
    """
    certificates = GeneratedCertificate.objects.filter(status='downloadable', user__is_active=True)

    all_counts = {
        row['course_id']: row['count']
        for row in certificates.values('course_id').annotate(count=Count('id'))
    }
    non_staff_counts = {
        row['course_id']: row['count']
        for row in certificates.annotate(
            course_org=Subquery(CourseOverview.objects.filter(id=OuterRef('course_id')).values('org')),
        ).filter(
            ~check_staff_exist_queryset(ref_user_id='user_id', ref_org='course_org', ref_course_id='course_id'),
        ).values('course_id').annotate(count=Count('id'))
    }

    now = timezone.now()
    stats = [
        CourseStat(
            course_key=course_id,
            certificate_count_all=count,
            certificate_count_non_staff=non_staff_counts.get(course_id, 0),
            last_updated=now,
        )
        for course_id, count in all_counts.items()
    ]

    if commit:
        with transaction.atomic():
            CourseStat.objects.bulk_create(
                stats,
                update_conflicts=True,
                unique_fields=['course_key'],
                update_fields=['certificate_count_all', 'certificate_count_non_staff', 'last_updated'],
                batch_size=500,
            )

    return len(stats)
