"""Tests for add_config_access management command."""
import pytest
from django.core.management import call_command

from futurex_openedx_extensions.helpers.management.commands.add_config_access import Command
from futurex_openedx_extensions.helpers.models import ConfigAccessControl, ConfigMirror


@pytest.mark.django_db
class TestAddConfigAccessCommand:  # pylint: disable=no-self-use
    """Tests for add_config_access management command."""

    def test_command_creates_entries(self):
        """Test that the command creates ConfigAccessControl entries."""
        ConfigAccessControl.objects.all().delete()

        call_command('add_config_access')

        assert ConfigAccessControl.objects.count() > 0

        entry = ConfigAccessControl.objects.get(key_name='custom_pages')
        assert entry.key_type == 'list'
        assert entry.path == 'theme_v2.custom_pages'
        assert entry.writable is True

        entry = ConfigAccessControl.objects.get(key_name='site_domain')
        assert entry.key_type == 'string'
        assert entry.path == 'SITE_NAME'
        assert entry.writable is False

    def test_command_updates_existing_entries(self):
        """Test that the command updates existing entries."""
        ConfigAccessControl.objects.create(
            key_name='custom_pages',
            key_type='string',
            path='wrong.path',
            writable=False
        )

        call_command('add_config_access')

        entry = ConfigAccessControl.objects.get(key_name='custom_pages')
        assert entry.key_type == 'list'
        assert entry.path == 'theme_v2.custom_pages'
        assert entry.writable is True

    def test_command_creates_mirror_entries(self):
        """Test that the command creates ConfigMirror entries."""
        ConfigMirror.objects.all().delete()

        call_command('add_config_access')

        assert ConfigMirror.objects.count() == 3

        entry = ConfigMirror.objects.get(source_path='theme_v2.platform_settings.site_name.en')
        assert entry.destination_path == 'PLATFORM_NAME'
        assert entry.priority == 20
        assert entry.enabled is True

        entry = ConfigMirror.objects.get(source_path='PLATFORM_NAME')
        assert entry.destination_path == 'platform_name'
        assert entry.priority == 0
        assert entry.enabled is True

    def test_command_updates_existing_mirror_entries(self):
        """
        Test that the command updates existing ConfigMirror entries.
        """
        mirror_data = Command.CONFIG_MIRROR_DATA[0]
        ConfigMirror.objects.create(
            source_path=mirror_data['source_path'],
            destination_path=mirror_data['destination_path'],
            priority=mirror_data['priority'] + 10,
            enabled=not mirror_data['enabled'],
        )

        call_command('add_config_access')

        assert ConfigMirror.objects.count() == 3

        updated_mirror = ConfigMirror.objects.get(
            source_path=mirror_data['source_path'],
            destination_path=mirror_data['destination_path']
        )
        assert updated_mirror.priority == mirror_data['priority']
        assert updated_mirror.enabled == mirror_data['enabled']
