"""Helpers for computing and caching course statistics."""
from __future__ import annotations

from completion_aggregator.models import Aggregator
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from lms.djangoapps.certificates.models import GeneratedCertificate
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

from futurex_openedx_extensions.helpers.models import CourseStat

PROGRESS_COUNT_BATCH_SIZE = 500


def sync_course_stats(commit: bool = True) -> int:
    """
    Refresh the cached per-course counts: downloadable certificates, and learners with course-level completion
    above zero (the total the bulk progress feed reports; see the note at the progress query).

    Each count is aggregated with a single grouped query. The cache is then rebuilt inside an atomic
    transaction: every existing row is deleted and the fresh rows are bulk-inserted. This keeps the
    logic database-agnostic (no upsert) and is cheap at this table's scale (roughly one row per course).

    ``certificate_count_non_staff`` is kept on the model but is left at 0 for now; consumers
    currently read ``certificate_count_all``. Skipping the per-row staff lookup keeps the sync
    fast. TODO: compute the staff-excluded count and populate this field.

    :param commit: When True (the default), write the computed counts to the database.
        When False, the counts are only computed (dry run) and nothing is written.
    :type commit: bool
    :return: The number of courses that have downloadable certificates or enrollments with progress.
    :rtype: int
    """
    certificate_counts = {
        row['course_id']: row['count'] for row in GeneratedCertificate.objects.filter(
            status='downloadable', user__is_active=True,
        ).values('course_id').annotate(count=Count('id'))
    }
    # Counted from the completion aggregates alone, course by course: with the course keys given, the
    # (course_key, aggregation_name, block_key, percent) index answers each batch as a range read without touching
    # rows. Measured on the prod replica (2026-10-24): 4,165 courses in 9 batches, 13.3 s. Two heavier forms were
    # too slow for an hourly job: checking each row's enrollment and user (over 5 minutes), and the same count without
    # the course keys, which scans the whole 416M-entry index (over 5 minutes). So a learner who unenrolled or was
    # deactivated after starting is still counted, and the feed's total can be slightly above the rows it returns.
    progress_counts: dict = {}
    course_keys = list(CourseOverview.objects.values_list('id', flat=True))
    for start in range(0, len(course_keys), PROGRESS_COUNT_BATCH_SIZE):
        for row in Aggregator.objects.filter(
            course_key__in=course_keys[start:start + PROGRESS_COUNT_BATCH_SIZE],
            aggregation_name='course',
            percent__gt=0,
        ).values('course_key').annotate(count=Count('id')):
            progress_counts[row['course_key']] = row['count']

    now = timezone.now()
    stats = [
        CourseStat(
            course_key=course_key,
            certificate_count_all=certificate_counts.get(course_key, 0),
            # Staff-excluded count is not computed yet (see the docstring); kept at 0.
            certificate_count_non_staff=0,
            progress_count=progress_counts.get(course_key, 0),
            last_updated=now,
        )
        for course_key in sorted(set(certificate_counts) | set(progress_counts), key=str)
    ]

    if commit:
        with transaction.atomic():
            CourseStat.objects.all().delete()
            CourseStat.objects.bulk_create(stats, batch_size=500)

    return len(stats)
