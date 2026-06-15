"""Tests for the sync_course_stats command and helper."""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from lms.djangoapps.certificates.models import GeneratedCertificate
from opaque_keys.edx.keys import CourseKey

from futurex_openedx_extensions.helpers.models import CourseStat
from futurex_openedx_extensions.helpers.stats import sync_course_stats

BLUE_COURSE = 'course-v1:acme+blue+1'
GREEN_COURSE = 'course-v1:acme+green+1'


def _make_user(username, is_active=True):
    """Create an active (by default) user."""
    return get_user_model().objects.create(username=username, email=f'{username}@example.com', is_active=is_active)


def _make_cert(user, course_id, status='downloadable'):
    """Create a GeneratedCertificate for the given user/course."""
    return GeneratedCertificate.objects.create(user=user, course_id=course_id, status=status)


@pytest.mark.django_db
@pytest.mark.usefixtures('base_data')
class TestCourseStatSync:
    """Tests for sync_course_stats."""

    def setup_method(self):
        """Capture the count of courses already seeded with downloadable certificates by base_data."""
        self.baseline = sync_course_stats(commit=False)  # pylint: disable=attribute-defined-outside-init

    def test_sync_creates_a_row_per_course(self):
        """sync writes one row per course that has downloadable certificates."""
        _make_cert(_make_user('learner_course_blue'), BLUE_COURSE)
        _make_cert(_make_user('learner_course_blue_2'), BLUE_COURSE)
        _make_cert(_make_user('learner_course_green'), GREEN_COURSE)

        synced = sync_course_stats()

        assert synced == self.baseline + 2  # two new courses gained downloadable certificates
        blue = CourseStat.objects.get(course_key=CourseKey.from_string(BLUE_COURSE))
        assert blue.certificate_count_all == 2
        assert blue.certificate_count_non_staff == 0  # not computed yet (see TODO in sync_course_stats)
        assert CourseStat.objects.get(course_key=CourseKey.from_string(GREEN_COURSE)).certificate_count_all == 1

    def test_sync_ignores_inactive_users(self):  # pylint: disable=no-self-use
        """Inactive users are excluded from the count."""
        _make_cert(_make_user('learner_course_blue'), BLUE_COURSE)
        _make_cert(_make_user('inactive_course_blue', is_active=False), BLUE_COURSE)

        sync_course_stats()

        assert CourseStat.objects.get(course_key=CourseKey.from_string(BLUE_COURSE)).certificate_count_all == 1

    def test_sync_counts_only_downloadable(self):  # pylint: disable=no-self-use
        """Only certificates with status='downloadable' are counted."""
        _make_cert(_make_user('learner_course_blue'), BLUE_COURSE, status='downloadable')
        _make_cert(_make_user('learner_course_blue_2'), BLUE_COURSE, status='generating')
        _make_cert(_make_user('learner_course_blue_3'), BLUE_COURSE, status='notpassing')

        sync_course_stats()

        assert CourseStat.objects.get(course_key=CourseKey.from_string(BLUE_COURSE)).certificate_count_all == 1

    def test_sync_updates_existing_row_without_duplicating(self):  # pylint: disable=no-self-use
        """A stale row is corrected rather than duplicated after a rebuild."""
        CourseStat.objects.create(
            course_key=CourseKey.from_string(BLUE_COURSE),
            certificate_count_all=100000,
            certificate_count_non_staff=100000,
        )
        _make_cert(_make_user('learner_course_blue'), BLUE_COURSE)
        _make_cert(_make_user('learner_course_blue_2'), BLUE_COURSE)

        sync_course_stats()

        course_key = CourseKey.from_string(BLUE_COURSE)
        assert CourseStat.objects.filter(course_key=course_key).count() == 1
        assert CourseStat.objects.get(course_key=course_key).certificate_count_all == 2

    def test_sync_refreshes_last_updated_on_update(self):  # pylint: disable=no-self-use
        """The rebuild refreshes last_updated for a course that already had a row."""
        old = timezone.datetime(2000, 1, 1, tzinfo=timezone.utc)
        stat = CourseStat.objects.create(course_key=CourseKey.from_string(BLUE_COURSE))
        # .update() bypasses auto_now so we can plant a stale timestamp.
        CourseStat.objects.filter(pk=stat.pk).update(last_updated=old)
        _make_cert(_make_user('learner_course_blue'), BLUE_COURSE)

        sync_course_stats()

        # The row is rebuilt (delete + re-insert), so re-fetch by course_key, not the old pk.
        refreshed = CourseStat.objects.get(course_key=CourseKey.from_string(BLUE_COURSE))
        assert refreshed.last_updated > old

    def test_sync_dry_run_writes_nothing(self):
        """commit=False computes the count but does not touch the database."""
        _make_cert(_make_user('learner_course_blue'), BLUE_COURSE)

        synced = sync_course_stats(commit=False)

        assert synced == self.baseline + 1
        assert not CourseStat.objects.exists()


@pytest.mark.django_db
@pytest.mark.usefixtures('base_data')
class TestSyncCourseStatsCommand:
    """Tests for the sync_course_stats management command."""

    def test_command_is_dry_run_by_default(self):  # pylint: disable=no-self-use
        """Without --commit the command writes nothing."""
        _make_cert(_make_user('learner_course_blue'), BLUE_COURSE)

        call_command('sync_course_stats')

        assert not CourseStat.objects.exists()

    def test_command_commit_writes_stats(self):  # pylint: disable=no-self-use
        """With --commit the command persists the computed counts."""
        _make_cert(_make_user('learner_course_blue'), BLUE_COURSE)
        _make_cert(_make_user('learner_course_blue_2'), BLUE_COURSE)

        call_command('sync_course_stats', commit=True)

        assert CourseStat.objects.get(course_key=CourseKey.from_string(BLUE_COURSE)).certificate_count_all == 2

    def test_command_async_dispatches_task(self):  # pylint: disable=no-self-use
        """With --async the command queues the Celery task instead of syncing synchronously."""
        _make_cert(_make_user('learner_course_blue'), BLUE_COURSE)

        with patch(
            'futurex_openedx_extensions.helpers.management.commands.sync_course_stats.sync_course_stats_task'
        ) as mock_task:
            call_command('sync_course_stats', run_async=True)

        mock_task.delay.assert_called_once_with()
        assert not CourseStat.objects.exists()
