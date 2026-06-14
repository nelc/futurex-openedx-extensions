"""Sync the CourseStat cache table."""
from typing import Any

from django.core.management.base import BaseCommand

from futurex_openedx_extensions.helpers.stats import sync_course_stats


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

    def handle(self, *args: Any, **options: Any) -> None:
        """Sync the CourseStat table, writing only when --commit is given."""
        commit = options['commit']
        count = sync_course_stats(commit=commit)

        if commit:
            self.stdout.write(self.style.SUCCESS(f'Synced certificate counts for {count} course(s).'))
        else:
            self.stdout.write(
                self.style.WARNING(f'Dry run: {count} course(s) would be synced. Pass --commit to write.')
            )
