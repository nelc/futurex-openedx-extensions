from __future__ import annotations

from typing import Dict

from common.djangoapps.student.models import CourseEnrollment, UserSignupSource, CourseAccessRole
from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, CommandParser

from futurex_openedx_extensions.helpers.tenants import get_tenants_by_org, get_tenants_sites


class Command(BaseCommand):
    """
    Creates missing UserSignupSource records for users who are enrolled in courses but do not have a signup source
    """

    help = 'Cleans up course access roles for all users'

    def add_arguments(self, parser: CommandParser) -> None:
        """Add arguments to the command."""
        parser.add_argument(
            '--commit',
            action='store',
            dest='commit',
            default='no',
            help='Commit changes, default is no (just perform a dry-run).',
            type=str,
        )

    def handle(self, *args: list, **options: Dict[str, str]) -> None:
        """Handle the command."""
        commit = (str(options['commit']).lower() == 'yes')
        if commit:
            print('**!!** Running in COMMIT mode **!!**')
        else:
            print('**!!** Running in dry-run mode **!!**')

        excluded_sites = {
            'pearsonvue.futurex.sa',
            'lms.futurex.sa',
            'dashboard.futurex.sa',
            'testapi.futurex.sa',
            'studio.nbu.futurex.sa',
        }

        users = get_user_model().objects.all()
        users_count = users.count()
        print(f'\nProcessing {users_count} users...')
        statistics = {
            'missing': {},
            'errors': 0,
        }
        for user in users:
            enrollment_orgs = set(list(CourseEnrollment.objects.filter(
                user=user,
            ).select_related('courseoverview').values_list('course_id__org', flat=True)))
            course_access_orgs = set(list(CourseAccessRole.objects.filter(user=user).exclude(org='').values_list('org', flat=True)))

            tenant_ids = set()
            for org in enrollment_orgs | course_access_orgs:
                tenant_ids.update(get_tenants_by_org(org))
            needed_sites = set([site.lower() for site in get_tenants_sites(list(tenant_ids))])
            signup_source_sites = set([site.lower() for site in list(UserSignupSource.objects.filter(user=user).values_list('site', flat=True))])
            missing_sites = needed_sites - signup_source_sites - excluded_sites
            if missing_sites:
                print(f'\n!! User {user.id} is missing signup sources for sites {missing_sites}')
                to_add = []
                for site in missing_sites:
                    statistics['missing'][site] = statistics['missing'].get(site, 0) + 1
                    to_add.append(UserSignupSource(user=user, site=site))
                try:
                    if commit:
                        UserSignupSource.objects.bulk_create(to_add)
                        print(f'Created {len(missing_sites)} signup sources for user {user.id}')
                except Exception as exc:
                    print('**** ERROR:', exc)
                    statistics['errors'] += 1
            users_count -= 1
            if users_count % 1000 == 0:
                self.stdout.write(f'\n------- {users_count} users remaining...')

        print(f'\n\nStatistics (number of missing records per site):')
        for site, count in statistics['missing'].items():
            print(f'    {site}: {count}')
        if commit:
            print('-' * 40)
            print(f'Insertion errors count: {statistics["errors"]}')
        print('\nDone!')
