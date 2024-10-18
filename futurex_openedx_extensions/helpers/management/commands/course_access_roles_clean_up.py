"""
This command cleans up course access roles for all users, for tenants with the FX Dashboard enabled.
"""
from __future__ import annotations

import copy
from typing import Dict

from common.djangoapps.student.models import CourseAccessRole
from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, CommandParser

from futurex_openedx_extensions.dashboard.serializers import UserRolesSerializer
from futurex_openedx_extensions.helpers import constants as cs
from futurex_openedx_extensions.helpers.exceptions import FXExceptionCodes
from futurex_openedx_extensions.helpers.roles import (
    cache_refresh_course_access_roles,
    delete_course_access_roles,
    get_user_course_access_roles,
    update_course_access_roles,
)
from futurex_openedx_extensions.helpers.tenants import get_all_tenant_ids, get_course_org_filter_list
from futurex_openedx_extensions.helpers.users import is_system_staff_user


class Command(BaseCommand):
    """
    Creates enrollment codes for courses.
    """

    help = 'Cleans up course access roles for all users'

    def __init__(self, *args, **kwargs):
        """Initialize the command."""
        super().__init__(*args, **kwargs)
        self.tenant_ids = get_all_tenant_ids()
        self.superuser = get_user_model().objects.filter(is_superuser=True, is_active=True).first()
        self.all_orgs = get_course_org_filter_list(self.tenant_ids)['course_org_filter_list']
        self.fake_request = type('Request', (object,), {
            'fx_permission_info': {
                'view_allowed_any_access_orgs': self.all_orgs,
                'view_allowed_tenant_ids_any_access': self.tenant_ids,
            },
            'query_params': {},
        })
        self.commit = False

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

    def _process_one_user(self, user):
        """Process one user."""
        user_id = user.id
        invalid_orgs = CourseAccessRole.objects.filter(
            user_id=user_id,
        ).exclude(
            org__in=self.all_orgs,
        ).values_list('org', flat=True).distinct()
        if invalid_orgs:
            print(f'**** User has invalid orgs in the roles: {list(invalid_orgs)}')
            print('**** this must be fixed manually..')
        if is_system_staff_user(user) or not user.is_active:
            user_desc = 'a system staff' if is_system_staff_user(user) else 'not active'
            print(f'**** User is {user_desc}, deleting all roles on all tenants..')
            delete_course_access_roles(
                caller=self.superuser,
                tenant_ids=self.tenant_ids,
                user=user,
                dry_run=not self.commit,
            )
            print('**** Done.')
            return

        invalid_orgs = CourseAccessRole.objects.filter(
            user_id=user_id,
        ).exclude(
            org__in=self.all_orgs,
        ).exclude(
            org='',
        ).values_list('org', flat=True).distinct()
        if invalid_orgs:
            print(f'**** User has invalid orgs in the roles: {list(invalid_orgs)}')
            print('**** this must be fixed manually..')

        empty_orgs = CourseAccessRole.objects.filter(
            user_id=user_id,
            org='',
        ).exclude(
            role__in=cs.COURSE_ACCESS_ROLES_GLOBAL,
        ).values_list('org', flat=True).distinct()
        if empty_orgs:
            print('**** User has roles with no organization!')
            print('**** this must be fixed manually..')

        unsupported_roles = CourseAccessRole.objects.filter(
            user_id=user_id,
        ).exclude(
            role__in=cs.COURSE_ACCESS_ROLES_SUPPORTED_READ,
        ).values_list('role', flat=True).distinct()
        if unsupported_roles:
            print(f'**** User has unsupported roles: {list(unsupported_roles)}')
            print('**** this must be fixed manually..')

        roles = UserRolesSerializer(user, context={'request': self.fake_request}).data
        for tenant_id in roles['tenants']:
            tenant_roles = copy.deepcopy(roles['tenants'][tenant_id])
            tenant_roles['tenant_id'] = tenant_id
            result = update_course_access_roles(
                caller=self.superuser,
                user=user,
                new_roles_details=tenant_roles,
                dry_run=not self.commit,
            )
            if result['error_code']:
                print(f'**** Failed for user {user_id}:{user.username}:{user.email} for tenant {tenant_id}..')
                print(f'**** {result["error_code"]}:{result["error_message"]}')
                self.print_helper_action(int(result['error_code']))


    def handle(self, *args: list, **options: Dict[str, str]) -> None:
        """Handle the command."""
        self.commit = (str(options['commit']).lower() == 'yes')

        user_ids = CourseAccessRole.objects.values_list(
            'user_id', flat=True,
        ).exclude(
            course_id__startswith='library-v1:',  # ignore library roles as they are not supported
        ).distinct()
        user_ids_to_clean = []

        print('-' * 80)
        print(f'{len(user_ids)} users to process..')
        for user_id in user_ids:
            cache_refresh_course_access_roles(user_id)
            roles = get_user_course_access_roles(user_id)
            if roles['useless_entries_exist']:
                user_ids_to_clean.append(user_id)
        if not user_ids_to_clean:
            print('No dirty entries found..')
        else:
            print(f'Found {len(user_ids_to_clean)} users with dirty entries..')

        for user_id in user_ids_to_clean:
            user = get_user_model().objects.get(id=user_id)
            print(f'\nCleaning up user {user_id}:{user.username}:{user.email}...')
            libraries_queryset = CourseAccessRole.objects.filter(
                user_id=user_id,
                course_id__startswith='library-v1:',
            )
            library_roles = []
            for role_record in libraries_queryset:
                library_roles.append(CourseAccessRole(
                    user_id=role_record.user_id,
                    role=role_record.role,
                    org=role_record.org,
                    course_id=role_record.course_id,
                ))
            if library_roles:
                print(f'**** User {user_id} has library roles: {len(library_roles)}')
                print('**** these will be removed before clean up then restored after..')
                libraries_queryset.delete()

            try:
                self._process_one_user(user)
            except Exception as e:
                print(f'**** Failed to process user {user_id}: {e}')

            if library_roles:
                print('**** Restoring library roles..')
                CourseAccessRole.objects.bulk_create(library_roles)
                print('**** Restored.')

        if self.commit:
            print('Operation completed..')
        else:
            print('Dry-run completed..')

        print('-' * 80)

    @staticmethod
    def print_helper_action(code: int) -> None:
        """Print helper action for the given error code."""
        message = None
        if code == FXExceptionCodes.INVALID_INPUT.value:
            message = (
                'Please check the input data and try again. Some roles are not supported in the update '
                'process and need to be removed manually.'
            )
        if message:
            print(f'**** {message}')
