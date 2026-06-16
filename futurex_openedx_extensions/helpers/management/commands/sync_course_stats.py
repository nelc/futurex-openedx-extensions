"""Sync the CourseStat cache table."""
from typing import Any

from django.core.management.base import BaseCommand

from futurex_openedx_extensions.helpers.stats import sync_course_stats
from futurex_openedx_extensions.helpers.tasks import sync_course_stats_task


class Command(BaseCommand):
    """Refresh cached per-course certificate counts in the CourseStat table."""

    help = 'Refresh cached per-course certificate counts in the CourseStat table.'

    def add_arguments(self, parser: Any) -> None:
        """Add the command arguments."""
        parser.add_argument(
            '--commit',
            action='store_true',
            help='Write the computed counts to the database. Without it the command runs as a dry run.',
        )
        parser.add_argument(
            '--async',
            action='store_true',
            dest='run_async',
            help='Dispatch the sync as a Celery task (always commits) instead of running synchronously.',
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Sync the CourseStat table, writing only when --commit is given."""
        if options['run_async']:
            sync_course_stats_task.delay()
            self.stdout.write(self.style.SUCCESS('Queued sync_course_stats_task (commits on completion).'))
            return

        commit = options['commit']
        count = sync_course_stats(commit=commit)

        if commit:
            self.stdout.write(self.style.SUCCESS(f'Synced certificate counts for {count} course(s).'))
        else:
            self.stdout.write(
                self.style.WARNING(f'Dry run: {count} course(s) would be synced. Pass --commit to write.')
            )
