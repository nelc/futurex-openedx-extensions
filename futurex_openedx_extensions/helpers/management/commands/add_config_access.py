"""
Django management command to add ConfigAccessControl entries for dashboard theme editor.

This command automates the creation of ConfigAccessControl entries that allow the
dashboard to read and write theme configuration values.

Usage:
    python manage.py lms add_config_access

"""
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from futurex_openedx_extensions.helpers.models import ConfigAccessControl, ConfigMirror


class Command(BaseCommand):
    """Django management command to create ConfigAccessControl entries."""

    help = 'Add ConfigAccessControl entries for dashboard theme editor access'

    CONFIG_ACCESS_DATA = {
        'course_categories': {
            'key_type': 'dict',
            'path': 'theme_v2.course_categories',
            'writable': True
        },
        'custom_pages': {
            'key_type': 'list',
            'path': 'theme_v2.custom_pages',
            'writable': True
        },
        'favicon_url': {
            'key_type': 'string',
            'path': 'favicon_path',
            'writable': True
        },
        'footer': {
            'key_type': 'dict',
            'path': 'theme_v2.footer',
            'writable': True
        },
        'footer_social_media_links': {
            'key_type': 'list',
            'path': 'theme_v2.footer.social_media_links',
            'writable': True
        },
        'fx_css_override_asset_slug': {
            'key_type': 'string',
            'path': 'theme_v2.fx_css_override_asset_slug',
            'writable': True
        },
        'fx_dev_css_enabled': {
            'key_type': 'boolean',
            'path': 'theme_v2.fx_dev_css_enabled',
            'writable': True
        },
        'header': {
            'key_type': 'dict',
            'path': 'theme_v2.header',
            'writable': True
        },
        'header_combined_login': {
            'key_type': 'boolean',
            'path': 'theme_v2.header.combined_login',
            'writable': True
        },
        'header_sections': {
            'key_type': 'list',
            'path': 'theme_v2.header.sections',
            'writable': True
        },
        'logo_image_url': {
            'key_type': 'string',
            'path': 'logo_image_url',
            'writable': True
        },
        'pages_about_us': {
            'key_type': 'dict',
            'path': 'theme_v2.pages.about_us',
            'writable': True
        },
        'pages_contact_us': {
            'key_type': 'dict',
            'path': 'theme_v2.pages.contact_us',
            'writable': True
        },
        'pages_courses': {
            'key_type': 'dict',
            'path': 'theme_v2.pages.courses',
            'writable': True
        },
        'pages_custom_page_1': {
            'key_type': 'dict',
            'path': 'theme_v2.pages.custom_page_1',
            'writable': True
        },
        'pages_custom_page_2': {
            'key_type': 'dict',
            'path': 'theme_v2.pages.custom_page_2',
            'writable': True
        },
        'pages_custom_page_3': {
            'key_type': 'dict',
            'path': 'theme_v2.pages.custom_page_3',
            'writable': True
        },
        'pages_custom_page_4': {
            'key_type': 'dict',
            'path': 'theme_v2.pages.custom_page_4',
            'writable': True
        },
        'pages_custom_page_5': {
            'key_type': 'dict',
            'path': 'theme_v2.pages.custom_page_5',
            'writable': True
        },
        'pages_custom_page_6': {
            'key_type': 'dict',
            'path': 'theme_v2.pages.custom_page_6',
            'writable': True
        },
        'pages_custom_page_7': {
            'key_type': 'dict',
            'path': 'theme_v2.pages.custom_page_7',
            'writable': True
        },
        'pages_custom_page_8': {
            'key_type': 'dict',
            'path': 'theme_v2.pages.custom_page_8',
            'writable': True
        },
        'pages_home': {
            'key_type': 'dict',
            'path': 'theme_v2.pages.home',
            'writable': True
        },
        'pages_terms': {
            'key_type': 'dict',
            'path': 'theme_v2.pages.terms',
            'writable': True
        },
        'platform_settings': {
            'key_type': 'dict',
            'path': 'theme_v2.platform_settings',
            'writable': True
        },
        'platform_settings_language': {
            'key_type': 'dict',
            'path': 'theme_v2.platform_settings.language',
            'writable': True
        },
        'site_domain': {
            'key_type': 'string',
            'path': 'SITE_NAME',
            'writable': False
        },
        'visual_identity': {
            'key_type': 'dict',
            'path': 'theme_v2.visual_identity',
            'writable': True
        }
    }

    CONFIG_MIRROR_DATA = [
        {
            'source_path': 'theme_v2.platform_settings.site_name.en',
            'destination_path': 'PLATFORM_NAME',
            'priority': 20,
            'enabled': True,
        },
        {
            'source_path': 'theme_v2.platform_settings.site_name.ar',
            'destination_path': 'PLATFORM_NAME',
            'priority': 10,
            'enabled': True,
        },
        {
            'source_path': 'PLATFORM_NAME',
            'destination_path': 'platform_name',
            'priority': 0,
            'enabled': True,
        },
    ]

    def log_success(self, processed: int, created: int, updated: int) -> None:
        """Log the summary of processed entries."""
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Successfully processed {processed} entries:'
        ))
        self.stdout.write(f'  - Created: {created}')
        self.stdout.write(f'  - Updated: {updated}')
        self.stdout.write('')

    def handle(self, *args: Any, **options: Any) -> None:
        """Execute the command to create ConfigAccessControl entries."""
        self.stdout.write(self.style.MIGRATE_HEADING('Creating ConfigAccessControl entries...'))
        self.stdout.write('')

        created_count = 0
        updated_count = 0

        with transaction.atomic():
            for key_name, fields in self.CONFIG_ACCESS_DATA.items():
                _, created = ConfigAccessControl.objects.update_or_create(
                    key_name=key_name,
                    defaults={
                        'key_type': fields['key_type'],
                        'path': fields['path'],
                        'writable': fields['writable'],
                    }
                )

                if created:
                    self.stdout.write(
                        self.style.SUCCESS(f'✓ Created: {key_name}')
                    )
                    created_count += 1
                else:
                    self.stdout.write(
                        self.style.WARNING(f'↻ Updated: {key_name}')
                    )
                    updated_count += 1

        self.log_success(
            processed=len(self.CONFIG_ACCESS_DATA),
            created=created_count,
            updated=updated_count
        )

        self.stdout.write(self.style.MIGRATE_HEADING('Creating ConfigMirror entries...'))
        self.stdout.write('')

        created_mirror_count = 0
        updated_mirror_count = 0

        with transaction.atomic():
            for mirror_data in self.CONFIG_MIRROR_DATA:
                _, created = ConfigMirror.objects.update_or_create(
                    source_path=mirror_data['source_path'],
                    destination_path=mirror_data['destination_path'],
                    defaults={
                        'priority': mirror_data['priority'],
                        'enabled': mirror_data['enabled'],
                    }
                )

                if created:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ Created Mirror: {mirror_data['source_path']} -> {mirror_data['destination_path']}"
                        )
                    )
                    created_mirror_count += 1
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"↻ Updated Mirror: {mirror_data['source_path']} -> {mirror_data['destination_path']}"
                        )
                    )
                    updated_mirror_count += 1

        self.log_success(
            processed=len(self.CONFIG_MIRROR_DATA),
            created=created_mirror_count,
            updated=updated_mirror_count
        )
