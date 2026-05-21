"""Sync CourseStat table"""
import logging
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from eox_tenant.models import TenantConfig
# Import your alternate open edX tables here as needed in the future
from lms.djangoapps.certificates.models import GeneratedCertificate

from futurex_openedx_extensions.helpers.models import CourseStat

logger = logging.getLogger(__name__)

LOOKBACK_WINDOW = timezone.timedelta(minutes=20)
FALLBACK_LAST_RUN = timezone.datetime(1970, 1, 1, tzinfo=timezone.utc)


class Command(BaseCommand):
    """Management command to fill up cache table of CourseStat"""
    help = 'Generic high-scale synchronization engine for multi-source CourseStat metrics'

    # =========================================================================
    # Add any source model, its filtering logic, and its tracking column here.
    # =========================================================================
    METRICS_MAPPING = {
        'certificate_count': {
            'source_model': GeneratedCertificate,
            'filter_q': Q(status='downloadable'),
            'date_field': 'modified_date',
            'default_value': 0,
        },
        # Future Column Example:
        # 'enrollment_count': {
        #     'source_model': CourseEnrollment,  # e.g. from student.models
        #     'filter_q': Q(is_active=True),
        #     'date_field': 'modified',         # tracking column for incremental updates
        #     'default_value': 0,
        # }
    }

    FIELDS_TO_UPDATE = list(METRICS_MAPPING.keys()) + ['last_updated']

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            '--mode',
            choices=['sync', 'rebuild'],
            default='sync',
            help='sync = incremental patch, rebuild = full system recompute',
        )
        parser.add_argument('--tenant_id', type=int, default=1)
        parser.add_argument('--batch_size', type=int, default=2500)
        parser.add_argument('--no-dry-run', action='store_true')

    def handle(self, *args: Any, **options: Any) -> None:
        tenant_id = options['tenant_id']
        self.mode = options['mode']  # pylint: disable=attribute-defined-outside-init
        self.batch_size = options['batch_size']  # pylint: disable=attribute-defined-outside-init
        self.dry_run = not options['no_dry_run']  # pylint: disable=attribute-defined-outside-init

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f'--- MODE: {self.mode.upper()} --- | DRY_RUN={self.dry_run}'
            )
        )

        tenant = TenantConfig.objects.filter(id=tenant_id).first()
        if not tenant:
            raise Exception(f'TenantConfig {tenant_id} not found')

        if self.mode == 'rebuild':
            self.stdout.write(
                self.style.WARNING(
                    '⚠️  WARNING: REBUILD MODE DETECTED.\n'
                    'This operation will completely wipe out '
                    'the CourseStat table before recalculating all data from scratch!'
                )
            )

            if not self.dry_run:
                self.stdout.write('Truncating CourseStat cache table...')
                CourseStat.objects.all().delete()

        last_run = self.get_last_run_at(tenant) if self.mode == 'sync' else None

        # Gather all affected course keys across all models dynamically
        affected_courses = self.get_affected_course_keys(last_run)
        self.stdout.write(f'Total distinct target courses found to evaluate: {len(affected_courses)}')

        if not affected_courses:
            self.stdout.write(self.style.SUCCESS('No courses require synchronization.'))
            return

        self.total_created = 0   # pylint: disable=attribute-defined-outside-init
        self.total_updated = 0   # pylint: disable=attribute-defined-outside-init
        self.total_unchanged = 0   # pylint: disable=attribute-defined-outside-init

        total_courses = self.process_course_set(affected_courses)

        if not self.dry_run and self.mode == 'sync':
            self.update_last_run(tenant)

        self.stdout.write('\n' + '=' * 50)
        self.stdout.write(self.style.SUCCESS('GENERIC SYNC RUN REPORT'))
        self.stdout.write('=' * 50)
        self.stdout.write(f'Total Unique Courses Evaluated: {total_courses}')
        self.stdout.write(f'Total Cached Records Created:   {self.total_created}')
        self.stdout.write(f'Total Cached Records Updated:   {self.total_updated}')
        self.stdout.write(f'Total Cached Records Unchanged: {self.total_unchanged}')
        self.stdout.write('=' * 50)

    def get_affected_course_keys(self, last_run: Any) -> set:
        """Finds distinct course keys safely without blowing up Python RAM footprint."""
        distinct_keys = set()

        for _, config in self.METRICS_MAPPING.items():
            self.stdout.write(f'Streaming course IDs from {config["source_model"].__name__}...')
            qs = config['source_model'].objects.values_list('course_id', flat=True).distinct()
            if self.mode == 'sync':
                time_filter = {f'{config["date_field"]}__gt': last_run}
                qs = qs.filter(**time_filter)

            for key in qs.iterator(chunk_size=self.batch_size):
                distinct_keys.add(key)

        return distinct_keys

    def process_course_set(self, course_set: set) -> int:
        """Converts the combined course set into clean pipeline execution batches."""
        course_list = list(course_set)
        total_courses = len(course_list)
        for i in range(0, total_courses, self.batch_size):
            chunk = course_list[i: i + self.batch_size]
            self.process_generic_batch(chunk)
        return total_courses

    def process_generic_batch(self, course_keys: list) -> None:  # pylint: disable=too-many-locals, too-many-branches
        """Aggregates all registered metrics dynamically within an isolated chunk."""
        now = timezone.now()

        # Initialize an empty blueprint dictionary mapping for this slice of courses
        # Shape: { 'course_id_1': {'certificate_count': 0, 'enrollment_count': 0} }
        incoming_data = {
            key: {
                field_name: field_config['default_value']
                for field_name, field_config in self.METRICS_MAPPING.items()
            }
            for key in course_keys
        }

        # 1. Dynamically loop through every metric defined in our configuration
        for field_name, config in self.METRICS_MAPPING.items():
            aggregates = (
                config['source_model'].objects
                .filter(Q(course_id__in=course_keys) & config['filter_q'])
                .values('course_id')
                .annotate(total=Count('id'))
            )
            for item in aggregates:
                course_id = item['course_id']
                incoming_data[course_id][field_name] = item['total']

        to_create = []
        to_update = []
        batch_unchanged = 0

        if self.mode == 'rebuild':
            for course_key, fields_map in incoming_data.items():
                model_kwargs = {
                    'course_key': course_key,
                    'last_updated': now,
                    **fields_map
                }
                to_create.append(CourseStat(**model_kwargs))
        else:
            # Standard 'sync' path: Read target database status to verify updates vs inserts
            existing_stats = {
                stat.course_key: stat
                for stat in CourseStat.objects.filter(course_key__in=course_keys)
            }

            # 3. Compare values and assign tracking states
            for course_key, fields_map in incoming_data.items():
                existing_obj = existing_stats.get(course_key)

                if existing_obj:
                    has_changes = False
                    for field_name, computed_val in fields_map.items():
                        if getattr(existing_obj, field_name) != computed_val:
                            setattr(existing_obj, field_name, computed_val)
                            has_changes = True

                    if has_changes:
                        existing_obj.last_updated = now
                        to_update.append(existing_obj)
                    else:
                        batch_unchanged += 1
                else:
                    model_kwargs = {
                        'course_key': course_key,
                        'last_updated': now,
                        **fields_map
                    }
                    to_create.append(CourseStat(**model_kwargs))

        if not self.dry_run:
            with transaction.atomic():
                if to_create:
                    CourseStat.objects.bulk_create(to_create, batch_size=self.batch_size)
                if to_update:
                    CourseStat.objects.bulk_update(
                        to_update,
                        fields=self.FIELDS_TO_UPDATE,
                        batch_size=self.batch_size
                    )

        self.total_created += len(to_create)
        self.total_updated += len(to_update)
        self.total_unchanged += batch_unchanged

        self.stdout.write(
            f'[BATCH] Checked={len(course_keys)} | '
            f'Created={len(to_create)} | '
            f'Updated={len(to_update)} | '
            f'Unchanged={batch_unchanged}'
        )

    def get_last_run_at(self, tenant: TenantConfig) -> timezone.datetime:  # pylint: disable=no-self-use
        """get command las runtime from tenant"""
        raw = (tenant.lms_configs or {}).get('last_run')
        if raw:
            parsed = parse_datetime(raw)
            if parsed:
                return parsed - LOOKBACK_WINDOW
        return FALLBACK_LAST_RUN

    def update_last_run(self, tenant: TenantConfig) -> None:  # pylint: disable=no-self-use
        """Update last_run time in tenant config"""
        cfg = tenant.lms_configs or {}
        cfg['last_run'] = timezone.now().isoformat()
        tenant.lms_configs = cfg
        tenant.save(update_fields=['lms_configs'])
