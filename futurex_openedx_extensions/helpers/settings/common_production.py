"""Common Settings"""
from __future__ import annotations

from typing import Any


def plugin_settings(settings: Any) -> None:
    """plugin settings"""
    # Cache timeout for long living cache
    settings.FX_CACHE_TIMEOUT_COURSE_ACCESS_ROLES = getattr(
        settings,
        'FX_CACHE_TIMEOUT_COURSE_ACCESS_ROLES',
        60 * 30,  # 30 minutes
    )

    # Cache timeout for tenants info
    settings.FX_CACHE_TIMEOUT_TENANTS_INFO = getattr(
        settings,
        'FX_CACHE_TIMEOUT_TENANTS_INFO',
        60 * 60 * 2,  # 2 hours
    )

    settings.FX_CACHE_TIMEOUT_VIEW_ROLES = getattr(
        settings,
        'FX_CACHE_TIMEOUT_VIEW_ROLES',
        60 * 30,  # 30 minutes
    )

    settings.FX_CACHE_TIMEOUT_CONFIG_ACCESS_CONTROL = getattr(
        settings,
        'FX_CACHE_TIMEOUT_CONFIG_ACCESS_CONTROL',
        60 * 60 * 24,  # 1 day
    )

    # Exported CSV files directive name
    settings.FX_DASHBOARD_STORAGE_DIR = getattr(
        settings,
        'FX_DASHBOARD_STORAGE_DIR',
        'fx_dashboard'
    )

    # Default Course Effort
    settings.FX_DEFAULT_COURSE_EFFORT = getattr(
        settings,
        'FX_DEFAULT_COURSE_EFFORT',
        12,
    )

    # Minutes limit for export tasks
    settings.FX_TASK_MINUTES_LIMIT = getattr(
        settings,
        'FX_TASK_MINUTES_LIMIT',
        5,
    )

    # Max Period Chunks
    settings.FX_MAX_PERIOD_CHUNKS_MAP = getattr(
        settings,
        'FX_MAX_PERIOD_CHUNKS_MAP',
        {
            'day': 365,
            'month': 12,
            'quarter': 4,
            'year': 1,
        },
    )

    # FX SSO Information
    settings.FX_SSO_INFO = getattr(
        settings,
        'FX_SSO_INFO',
        {
            'dummy_entity_id': {
                'external_id_field': 'uid',
                'external_id_extractor': 'path to function to be extracted using extractors.import_from_path'
            },
        },
    )

    # Default Tenant site
    settings.FX_TEMPLATE_TENANT_SITE = getattr(
        settings,
        'FX_TEMPLATE_TENANT_SITE',
        'template.futurex.sa',
    )

    # Tenant Base Domain
    settings.FX_TENANTS_BASE_DOMAIN = getattr(
        settings,
        'FX_TENANTS_BASE_DOMAIN',
        'nelp.gov.sa',
    )

    # Course Categories Key
    settings.FX_COURSE_CATEGORY_CONFIG_KEY = getattr(
        settings,
        'FX_COURSE_CATEGORY_CONFIG_KEY',
        'course_categories',
    )

    # Course Category Name Max Length
    settings.FX_COURSE_CATEGORY_MAX_COUNT = getattr(
        settings,
        'FX_COURSE_CATEGORY_MAX_COUNT',
        20,
    )

    # Stop NEW certificates for courses with disabled issuance. Merged into any existing filters configuration
    # (e.g. the xAPI filters of eox-nelp), never replacing it. fail_silently=True keeps certificates issuing if the
    # step itself errors (e.g. migrations not applied yet); PreventCertificateCreation is always propagated
    filters_config = getattr(settings, 'OPEN_EDX_FILTERS_CONFIG', None) or {}
    certificate_filter = filters_config.setdefault(
        'org.openedx.learning.certificate.creation.requested.v1',
        {'fail_silently': True, 'pipeline': []},
    )
    pipeline = certificate_filter.setdefault('pipeline', [])
    step = 'futurex_openedx_extensions.helpers.certificates.StopCertificateIssuanceWhenDisabled'
    if step not in pipeline:
        pipeline.append(step)
    settings.OPEN_EDX_FILTERS_CONFIG = filters_config
