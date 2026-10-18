"""
Backfill ViewAllowedRoles.allow_write before the flag is enforced (ADR 0009 addendum F2, rule W).

Until now the flag was stored but never read, and rows created before the column existed carry the default False.
Enforcing it as-is would stop every current writer, so each role a write-capable view lists for writing gets True,
exactly where the view's declared defaults say it may write.

Only False becomes True, so running it twice changes nothing and no flag is ever lowered. A row that was ever saved
through the ORM history (created or edited by an operator in the admin or a shell) is left alone and only reported:
the rows the package seeds itself are written with ``bulk_create``, which leaves no history record, so "has history"
means "an operator touched it".
"""
import logging

from django.db import migrations

logger = logging.getLogger(__name__)

STAFF = 'staff'
CREATOR = 'org_course_creator_group'
API_GLOBAL = 'fx_api_access_global'
# Frozen at this release: the roles each write-capable view may write with (its declared read-write roles; for
# courses_list and libraries_list, which declare none, the roles they list today).
WRITE_ROLES = {
    'tenant_assets': [STAFF, API_GLOBAL],
    'categories_management': [STAFF, CREATOR],
    'category_detail': [STAFF, CREATOR],
    'categories_order': [STAFF, CREATOR],
    'course_categories': [STAFF, CREATOR],
    'course_certificates': [STAFF, CREATOR],
    'theme_config_draft': [STAFF, API_GLOBAL],
    'theme_config_publish': [STAFF, API_GLOBAL],
    'upload_file': [STAFF, API_GLOBAL],
    'exported_files_data': [STAFF, 'instructor', 'data_researcher', CREATOR],
    'learner_unenroll': [STAFF, 'instructor', CREATOR],
    'user_roles': [CREATOR],
    'courses_list': [STAFF, 'instructor', 'data_researcher', CREATOR],
    'libraries_list': [STAFF, 'instructor', 'library_user', 'data_researcher', CREATOR],
}


def backfill_allow_write(apps, schema_editor):  # pylint: disable=unused-argument
    """Set allow_write on the untouched rows of the write-capable views, and report the touched ones."""
    view_allowed_roles = apps.get_model('fx_helpers', 'ViewAllowedRoles')
    history = apps.get_model('fx_helpers', 'HistoricalViewAllowedRoles')
    touched_ids = set(history.objects.values_list('id', flat=True))

    for view_name, roles in WRITE_ROLES.items():
        rows = view_allowed_roles.objects.filter(view_name=view_name, allowed_role__in=roles, allow_write=False)
        skipped = list(rows.filter(id__in=touched_ids).values_list('allowed_role', flat=True))
        rows.exclude(id__in=touched_ids).update(allow_write=True)
        if skipped:
            logger.warning(
                'fx_helpers 0013: left allow_write=False on operator-edited rows of view (%s), roles %s. '
                'Review them before relying on writes through those roles.', view_name, sorted(skipped),
            )


class Migration(migrations.Migration):
    """Data migration, no schema change"""

    dependencies = [
        ('fx_helpers', '0012_coursecertificateissuance'),
    ]

    operations = [
        migrations.RunPython(backfill_allow_write, migrations.RunPython.noop),
    ]
