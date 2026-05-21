"""Tests for sync_course_stats management command."""
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from eox_tenant.models import TenantConfig
from lms.djangoapps.certificates.models import GeneratedCertificate
from opaque_keys.edx.keys import CourseKey

from futurex_openedx_extensions.helpers.management.commands.sync_course_stats import Command
from futurex_openedx_extensions.helpers.models import CourseStat


@pytest.mark.django_db
@pytest.mark.usefixtures('base_data')
class TestSyncCertificatesCommand:
    """Tests for sync certificates management command."""

    def setup_method(self):
        """Clean state before each test."""
        self.tenant = TenantConfig.objects.get(id=1)  # pylint: disable=attribute-defined-outside-init

    def test_course_stats_created_on_force_sync(self):  # pylint: disable=no-self-use
        """CourseStat should be rebuilt during sync."""
        GeneratedCertificate.objects.create(
            user_id=1,
            course_id='course-v1:1+1+1',
            status='downloadable',
        )
        GeneratedCertificate.objects.create(
            user_id=2,
            course_id='course-v1:1+1+1',
            status='downloadable',
        )

        call_command('sync_course_stats', mode='sync')
        # by default command will run in dry run mode, so no course stat should be created
        assert not CourseStat.objects.filter(course_key=CourseKey.from_string('course-v1:1+1+1')).exists()

        call_command('sync_course_stats', mode='sync', no_dry_run=True)
        stat = CourseStat.objects.get(course_key=CourseKey.from_string('course-v1:1+1+1'))
        assert stat.certificate_count == 2

        # count updated to wrong.
        stat.certificate_count = 100000
        stat.save()

        # calling command again, should make the count correct
        call_command('sync_course_stats', mode='sync', no_dry_run=True)
        stat = CourseStat.objects.get(course_key=CourseKey.from_string('course-v1:1+1+1'))
        assert stat.certificate_count == 2

    def test_course_stats_incrementally(self):  # pylint: disable=no-self-use
        """Only affected courses should have stats updated."""
        CourseStat.objects.create(course_key=CourseKey.from_string('course-v1:1+1+1'), certificate_count=0)
        CourseStat.objects.create(course_key=CourseKey.from_string('course-v1:2+2+2'), certificate_count=3)

        GeneratedCertificate.objects.create(
            user_id=2,
            course_id='course-v1:1+1+1',
            status='downloadable',
        )
        GeneratedCertificate.objects.create(
            user_id=2,
            course_id='course-v1:3+3+3',
            status='downloadable',
        )

        call_command('sync_course_stats', mode='sync', no_dry_run=True)

        stat = CourseStat.objects.get(course_key=CourseKey.from_string('course-v1:1+1+1'))
        assert stat.certificate_count == 1  # previous stat row is updated

        stat = CourseStat.objects.get(course_key=CourseKey.from_string('course-v1:2+2+2'))
        assert stat.certificate_count == 3  # should remain unchanged until mode=rebuild is set.

        stat = CourseStat.objects.get(course_key=CourseKey.from_string('course-v1:3+3+3'))
        assert stat.certificate_count == 1  # new  stat row is added.

    def test_last_run_is_updated(self):
        """Command should update last_run in TenantConfig."""
        assert 'last_run' not in self.tenant.lms_configs
        call_command('sync_course_stats', mode='sync', no_dry_run=True)
        self.tenant.refresh_from_db()
        assert 'last_run' in self.tenant.lms_configs

    def test_sync_course_stats_raises_when_tenant_missing(self):  # pylint: disable=no-self-use
        """Command should fail if TenantConfig does not exist."""
        with pytest.raises(Exception) as exc_info:
            call_command('sync_course_stats', tenant_id=999)
        assert 'TenantConfig 999 not found' in str(exc_info.value)

    def test_fallback_used_when_no_last_run(self):
        """Should use fallback datetime when last_run is missing."""
        result = Command().get_last_run_at(tenant=self.tenant)
        assert result == timezone.datetime(1970, 1, 1, tzinfo=timezone.utc)

    def test_course_stats_created_on_force_sync_and_batch_size(self):  # pylint: disable=no-self-use
        """CourseStat should be rebuilt during force sync."""
        GeneratedCertificate.objects.create(
            user_id=1,
            course_id='course-v1:1+1+1',
            status='downloadable',
        )
        GeneratedCertificate.objects.create(
            user_id=2,
            course_id='course-v1:1+1+1',
            status='downloadable',
        )
        GeneratedCertificate.objects.create(
            user_id=1,
            course_id='course-v1:2+2+2',
            status='downloadable',
        )
        GeneratedCertificate.objects.create(
            user_id=1,
            course_id='course-v1:3+3+3',
            status='downloadable',
        )
        # by default command run in dry run mode, no stats should be created.
        call_command('sync_course_stats', mode='rebuild', batch_size=2)
        assert not CourseStat.objects.filter(
            course_key__in=[
                CourseKey.from_string('course-v1:1+1+1'),
                CourseKey.from_string('course-v1:2+2+2'),
                CourseKey.from_string('course-v1:3+3+3')
            ]
        ).exists()
        call_command('sync_course_stats', mode='rebuild', no_dry_run=True, batch_size=2)
        assert CourseStat.objects.get(course_key=CourseKey.from_string('course-v1:1+1+1')).certificate_count == 2
        assert CourseStat.objects.get(course_key=CourseKey.from_string('course-v1:2+2+2')).certificate_count == 1
        assert CourseStat.objects.get(course_key=CourseKey.from_string('course-v1:3+3+3')).certificate_count == 1

        GeneratedCertificate.objects.create(
            user_id=3,
            course_id='course-v1:1+1+1',
            status='downloadable',
        )
        GeneratedCertificate.objects.create(
            user_id=3,
            course_id='course-v1:2+2+2',
            status='downloadable',
        )
        GeneratedCertificate.objects.create(
            user_id=3,
            course_id='course-v1:3+3+3',
            status='downloadable',
        )
        call_command('sync_course_stats', mode='rebuild', no_dry_run=True, batch_size=2)
        assert CourseStat.objects.get(course_key=CourseKey.from_string('course-v1:1+1+1')).certificate_count == 3
        assert CourseStat.objects.get(course_key=CourseKey.from_string('course-v1:2+2+2')).certificate_count == 2
        assert CourseStat.objects.get(course_key=CourseKey.from_string('course-v1:3+3+3')).certificate_count == 2

    def test_command_for_no_updates(self):
        """Test that command run successfully when there are no stats to update/create."""
        # update last_run to now, and are no new certificae so calling command will have no affected courses.
        config = self.tenant.lms_configs
        config['last_run'] = timezone.now() + timezone.timedelta(minutes=30)
        self.tenant.lms_configs = config
        self.tenant.save()
        call_command('sync_course_stats', mode='sync', tenant_id=self.tenant.id)

    def test_command_for_old_date(self):   # pylint: disable=no-self-use
        """Test command for stale data."""
        # Some old data in stats, rebuild should make count correct.
        CourseStat.objects.create(
            course_key=CourseKey.from_string('course-v1:3+3+3'),
            certificate_count=3
        )
        CourseStat.objects.create(
            course_key=CourseKey.from_string('course-v1:2+2+2'),
            certificate_count=5
        )


@pytest.mark.django_db
@pytest.mark.parametrize(
    'lms_configs, expect_fallback',
    [
        (None, True),
        ({}, True),
        ({'last_run': 'invalid-date'}, True),
        ({'last_run': '2024-01-01T10:00:00Z'}, False),
    ],
)
def test_get_last_run_at_cases(
    lms_configs, expect_fallback, base_data  # pylint: disable=unused-argument
):
    """test get_last_run for different edge cases"""
    command = Command()
    tenant = TenantConfig.objects.get(id=1)
    tenant.lms_configs = lms_configs
    tenant.save(update_fields=['lms_configs'])
    result = command.get_last_run_at(tenant)
    if expect_fallback:
        assert result == timezone.datetime(1970, 1, 1, tzinfo=timezone.utc)
    else:
        assert result is not None
        assert result == parse_datetime(lms_configs['last_run']) - timedelta(minutes=20)
