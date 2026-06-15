"""Helpers for computing and caching course statistics."""
from __future__ import annotations

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from lms.djangoapps.certificates.models import GeneratedCertificate

from futurex_openedx_extensions.helpers.models import CourseStat


def sync_course_stats(commit: bool = True) -> int:
    """
    Refresh the cached downloadable-certificate count for every course.

    The count is aggregated with a single grouped query (downloadable certificates of active
    users) and written with one bulk upsert in an atomic transaction: existing rows are
    updated and missing rows are created.

    ``certificate_count_non_staff`` is kept on the model but is left at 0 for now; consumers
    currently read ``certificate_count_all``. Skipping the per-row staff lookup keeps the sync
    fast. TODO: compute the staff-excluded count and populate this field.

    :param commit: When True (the default), write the computed counts to the database.
        When False, the counts are only computed (dry run) and nothing is written.
    :type commit: bool
    :return: The number of courses that have downloadable certificates.
    :rtype: int
    """
    counts = (
        GeneratedCertificate.objects
        .filter(status='downloadable', user__is_active=True)
        .values('course_id')
        .annotate(count=Count('id'))
    )

    now = timezone.now()
    stats = [
        CourseStat(
            course_key=row['course_id'],
            certificate_count_all=row['count'],
            # Staff-excluded count is not computed yet (see the docstring); kept at 0.
            certificate_count_non_staff=0,
            last_updated=now,
        )
        for row in counts
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
