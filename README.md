# FutureX Multi-tenant Reporting and Admin

`futurex-openedx-extensions` is a proprietary Open edX plugin (developed by Zeitlabs for NELC/FutureX) that adds a multi-tenant analytics-and-administration dashboard on top of an Open edX deployment. It installs into the LMS process and surfaces a large REST API under `/api/fx/...` for managing courses, learners, roles, tenants, configuration/theming, statistics, and payments. At its core is a multi-tenant theme/config system: a "template" tenant supplies default config and shared assets, a whitelist controls which config keys are editable, and edits flow through a draft-and-publish workflow before being consumed by an external comprehensive theme (futurex-theme).

## Table of Contents

- [Overview & Architecture](#overview--architecture)
- [Installing in Tutor (dev)](#installing-in-tutor-dev)
- [Testing & Quality (tox)](#testing--quality-tox)
- [Django Models](#django-models)
- [The Template Tenant](#the-template-tenant)
- [Config Access Control](#config-access-control)
- [Draft & Publish Workflow](#draft--publish-workflow)
- [Theme Consumption (futurex-theme)](#theme-consumption-futurex-theme)

## Overview & Architecture

`futurex-openedx-extensions` is a proprietary Open edX plugin that adds a multi-tenant analytics-and-administration dashboard on top of an Open edX deployment. It is not a standalone service: it installs into the LMS (and CMS) process and surfaces a large REST API under `/api/fx/...` for managing courses, learners, roles, tenants, configuration/theming, statistics, and payments.

> Note: the checked-in `README.rst`, `openedx.yaml`, `catalog-info.yaml`, and `docs/decisions/0001-purpose-of-this-repo.rst` are all unfilled Open edX cookiecutter boilerplate ("One-line description...", TODO/PLACEHOLDER) and should not be relied on for real documentation. The substantive description here is derived from the code.

### How it plugs in

The package registers itself through Open edX's plugin mechanism via three `lms.djangoapp` entry points in `setup.py`, each pointing at a Django `AppConfig`:

| Entry point | AppConfig | Django label |
|---|---|---|
| `fx_dashboard` | `dashboard.apps.DashboardConfig` | `fx_dashboard` |
| `fx_helpers` | `helpers.apps.HelpersConfig` | `fx_helpers` |
| `fx_upgrade` | `upgrade.apps.UpgradeConfig` | `fx_upgrade` |

Each `AppConfig` declares a `plugin_app` dict so the Open edX plugin framework auto-wires it. Settings are injected for the `production` stack of both `lms.djangoapp` and `cms.djangoapp` via a `settings_config` → `settings.common_production` relative path (`dashboard/apps.py`, `helpers/apps.py`, `upgrade/apps.py`); those `plugin_settings(settings)` functions set `FX_*` defaults (cache timeouts, tenant domains, course-category limits, etc.) using `getattr` so deployments can override them (`dashboard/settings/common_production.py`, `helpers/settings/common_production.py`). Only `fx_dashboard` registers a `url_config` (namespace `fx_dashboard`), which is where the API routes live (`dashboard/urls.py`).

`HelpersConfig.ready()` does additional boot-time wiring beyond settings: it imports `custom_roles`, `monkey_patches`, and `signals`, and rewrites the edx-platform `CAN_MASQUARADE_LEARNER_PROGRESS` bridgekeeper permission to `staff | data_researcher` (`helpers/apps.py`). So the plugin deliberately patches host-platform behavior at startup.

### The three Django apps

| App | Role | Key contents |
|---|---|---|
| **dashboard** | The public surface: DRF API (views, serializers, pagination, middleware, docs). Org/tenant-scoped HTTP endpoints. | `views/` (split by domain: `courses`, `learners`, `roles`, `statistics`, `configs`, `categories`, `payments`, `clickhouse`, `files`, `admin`, `misc`), `serializers.py`, `urls.py` |
| **helpers** | Shared core library — everything dashboard is built on. Models, roles/permissions, tenant resolution, caching, config/theme, tasks. | `models.py`, `roles.py`, `tenants.py`, `caching.py`, `permissions.py`, `theme.py`, `stats.py`, `extractors.py`, `signals.py`, `monkey_patches.py`, `clickhouse_operations.py` |
| **upgrade** | Release-version abstraction so one codebase runs across multiple Open edX releases. | `utils.py`, `models_switch.py` |

The dependency direction is one-way: `dashboard` imports from `helpers`; `helpers` is the foundation; `upgrade` is consulted where release differences matter. `dashboard/urls.py` maps the API into versioned route families — `accessible`, `courses`, `libraries`, `learners`, `roles`, `statistics`, `tenants`, `config`, `assets`, `payments`, `export`, `query` (ClickHouse) — most under `/api/fx/<area>/v1/`, with a couple of `v2` endpoints already present (`AccessibleTenantsInfoViewV2`, `PaymentOrdersViewV2`).

The `helpers` app owns the plugin's own DB models (all migrated under label `fx_helpers`): `ViewAllowedRoles`, `ViewUserMapping`, `ClickhouseQuery`, `DataExportTask`, `ConfigAccessControl`, `TenantAsset`, `DraftConfig`, `ConfigMirror`, `CourseStat` (`helpers/models.py`). See [Django Models](#django-models) for details.

### Multi-tenant by design

The system is multi-tenant: a "tenant" maps to an `eox_tenant.TenantConfig` and its associated `Route`/`Site` records, and effectively to a set of course orgs. `helpers/tenants.py` resolves tenants to org filter lists, sites, and excluded/bad-config tenants, while `helpers/roles.py` (~1.6k lines) implements per-tenant/per-org access-role logic on top of edx-platform's `CourseAccessRole`. Authorization flows through DRF permission classes in `helpers/permissions.py`, which build a per-request `fx_permission_info` (accessible tenant IDs, user roles, org filters, system-staff flag) used to scope every query. The result: callers only see data for the tenants/orgs their roles grant, and most endpoints accept a `tenant_ids` scope.

### Supported Open edX releases

The plugin targets three releases — **redwood**, **sumac**, and **teak** — defined in `upgrade/utils.py`. At import time it reads edx-platform's `RELEASE_LINE` and resolves `FX_CURRENT_EDX_PLATFORM_VERSION` (`upgrade/utils.py`); `upgrade/models_switch.py` is the single branch point where release-specific model imports would be selected (currently all three branches are no-ops because nothing the plugin uses differs across these releases). Release-specific install extras are wired in `setup.py` (`extras_require` redwood/sumac/teak, each pulling a different constraints file), and tests run per-release via tox mocks.

**teak is the current/primary target.** Redwood tests were disabled (commit `96884f0 "chore: disable redwood tests"`), and CI now runs only the `quality` and `py311-teak` tox environments (`.github/workflows/ci.yml`) even though `tox.ini` still defines all three. Per project memory, redwood/sumac support is being dropped and the codebase assumes Django 4.2. Python 3.11+ is required (`setup.py`).

## Installing in Tutor (dev)

`futurex-openedx-extensions` is a standard Open edX Django plugin. It is installed into the **LMS** Python environment and auto-registers via `entry_points` — no manual `INSTALLED_APPS`/URL wiring is needed. The pattern below follows the conventional Tutor "mounted package" dev workflow; the plugin-specific parts (extras, entry points, migrations, the `add_config_access` command, and required settings) are codified in this repo.

### What gets installed

- **Distribution name:** `futurex-openedx-extensions`; **import package / folder name:** `futurex_openedx_extensions` (`setup.py`).
- **Python:** `python_requires='>=3.11'` (`setup.py`). Use the Open edX image's Python (Teak ships 3.11).
- **Release extras:** `setup.py` defines version-pinned dependency sets keyed by Open edX release: `redwood`, `sumac`, `teak`. Each pulls `requirements/base.in` (`Django`, `clickhouse-connect`) constrained by `requirements/constraints-<release>.txt`. Install with the extra that matches your platform, e.g. `.[teak]`.
- **Auto-registered apps:** three apps register under the `lms.djangoapp` entry point group — `fx_dashboard`, `fx_helpers`, `fx_upgrade` (`setup.py`). On LMS boot, Open edX's plugin machinery adds them to `INSTALLED_APPS` and applies each app's `plugin_app` config (`dashboard/apps.py`, `helpers/apps.py`, `upgrade/apps.py`). Django settings come from each app's `settings/common_production.py` (`plugin_settings(settings)`), and the dashboard mounts its REST API under the `fx_dashboard` URL namespace (`dashboard/urls.py`, e.g. `/api/fx/...`).

> **CMS note:** the three apps *declare* a `cms.djangoapp` block in their `plugin_app['settings_config']` (`dashboard/apps.py`, `helpers/apps.py`, `upgrade/apps.py`), but `setup.py` only registers entry points under `lms.djangoapp` — there is **no `cms.djangoapp` entry-points group**. As packaged, the plugin loads into the LMS only. If you need it in Studio/CMS, you must add a `cms.djangoapp` entry-points block to `setup.py` and reinstall; otherwise CMS will not pick it up.

### 1. Mount the repo and install into the LMS container

```bash
# Tell Tutor to mount this checkout into the openedx image (lms + cms)
tutor mounts add /Users/omar/work/nelc/futurex-openedx-extensions

# Bring the platform up (rebuilds/links mounts on first launch)
tutor dev launch
```

`tutor mounts add` bind-mounts the directory to `/mnt/futurex-openedx-extensions` inside the container. To (re)install editable without a full image rebuild, install into the running LMS with the release extra (note: extra in quotes so the shell doesn't glob the brackets):

```bash
tutor dev exec lms pip install -e "/mnt/futurex-openedx-extensions[teak]"
tutor dev restart lms        # reload so entry points / plugin settings take effect
```

For Sumac or Redwood images, swap the extra: `"...[sumac]"` / `"...[redwood]"`.

> The Tutor commands above (`tutor mounts add`, `tutor dev launch`, the editable install, the `/mnt/...` mount path) are standard Tutor dev conventions, not codified in this repo. The repo ships no Tutor plugin, Dockerfile, or how-to.

### 2. Run migrations

All plugin migrations are owned by the **helpers** app (`fx_helpers`); `dashboard` and `upgrade` ship no migrations. Current set lives in `futurex_openedx_extensions/helpers/migrations/` and includes, e.g., `0009_draftconfig`, `0010_historicalconfigmirror_configmirror`, `0011_coursestat`. Apply them in the LMS:

```bash
tutor dev exec lms ./manage.py lms migrate fx_helpers
# or just: tutor dev exec lms ./manage.py lms migrate
```

### 3. Seed dashboard config rows

The theme editor in the dashboard needs `ConfigAccessControl` and `ConfigMirror` rows. The repo provides a management command that upserts them idempotently (`helpers/management/commands/add_config_access.py`):

```bash
tutor dev exec lms ./manage.py lms add_config_access
```

This creates/updates ~30 `ConfigAccessControl` entries (logo/header/footer/pages/`platform_settings`, etc.) and 3 `ConfigMirror` entries (mirroring `theme_v2.platform_settings.site_name.*` → `PLATFORM_NAME` → `platform_name`). See [Config Access Control](#config-access-control) for the full whitelist and mirror semantics.

### 4. Key settings the deployment must define

Most `FX_*` settings are defaulted via `getattr(settings, ..., default)` in the plugin's `plugin_settings` (`helpers/settings/common_production.py`, `dashboard/settings/common_production.py`), so they work out of the box. The ones you almost certainly need to override for a real tenant setup:

| Setting | Where defaulted | Why it matters |
| --- | --- | --- |
| `FX_TEMPLATE_TENANT_SITE` | `helpers/settings/common_production.py` (default `template.futurex.sa`) | Names the "template" tenant looked up by `TenantConfig`. If no `TenantConfig` matches this domain/`external_key`, tenant resolution logs a CONFIGURATION ERROR and default-config lookups fail (`helpers/tenants.py`, `helpers/admin.py`). |
| `NELC_DASHBOARD_BASE` | **Not defaulted by the plugin** — read via `getattr(settings, 'NELC_DASHBOARD_BASE', None)` | Base host for the dashboard URL surfaced to staff/role users; when unset, `get_fx_dashboard_url()` returns `None` and no dashboard link is produced (`helpers/theme.py`). Set it in your Tutor settings override if you want the dashboard link. |
| `FX_TENANTS_BASE_DOMAIN` | `helpers/settings/common_production.py` (default `nelp.gov.sa`) | Base domain for tenant sites; override to match your deployment. |

Define overrides through a Tutor plugin / `OPENEDX_EXTRA_*` settings rather than editing the package, e.g.:

```python
# in a Tutor plugin patch (openedx-common-settings / openedx-lms-production-settings)
NELC_DASHBOARD_BASE = "dashboard.local.overhang.io"
FX_TEMPLATE_TENANT_SITE = "template.local.overhang.io"
```

Then `tutor dev restart lms`.

### Quick verification

```bash
tutor dev exec lms pip show futurex-openedx-extensions      # confirm editable install
tutor dev exec lms ./manage.py lms showmigrations fx_helpers # all [X]
tutor dev exec lms ./manage.py lms shell -c \
  "from django.conf import settings; print(settings.FX_TEMPLATE_TENANT_SITE)"
```

## Testing & Quality (tox)

All tests and linters run through [`tox`](tox.ini). Tests cannot be run with a bare `pytest`: the plugin imports edx-platform packages (`lms`, `cms`, `common`, `openedx`, `organizations`, ...) that don't exist outside a real platform, so tox injects a stack of *fake* edx-platform modules onto `PYTHONPATH` and points Django at a release-specific settings module. See "Running tests" below.

### tox environments

`envlist = quality,py311-{redwood,sumac,teak}` — the `{redwood,sumac,teak}` factor expands `py311` into three release-specific test envs (one per supported Open edX release line). **CI runs only two of these:** `.github/workflows/ci.yml` defines a matrix of exactly `quality` and `py311-teak`. Redwood tests were turned off (git: `chore: disable redwood tests`), so `py311-redwood` / `py311-sumac` exist in `tox.ini` but are not exercised by CI.

| Env | basepython | Purpose | Notes |
|-----|-----------|---------|-------|
| `quality` | `python3.11` | Static analysis & lint gate | uv-based (`uv_seed = true`); runs flake8, mypy, pycodestyle, pydocstyle, pylint, isort. **Run by CI.** |
| `py311-teak` | 3.11 | Unit tests on the Teak release line | `DJANGO_SETTINGS_MODULE=test_settings_teak`; 100% coverage gate. **Run by CI.** |
| `py311-redwood` | 3.11 | Unit tests on Redwood | Defined but **disabled in CI**. |
| `py311-sumac` | 3.11 | Unit tests on Sumac | Defined but **not in CI matrix**. |
| `docs` | — | Build Sphinx docs + wheel (`doc8`, `make html`, `twine check`) | Not in CI matrix. |
| `pii_check` | — | `code_annotations` PII lint against `.pii_annotations.yml` | Not in CI matrix. |

CI installs deps with `pip install -r requirements/ci.in`, then runs `tox -e <env>` on `ubuntu-22.04` / Python 3.11.

### How the fake edx-platform mocks work

The plugin code imports real edx-platform packages, which aren't installed in CI. `test_utils/edx_platform_mocks_*` supplies stand-ins:

- **`edx_platform_mocks_shared`** holds all the actual fake modules — `lms/`, `cms/`, `common/`, `openedx/`, `organizations/`, `completion/`, `xmodule/`, `zeitlabs_payments/`, `eox_*`, plus the `fake_models` Django app whose migrations the test command (re)generates. This is always on `PYTHONPATH` and always installed.
- **`edx_platform_mocks_{redwood,sumac,teak}`** are essentially empty marker packages — each is just a `setup.py` with `packages=[]` and no modules of its own. They exist so the per-release tox factor has something release-specific to install, but today the shared package carries everything (the `models_switch.py` branches all `pass` — "nothing changed that we're using in this package").

The `py311-teak` env stacks them as `PYTHONPATH = .../edx_platform_mocks_shared:.../edx_platform_mocks_teak:$PYTHONPATH` and also `pip install -e`'s both. `test_settings_teak.py` then does `from openedx.core import release; release.RELEASE_LINE = 'teak'` — `openedx.core.release` itself comes from the shared mock — which drives `FX_CURRENT_EDX_PLATFORM_VERSION` in `futurex_openedx_extensions/upgrade/utils.py`.

### The `quality` env and per-release pylint

`quality` (`tox.ini`) installs only the **shared** mock plus `requirements/quality.in` (flake8/flake8-quotes, mypy, pycodestyle, pydocstyle, edx-lint/pylint, isort), constrained by `test-constraints-redwood.txt`. It runs, in order:

1. `flake8`, `mypy`, `pycodestyle`, `pydocstyle` over `futurex_openedx_extensions tests test_utils manage.py`.
2. **pylint, with special per-release handling.**
3. `isort --check-only --diff` over the package, tests, and all three `test_settings_*.py`.

**Why pylint is run multiple times:** almost the entire codebase is release-agnostic, but `futurex_openedx_extensions/upgrade/releases/{redwood,sumac,teak}/` is release-divergent — each subpackage is meant to import edx-platform symbols that differ between releases, so it can only be linted while the *matching* release's mocks are installed. So `quality`:

- Installs the redwood mock and lints **everything except** `upgrade/` (`--ignore-paths="^futurex_openedx_extensions/upgrade/"`) — valid because non-upgrade code is shared across all releases.
- Lints `upgrade/` for redwood only (ignoring `releases/(?!redwood/)`), then `pip uninstall` redwood / `pip install` sumac and lints `upgrade/` for sumac, then swaps to teak and lints `upgrade/` for teak.

This mock swap-in/swap-out via `pip install`/`pip uninstall` is the mechanism that lets one pylint pass see redwood symbols, the next see sumac, etc. Today these per-release subpackages are scaffolding (no divergent code yet), so the multiple passes are mostly future-proofing — but the mechanism is real.

### The `py311-teak` test env

From `[testenv]` with the `teak` factor:

- `skip_install = true` — the plugin under test is imported from the source tree, not installed.
- `setenv`: `DJANGO_SETTINGS_MODULE=test_settings_teak`, `PYTEST_COV_CONFIG=.coveragerc-teak`, and the shared+teak `PYTHONPATH` stack described above.
- `deps`: `-c requirements/test-constraints-teak.txt` (pins everything to the Teak release/branch constraints, including upstream edx-platform's `constraints.txt`), `-r requirements/test.in`, editable installs of the shared + teak mocks, and `setuptools==79.0.0`.
- `commands`:
  1. `rm -Rf` the generated `fake_models/migrations` for every mock dir.
  2. `python manage.py makemigrations fake_models` — regenerate migrations for the shared `fake_models` app.
  3. `python manage.py check` — Django system check / import sanity.
  4. `pytest {posargs} --cov-config=.coveragerc-teak`.

**Coverage gate:** `[pytest] addopts` hard-codes `--cov futurex_openedx_extensions --cov tests --cov-report term-missing --cov-report xml --cov-fail-under=100`, so the suite **fails under 100% coverage**. `.coveragerc-teak` scopes coverage to `futurex_openedx_extensions` with `branch = True` and omits the `test_settings_*.py` files, migrations, `static/`, the MySQL-only `mysql_functions.py`, `upgrade/models_switch.py`, and the non-teak `upgrade/releases/{redwood,sumac}/*` (so version-specific code doesn't drag coverage below 100% on the teak run).

### Running tests

```bash
# Lint / static-analysis gate (flake8, mypy, pycodestyle, pydocstyle, pylint, isort)
tox -e quality

# Full unit-test suite on the Teak release line (this is what CI runs)
tox -e py311-teak

# Run a subset — everything after `--` is passed through to pytest as {posargs}
tox -e py311-teak -- tests/test_helpers/test_something.py
tox -e py311-teak -- tests/test_helpers/ -k some_test_name
```

Do **not** invoke `pytest` directly: tests need the mock `PYTHONPATH` (shared + teak fake edx-platform modules) and `DJANGO_SETTINGS_MODULE=test_settings_teak`, both of which tox sets up. A bare `pytest` will fail to import `lms`/`cms`/`openedx`/etc. Because `--cov-fail-under=100` is baked into `addopts`, running a narrow path subset will report a coverage failure even when those tests pass — use the full env for a true pass/fail.

## Django Models

All application models live in a single module, `futurex_openedx_extensions/helpers/models.py`. Custom managers, querysets, and update helpers live in `futurex_openedx_extensions/helpers/model_helpers.py`. Migrations live in `futurex_openedx_extensions/helpers/migrations/` (`0001_initial.py` through `0011_coursestat.py`).

History tracking uses **django-simple-history** (`from simple_history.models import HistoricalRecords`). Any model with a `history = HistoricalRecords()` field gets an auto-generated `Historical<Model>` shadow table that records every insert/update/delete (the `Historical*` tables were created in migrations `0003`, `0006`, `0008`, and `0010`).

Several models reference Open edX core models directly: `TenantConfig` (from `eox_tenant.models`), `CourseAccessRole` (from `common.djangoapps.student.models`), the Django `User` model (`get_user_model()`), and `CourseKeyField` (from `opaque_keys`).

### Model overview

| Model | History-tracked | FK to `TenantConfig` | Purpose |
|---|---|---|---|
| `ViewAllowedRoles` | Yes | No | Maps a view name to the roles allowed to access it (and whether write is allowed). |
| `ViewUserMapping` | Yes | No | Per-user override granting access to a view; custom manager annotates `usable`. |
| `ClickhouseQuery` | Yes | No | Stores parameterized Clickhouse SQL queries, validated on save. |
| `DataExportTask` | No | **Yes** | Tracks async CSV/data-export jobs (status, progress, file). |
| `ConfigAccessControl` | No | No | Declares which tenant-config keys/paths are readable/writable (theme editor). |
| `TenantAsset` | Yes | **Yes** | Per-tenant uploaded files/assets (theme editor). |
| `DraftConfig` | No | **Yes** | Draft (unpublished) tenant config values; uses `NoUpdateQuerySet` (theme editor). |
| `ConfigMirror` | Yes | No (operates on `TenantConfig.lms_configs`) | Rules to copy/mirror one config path to another during tenant sync (theme editor). |
| `CourseStat` | No | No | Cached per-course certificate counts for fast reads. |

### `ViewAllowedRoles` (models.py:37)
Allowed roles for every supported view. Fields: `view_name`, `view_description` (nullable), `allowed_role`, `allow_write` (bool, default `False`). `unique_together = ('view_name', 'allowed_role')`. History-tracked.

### `ViewUserMapping` (models.py:124) + `ViewUserMappingManager` (models.py:53)
Per-user mapping that can grant a specific user access to a view independent of role configuration. Fields: `user` (FK → `User`, `CASCADE`), `view_name`, `enabled` (default `True`), `expires_at` (nullable). `unique_together = ('user', 'view_name')`. History-tracked.

The default manager (`objects = ViewUserMappingManager()`) overrides `get_queryset()` to annotate four computed booleans on every row:
- `is_user_active` — from `user.is_active`.
- `is_user_system_staff` — true if the user is superuser **or** staff.
- `has_access_role` — `Exists()` subquery against `CourseAccessRole`, matching role scope (global/tenant_only/course_only/tenant_or_course) using `get_allowed_roles(cs.COURSE_ACCESS_ROLES_USER_VIEW_MAPPING)`.
- `usable` — the overall verdict: active **and** (system staff **or** (has access role **and** `enabled` **and** not expired)).

`get_annotated_attribute()` re-fetches the annotated value if missing on the instance. Classmethod `is_usable_access(user, view_name)` is the main entry point used to check access.

### `ClickhouseQuery` (models.py:184)
Stores reusable parameterized Clickhouse SQL queries. Key fields: `scope` (choices: `course`/`platform`/`tenant`/`user`), `slug`, `version`, `description`, `query` (TextField), `params_config` (JSONField), `paginated`, `enabled`, plus `created_at`/`modified_at`. `unique_together = ('scope', 'slug', 'version')`. History-tracked (`HistoricalClickhouseQuery`, migration `0003`).

`save()` calls `clean()` first. `clean()` normalizes/validates the slug (`^[a-z0-9-]+$`), scope, and version, and — when `enabled` — runs `validate_clickhouse_query()`, which requires the SQL to start with `SELECT`, forbids a trailing `;`, builds sample params, and executes a real validation against Clickhouse via `clickhouse_operations`. Param types are restricted to `date/float/int/list_str/str`; built-in params `__orgs_of_tenants__` and `__ca_users_of_tenants__` are auto-injected. Classmethods support seeding defaults: `get_default_query_ids()`, `get_missing_query_ids()`, `load_missing_queries()`, `get_missing_queries_count()`, `get_query_record()`.

### `DataExportTask` (models.py:441)
Tracks asynchronous data/CSV export jobs. Fields: `filename`, `view_name`, `related_id` (nullable), `user` (FK → `User`), `status` (choices `in_queue`/`processing`/`completed`/`failed`, default `in_queue`), `progress` (float), `notes`, **`tenant` (FK → `TenantConfig`, `CASCADE`)**, `created_at`/`started_at`/`completed_at`, `error_message`. Indexed on `(tenant_id, user)` and `(view_name, related_id)`. **Not** history-tracked.

State transitions are enforced via classmethods (`set_status`, `set_progress`, `get_status`, `get_task`); illegal transitions or invalid progress raise `FXCodedException` with codes like `EXPORT_CSV_TASK_CHANGE_STATUS_NOT_POSSIBLE`. `set_status` stamps `started_at`/`completed_at` and forces `progress = 1.0` on completion.

### Config / theme-editor cluster

Four models power the tenant theme editor — `ConfigAccessControl`, `TenantAsset`, `DraftConfig`, and `ConfigMirror`. They are summarized here; their full behavior is documented in the dedicated sections: [Config Access Control](#config-access-control), [Draft & Publish Workflow](#draft--publish-workflow), and [Theme Consumption](#theme-consumption-futurex-theme).

- **`ConfigAccessControl` (models.py:581)** — the whitelist of editable/readable dashboard keys. Fields: `key_name` (unique), `key_type` (choices `string`/`integer`/`boolean`/`dict`/`list`, default `string`), `path` (dot-separated, e.g. `theme_v2.footer.linkedin_url`), `writable` (default `False`). Not history-tracked. See [Config Access Control](#config-access-control).
- **`TenantAsset` (models.py:603)** — per-tenant uploaded files. Fields: **`tenant` (FK → `TenantConfig`, `CASCADE`)**, `slug` (SlugField), `file` (FileField, `upload_to=get_tenant_asset_dir`), `updated_by` (FK → `User`), `updated_at`. `unique_together = ('tenant', 'slug')`. History-tracked (`HistoricalTenantAsset`, migration `0008`). See [Theme Consumption](#theme-consumption-futurex-theme).
- **`DraftConfig` (models.py:620)** — draft (unpublished) tenant config values, one row per dot-separated config path; uses the `NoUpdateQuerySet` manager and per-row `revision_id` tracking. Not history-tracked. See [Draft & Publish Workflow](#draft--publish-workflow).
- **`ConfigMirror` (models.py:895)** — global rules that mirror/copy one config path to another at sync time. History-tracked (`HistoricalConfigMirror`, migration `0010`). Note: it has **no FK to `TenantConfig`** — it holds global rules and operates on a tenant's `lms_configs` dict at sync time. See [Config Access Control](#config-access-control).

### `CourseStat` (models.py:1040)
Cached, fast-read denormalization of downloadable-certificate counts per course. Fields: `course_key` (`CourseKeyField`, unique), `certificate_count_all`, `certificate_count_non_staff`, `last_updated` (`auto_now`). Defines `__str__`. No manager overrides; **not** history-tracked. Added in migration `0011`.

## The Template Tenant

The **template tenant** is a single, special `TenantConfig` row that acts as the source of truth for two things every other tenant inherits or falls back to:

1. The **default theme config** (`lms_configs`) used as the blueprint when a brand-new tenant is created.
2. The **shared asset set** (`TenantAsset` rows — e.g. logos, CSS override files) that any tenant can reference.

It is identified by a configurable site/domain, not by a hardcoded id.

### The setting: `FX_TEMPLATE_TENANT_SITE`

Defined in `common_production.py` and defaults to `template.futurex.sa`:

```python
settings.FX_TEMPLATE_TENANT_SITE = getattr(settings, 'FX_TEMPLATE_TENANT_SITE', 'template.futurex.sa')
```

(`futurex_openedx_extensions/helpers/settings/common_production.py`). Override it in your Open edX settings to point at whichever `TenantConfig` you want to treat as the template.

### How it's resolved — and exposed via `get_all_tenants_info()`

The cached `get_all_tenants_info()` (`helpers/tenants.py`) looks the template tenant up by **`external_key`**:

```python
template_tenant = TenantConfig.objects.get(external_key=settings.FX_TEMPLATE_TENANT_SITE)
```

If it's missing, it does **not** raise — it logs an error and continues with `None`:

```python
logger.error('CONFIGURATION ERROR: Template tenant not found! (%s)', settings.FX_TEMPLATE_TENANT_SITE)
```

When found, it loads that tenant's assets into a `{slug: file.url}` map. The result dict carries a dedicated `template_tenant` block:

```python
'template_tenant': {
    'tenant_id':   template_tenant.id if template_tenant else None,
    'tenant_site': settings.FX_TEMPLATE_TENANT_SITE if template_tenant else None,
    'assets':      template_assets,   # {slug: url} or None
}
```

> Note the two different lookup keys. `get_all_tenants_info()` and the signals match on **`external_key`**, while config-generation and admin validation match on **`route__domain`** (`TenantConfig.objects.get(route__domain=settings.FX_TEMPLATE_TENANT_SITE)`, `helpers/tenants.py`, `helpers/admin.py`). For the template tenant to work end-to-end, its `external_key` *and* its route domain must both equal `FX_TEMPLATE_TENANT_SITE`. This dual-keying is a subtle correctness requirement not documented in the code.

### Role 1 — Default config for NEW tenants

Creating a tenant goes through `ThemeConfigTenantView` (`POST /api/fx/config/v1/tenant/`, `dashboard/views/configs.py`), which calls `create_new_tenant_config(sub_domain, platform_name)`. That in turn calls `generate_tenant_config()`, which **copies the template tenant's `lms_configs`** and substitutes placeholders:

```python
default_config = TenantConfig.objects.get(route__domain=settings.FX_TEMPLATE_TENANT_SITE)
config_lms_dict = json.dumps(default_config.lms_configs)
config_lms_dict = config_lms_dict.replace('{{platform_name}}', platform_name)
config_lms_dict = config_lms_dict.replace('{{sub_domain}}', sub_domain)
```

If the template tenant is absent here, it *does* raise (`FXCodedException(TENANT_NOT_FOUND)`). So the template config defines `{{platform_name}}`/`{{sub_domain}}` placeholders that get filled in per new tenant (`helpers/tenants.py`). Note that the new tenant's own `external_key` is set to the bare `sub_domain` (e.g. `mytenant`), not the full domain — only the template tenant is expected to have `external_key == FX_TEMPLATE_TENANT_SITE`.

### Role 2 — Shared assets / CSS override

`get_fx_theme_css_override()` pulls the override file from the template tenant's asset map, not the current tenant's (`helpers/tenants.py`):

```python
assets = get_all_tenants_info()['template_tenant']['assets'] or {}
return {'css_override_file': assets.get(override_slug, '') ...}
```

So a CSS override uploaded once to the template tenant is served to whichever tenants reference its slug.

### Special access handling (system-staff only)

Normal users can only touch tenants in their `view_allowed_tenant_ids_full_access`. **System-staff users** get the template tenant treated as accessible so they can manage the shared assets/config:

- **Asset listing** — `TenantAssetsManagementView.get_queryset` appends the template tenant id to accessible tenants for staff, and only staff see assets whose slug starts with `_` (`dashboard/views/admin.py`). The underscore convention marks internal/template assets, also enforced in `TenantAssetSerializer.validate_slug` (`dashboard/serializers.py`).
- **Asset upload** — `TenantAssetSerializer.validate_tenant_id` lets a staff user write to the template tenant even though it isn't in their normal access list (`dashboard/serializers.py`).

### Cache invalidation

Because the asset map lives inside the cached `get_all_tenants_info()`, two signal receivers blow away the cache whenever a **template-tenant** asset is saved or deleted (a no-op for other tenants' assets), `helpers/signals.py`:

```python
template_tenant_id = get_all_tenants_info()['template_tenant']['tenant_id']
if template_tenant_id and instance.tenant_id == template_tenant_id:
    invalidate_cache()
```

### Admin path validation

When defining a `ConfigAccessControl` key in Django admin, `ConfigAccessControlForm.clean_path` walks the dotted path against the **template tenant's `lms_configs`** and rejects any path that doesn't exist there (`helpers/admin.py`). This guarantees every configurable/editable theme key actually corresponds to a real field in the default config.

### Why it matters

The template tenant is the central "prototype" for the multi-tenant theming system. New tenants are clones of its config; the editable-key catalog is validated against its config; shared/branding assets (and the CSS override) live on it and are served to others; and it's the one tenant system-staff can edit outside their normal tenant access. **If `FX_TEMPLATE_TENANT_SITE` doesn't resolve to a real `TenantConfig` (matched on both `external_key` and route domain), new-tenant creation breaks, admin key validation fails, and shared assets disappear** — hence the loud `CONFIGURATION ERROR` log. Note that missing-template handling is deliberately inconsistent: `get_all_tenants_info` degrades gracefully (logs, returns `None` ids/assets), while `generate_tenant_config` and the admin form raise hard errors.

## Config Access Control

Tenant theme/configuration lives inside `TenantConfig.lms_configs` — a large, free-form JSON blob (the eox-tenant config). The dashboard must never read or write that blob directly. Instead, a small whitelist table (`ConfigAccessControl`) maps **flat, human-friendly dashboard keys** to **dotted JSON paths** inside `lms_configs`, and marks each as readable-only or writable. Only whitelisted paths are reachable through the config API. A second table (`ConfigMirror`) derives/copies one config value into another so legacy Open edX settings (e.g. `PLATFORM_NAME`) stay in sync with the editable `theme_v2.*` values.

### `ConfigAccessControl` — the whitelist

Defined at `helpers/models.py:581`. Each row is one editable dashboard key:

| Field | Meaning |
|-------|---------|
| `key_name` | Unique flat key the dashboard uses, e.g. `header`, `favicon_url` |
| `key_type` | Declared data type — one of `string`, `integer`, `boolean`, `dict`, `list` (`KEY_TYPE_CHOICES`) |
| `path` | Dot-separated path into `lms_configs`, e.g. `theme_v2.footer.linkedin_url` |
| `writable` | If `False` (default) the key is read-only through the API |

`get_config_access_control()` loads all rows into a `{key_name: {key_type, path, writable}}` dict and is the single source of truth used by every read/write path (`helpers/tenants.py`).

> Note: `key_type` is **stored and exposed** but is *not* enforced on writes — the PUT handler only checks `writable` and that the key name is a string (see Security model below). `key_type` is metadata for the dashboard UI, not server-side value validation.

### `add_config_access` management command — seeding the whitelist

`helpers/management/commands/add_config_access.py` is an idempotent seeder (run `manage.py lms add_config_access`). It `update_or_create`s rows from two static tables inside `transaction.atomic()` blocks.

**`CONFIG_ACCESS_DATA`** — maps each flat key to a path + writable flag. Examples:

- `header` -> `theme_v2.header` (dict, writable) — the whole header object
- `header_combined_login` -> `theme_v2.header.combined_login` (boolean, writable) — a leaf *inside* `header`
- `header_sections` -> `theme_v2.header.sections` (list, writable)
- `footer`, `footer_social_media_links`, `course_categories`, `custom_pages`, `pages.*` (home/about_us/contact_us/terms/courses/custom_page_1..8), `platform_settings`, `visual_identity`, etc. — all under `theme_v2.*`, writable
- `favicon_url` -> `favicon_path`, `logo_image_url` -> `logo_image_url` — top-level `lms_configs` keys (not under `theme_v2`), writable
- `site_domain` -> `SITE_NAME` (string, **`writable: False`**) — the canonical read-only example: the dashboard can read the tenant's site domain but cannot change it through the API

Note that the same subtree is whitelisted at multiple granularities (e.g. both `header` and `header.combined_login`). Reads collapse overlapping paths to their roots so the subtree is only emitted once (`get_tenant_readable_lms_config`, `tenants.py`).

**`CONFIG_MIRROR_DATA`** — seeds three `ConfigMirror` rows (see below).

### `ConfigMirror` — deriving one setting from another

Defined at `helpers/models.py:895`. A mirror copies the value at `source_path` to `destination_path` inside `lms_configs`, ordered by `priority` (higher first; ties broken by `id` ascending — `get_active_records`). Only `enabled=True` rows apply. `clean()` rejects a source/destination where one is a prefix of the other, and `save()` calls `clean()`.

The seeded chain keeps the legacy `PLATFORM_NAME` / `platform_name` settings synced to the editable `theme_v2` platform name:

| priority | source_path | destination_path |
|----------|-------------|------------------|
| 20 | `theme_v2.platform_settings.site_name.en` | `PLATFORM_NAME` |
| 10 | `theme_v2.platform_settings.site_name.ar` | `PLATFORM_NAME` |
| 0 | `PLATFORM_NAME` | `platform_name` |

Because higher priority applies first and later writes overwrite earlier ones, the English name wins; if absent, Arabic; then whatever lands in `PLATFORM_NAME` is copied down to `platform_name`. So editing `theme_v2.platform_settings.site_name.en` in the dashboard automatically propagates to the Open edX `PLATFORM_NAME` and `platform_name` settings on publish. (The seeded mirrors do not set `missing_source_action`, so all three use the `skip` default — a missing source leaves the destination unchanged.)

`sync_tenant(tenant)` iterates active records: if the source exists it deep-copies the value to the destination; if the source is missing it runs the configured `missing_source_action` — `skip` (default, no-op), `set_null`, `delete`, or `copy_dest` (copies destination back into source). It then saves the tenant and invalidates caches. `sync_tenant_by_id` wraps this in a transaction. Mirrors run on **publish** (see below) — `publish_tenant_config` calls `ConfigMirror.sync_tenant` after applying drafts (`tenants.py`).

### The config API surface (`dashboard/views/configs.py`)

All four views require `FXHasTenantAllCoursesAccess` and `staff` / `fx_api_access_global` roles; routes under `api/fx/config/v1/` (`dashboard/urls.py`).

| View | Route | Purpose |
|------|-------|---------|
| `ConfigEditableInfoView` | `GET .../editable/` | Returns `editable_fields` and `read_only_fields` — the whitelisted key names split by `writable` via `get_accessible_config_keys(..., writable_fields_filter=...)` (`tenants.py`) |
| `ThemeConfigRetrieveView` | `GET .../values/` | Reads values for given `keys` (or all accessible keys) via `get_tenant_config`; `published_only=1` skips drafts |
| `ThemeConfigDraftView` | `GET/PUT/DELETE .../draft/<tenant_id>/` | Read/update/clear the draft layer |
| `ThemeConfigPublishView` | `POST .../publish/` | Apply drafts to `lms_configs`, then run mirrors |

**How a path resolves into `lms_configs`:** reads go through `get_tenant_readable_lms_config` (`tenants.py`), which builds the result from *only* the whitelisted `path`s using `dot_separated_path_get_value` (`extractors.py`); anything not whitelisted is never returned. `get_tenant_config` then picks out requested keys, marks unknown keys as `bad_keys`, and (when not `published_only`) overlays draft values via `DraftConfig.loads_into` and attaches per-key `revision_ids` (`tenants.py`). Results are wrapped by `TenantConfigSerializer` (`serializers.py`), which only surfaces `values`, `not_permitted`, `bad_keys`, and stringified `revision_ids`.

**Write path (`PUT .../draft/`)**: the request supplies a flat `key` (plus `new_value` or `reset`, and `current_revision_id`). The handler:
1. Requires `key` to be a `str`.
2. Looks up `ConfigAccessControl.objects.get(key_name=key)`; an unknown key returns 400 `Invalid key ... in config access control`.
3. Rejects the write if `not key_access_info.writable` -> 400 `Config Key: (...) is not writable.`. This is what makes `site_domain` (and any `writable=False` row) read-only.
4. Translates the flat key to its whitelisted `path` and writes into the **draft** layer via `update_draft_tenant_config(config_path=key_access_info.path, ...)` (`tenants.py`) — the live `lms_configs` is untouched until publish.

Drafts use optimistic concurrency: `current_revision_id` must match the stored draft revision, else a `DRAFT_CONFIG_*_MISMATCH` returns HTTP 409. `DELETE` clears all drafts for the tenant. See [Draft & Publish Workflow](#draft--publish-workflow) for the full lifecycle.

**Publish (`POST .../publish/`)**: validates the caller has full access to `tenant_id` and that the supplied `draft_hash` still matches the current draft, then `publish_tenant_config` (`tenants.py`) copies draft paths into `lms_configs`, deletes the drafts, and runs `ConfigMirror.sync_tenant` so derived settings (`PLATFORM_NAME`, `platform_name`) are recomputed. If there are no drafts it still runs the mirror sync.

### Security model summary

- The whitelist is the gate: only paths present in `ConfigAccessControl` are reachable. Reads build their output exclusively from whitelisted paths; the rest of `lms_configs` is never exposed. Writes must resolve a `key_name` row or are rejected.
- `writable=False` keys are read-only end-to-end: they appear in `read_only_fields` / `values` but the PUT handler refuses to draft them. `site_domain -> SITE_NAME` is the seeded read-only example.
- Edits land in a draft layer and only touch live `lms_configs` on an explicit, access-checked, hash-guarded publish — limiting blast radius and giving optimistic-concurrency protection for concurrent editors.
- `ConfigMirror` keeps derived Open edX settings consistent with the editable `theme_v2` source-of-truth values on every publish, so the dashboard only edits the new `theme_v2.*` keys while legacy settings follow automatically.

> Per-user / per-tenant filtering of *which* whitelisted keys are accessible is not yet implemented (`get_accessible_config_keys` ignores `user_id`/`tenant_id`, TODO in `tenants.py`); access is currently gated only by the view-level role/tenant permissions, and all whitelisted keys are returned to any authorized caller.

## Draft & Publish Workflow

Tenant theme/branding configuration is **never edited in place**. Edits are staged in a separate `DraftConfig` table, reviewed against the live values, and only promoted into the live `TenantConfig.lms_configs` JSON by an explicit, hash-guarded publish step. This gives a `draft -> review -> publish` lifecycle with optimistic concurrency control at two levels (per-key `revision_id` and a whole-draft `draft_hash`).

### The data model: `DraftConfig`

A draft is a set of rows, one per edited config path, overlaid on top of the published `TenantConfig.lms_configs`.

| Field | Notes |
|---|---|
| `tenant` (FK → `TenantConfig`) | `unique_together('tenant', 'config_path')` — one draft row per path per tenant |
| `config_path` | Dot-separated path, e.g. `theme_v2.footer.linkedin_url` |
| `config_value` (TextField) | The drafted value, stored as JSON wrapped under a `___root` key (`ROOT = '___root'`) so any JSON type (str/dict/list/null) round-trips safely |
| `revision_id` (BigIntegerField) | Random 63-bit token regenerated on every value change; the per-key optimistic-lock token (the "draft hash" at the row level) |
| `created_at` / `created_by`, `updated_at` / `updated_by` | Audit fields (FKs to `User`) |

Defined in `helpers/models.py:620`. The value is normalized by `get_save_ready_config_value` and unwrapped by `json_load_config_value`. `save()` only bumps `revision_id` when the serialized value actually changes.

**Overlay semantics.** For a given tenant, the published baseline comes from `get_tenant_readable_lms_config` (only paths registered in `ConfigAccessControl`, `tenants.py`). `DraftConfig.loads_into` then writes each non-empty draft path on top of that baseline tree via `dot_separated_path_force_set_value`. Draft rows with `revision_id == 0` or a `None` value are skipped, so a draft cleanly overrides exactly the paths it covers and nothing else.

**`NoUpdateQuerySet` manager.** `DraftConfig.objects = NoUpdateQuerySet.as_manager()`. This queryset (`helpers/model_helpers.py`) makes `.update()` and `.bulk_update()` **raise `AttributeError`** unless the caller first opts in with `.allow_update()`. The intent: those bulk methods bypass `Model.save()`, which is exactly where `revision_id` bumping and `___root` wrapping live, so bypassing it accidentally would corrupt the revision-tracking invariant. The one legitimate bulk update — the conditional `Case/When` update in `DraftConfig.update_from_dict` — explicitly calls `.allow_update()`, and tests catch any unguarded use. (Revision checks are bypassed entirely when `settings.FX_DISABLE_CONFIG_VALIDATIONS` is set.)

The bulk update path, `update_from_dict()`, delegates to `DraftConfigUpdatePreparer` (`model_helpers.py`) to compute a `to_delete`/`to_update`/`to_create` plan with optimistic-concurrency revision checks (`verify_revision_ids`). It then executes delete → conditional `Case/When` update (via `.allow_update()`) → `bulk_create`, all inside `transaction.atomic()`, raising `FXCodedException` (`DRAFT_CONFIG_*_MISMATCH`) if any step's affected-row count doesn't match the plan.

### The two safety tokens

- **`revision_id`** (per key): returned to the client per key, and echoed back as `current_revision_id` on the next draft PUT. The update plan verifies it (`get_update_plan` → `_get_current_revision_id`, `model_helpers.py`); a mismatch means another editor changed that key, and the write fails with a `*_MISMATCH` coded exception surfaced as **HTTP 409** (`views/configs.py`). Guards a single concurrent field edit.
- **`draft_hash`** (whole draft): `SHA-256` of the entire `updated_fields` map (`dict_to_hash`, `converters.py`), computed in `ThemeConfigDraftView.get`. **Its safety role is the publish gate**: the client must read the draft, review it, and send back the exact hash it reviewed. Publish recomputes the hash from the current draft and rejects the request if it differs (`validate_payload`, `views/configs.py`). This prevents publishing a draft that changed (by another editor) between review and publish — i.e. it stops shipping *unreviewed / stale* changes wholesale. Note `dict_to_hash` returns `''` for an empty/None dict, so an empty draft hashes to the empty string.

> The model field is named `revision_id`, not `draft_hash`; there is no field literally called `draft_hash` on `DraftConfig`. The `draft_hash` is computed on the fly from the whole draft, while `revision_id` is the persisted per-row token.

### Lifecycle, step by step

1. **Discover editable keys** — `GET /api/fx/config/v1/editable/` lists writable vs read-only keys (`ConfigEditableInfoView`, `views/configs.py`). Only keys whose `ConfigAccessControl.writable` is true may be drafted.
2. **Stage edits** — `PUT /api/fx/config/v1/draft/<tenant_id>/` for each key. Body: `key`, `new_value`, `current_revision_id` (optimistic lock), or `reset: true`. The view resolves `key → ConfigAccessControl.path`, rejects non-writable keys, then calls `update_draft_tenant_config` (`tenants.py`), which builds the merged draft tree and persists via `DraftConfig.update_from_dict`. It returns the resulting value(s) plus the new `revision_id`. `reset: true` forces `new_value = None`, which removes that key from the draft (reverting it to the published value).
3. **Review** — `GET /api/fx/config/v1/draft/<tenant_id>/` returns `updated_fields` (every drafted key with its `published_value` and `draft_value`, from `get_draft_tenant_config`, `tenants.py`) plus the `draft_hash`. The client/reviewer compares old vs new.
4. **(optional) Preview** — `GET /api/fx/config/v1/values/?published_only=0` renders the tenant config with the draft overlaid (draft-first). Used by theme-preview flows (`get_config_current_request` checks the `theme-preview` cookie, `tenants.py`).
5. **Publish** — `POST /api/fx/config/v1/publish/` with `tenant_id` + the reviewed `draft_hash`. After the hash check, `publish_tenant_config` (`tenants.py`):
   - `select_for_update()` locks the `TenantConfig` row,
   - `DraftConfig.loads_into(...)` overlays all draft paths onto a deep copy of `lms_configs`,
   - saves `tenant.lms_configs` (the drafts are now the published values),
   - `delete_draft_tenant_config(tenant_id)` clears the draft table,
   - `ConfigMirror.sync_tenant(tenant)` runs derived-value mirroring and saves again.
   All inside `transaction.atomic()`. If there are no draft rows, it still runs `ConfigMirror.sync_tenant_by_id` so mirrors stay consistent. Response renames `published_value/draft_value` → `old_value/new_value` (`rename_keys`, `views/configs.py`).
6. **Discard** — `DELETE /api/fx/config/v1/draft/<tenant_id>/` drops all draft rows for the tenant (`delete_draft_tenant_config`, `tenants.py`), abandoning the staged changes without touching published values.

### Publish side effects: ConfigMirror + cache invalidation

`ConfigMirror.sync_tenant` (`helpers/models.py:1008`) copies/derives values between paths (source→destination, with `skip` / `set_null` / `delete` / `copy_dest` handling for missing sources), then `tenant.save()` and invalidates caches: `invalidate_tenant_readable_lms_configs([tenant.id])` (drops the per-tenant readable-config cache key, `caching.py`) and `invalidate_cache()` (clears the global tenant-info / org-filter / view-roles caches, `caching.py`). So a successful publish writes `TenantConfig.lms_configs`, applies mirrors, and flushes the caches that serve the live config — no draft state remains.

> Note: signal receivers in `helpers/signals.py` handle cache busting for `ConfigAccessControl`, `TenantAsset`, etc., but **`DraftConfig` has no signal receiver** — publish-time invalidation is done explicitly inside `ConfigMirror.sync_tenant`, not via signals.

### Endpoint reference

| Method & path | View | Purpose |
|---|---|---|
| `GET /api/fx/config/v1/editable/` | `ConfigEditableInfoView` | List writable / read-only config keys |
| `GET /api/fx/config/v1/draft/<tenant_id>/` | `ThemeConfigDraftView.get` | Per-key `published_value` + `draft_value`, plus `draft_hash` |
| `PUT /api/fx/config/v1/draft/<tenant_id>/` | `ThemeConfigDraftView.put` | Create/update a draft key (or `reset` to published); guarded by `current_revision_id` (→ 409 on conflict) |
| `DELETE /api/fx/config/v1/draft/<tenant_id>/` | `ThemeConfigDraftView.delete` | Discard the entire draft (204) |
| `POST /api/fx/config/v1/publish/` | `ThemeConfigPublishView.post` | Requires `tenant_id` + matching `draft_hash`; promotes drafts into `lms_configs`, deletes drafts, runs ConfigMirror |
| `GET /api/fx/config/v1/values/` | `ThemeConfigRetrieveView.get` | Read values; `published_only=0` (default) = draft-first overlay, `published_only=1` = published only |

URL wiring: `dashboard/urls.py`.

## Theme Consumption (futurex-theme)

The plugin is the **authoring + serving backend** for a multi-tenant Open edX site. The actual rendering of each tenant's site is done by an external Open edX comprehensive theme (referred to here as **futurex-theme**), which reads the effective configuration and assets that this plugin publishes. This section documents the contract between the two: the `theme_v2` config namespace, the read API the theme calls, asset serving, and the preview-before-publish flow.

> `futurex-theme` is **not present in this repository**. Its name and role as the rendering comprehensive theme are inferred from the surrounding mechanism (the values API, asset serving, the preview middleware forcing `indigo`, and `get_fx_theme_css_override`). Likewise `FutureXThemePreviewMiddleware`, `get_fx_theme_css_override`, and `get_fx_dashboard_url` are defined here but not referenced elsewhere in this repo — they are wired up and consumed externally (edx-platform settings and the external theme).

### The `theme_v2` config namespace

All theme-editable settings live under a structured `theme_v2.*` namespace inside each tenant's `TenantConfig.lms_configs` JSON. The mapping of editor-facing key names to dot-separated config paths is seeded by the `add_config_access` management command into the `ConfigAccessControl` table (`helpers/management/commands/add_config_access.py`). Representative keys:

| Editor key | Config path | Type | Writable |
|---|---|---|---|
| `header` | `theme_v2.header` | dict | yes |
| `footer` | `theme_v2.footer` | dict | yes |
| `pages_home`, `pages_about_us`, `pages_courses`, `pages_terms`, `pages_custom_page_1..8` | `theme_v2.pages.*` | dict | yes |
| `platform_settings` | `theme_v2.platform_settings` | dict | yes |
| `visual_identity` | `theme_v2.visual_identity` | dict | yes |
| `custom_pages`, `course_categories` | `theme_v2.custom_pages` / `theme_v2.course_categories` | list/dict | yes |
| `fx_css_override_asset_slug` | `theme_v2.fx_css_override_asset_slug` | string | yes |
| `fx_dev_css_enabled` | `theme_v2.fx_dev_css_enabled` | boolean | yes |
| `logo_image_url`, `favicon_url` | `logo_image_url` / `favicon_path` | string | yes |
| `site_domain` | `SITE_NAME` | string | **no** (read-only) |

A `ConfigAccessControl` row defines `key_name`, `key_type`, `path`, and a `writable` flag (`helpers/models.py`). Only `writable=True` keys can be edited; the draft/write APIs reject non-writable keys (`dashboard/views/configs.py`). See [Config Access Control](#config-access-control).

The same command also seeds `ConfigMirror` rows that **mirror** structured `theme_v2` values into the legacy Open edX config keys the rest of the platform expects — e.g. `theme_v2.platform_settings.site_name.en` → `PLATFORM_NAME` → `platform_name`. Mirrors are applied at publish time.

### The read API: `GET /api/fx/config/v1/values/`

`ThemeConfigRetrieveView` is the endpoint the theme/frontend calls to get the effective config for a tenant (`dashboard/views/configs.py`, routed at `dashboard/urls.py`). Behavior:

- A single tenant id must be supplied (`verify_one_tenant_id_provided`).
- `keys` is an optional comma-separated filter; if omitted, it returns all keys accessible to the user (`get_accessible_config_keys`).
- `published_only` query param: `1` returns only the last published values (used to render the live tenant site); anything else (default `0`) overlays draft values on top of published ones for preview.

The actual value lookup is `get_tenant_config` (`helpers/tenants.py`): it loads the tenant's readable LMS config, and when `published_only=False` it overlays any matching `DraftConfig` rows via `DraftConfig.loads_into`. The response (`TenantConfigSerializer`, `dashboard/serializers.py`) carries `values`, `not_permitted`, `bad_keys`, and `revision_ids` (a per-key draft revision; `"0"` means no draft exists).

### Asset serving (`TenantAsset`) and how config references files

Binary theme assets (logos, favicons, CSS overrides, etc.) are stored as `TenantAsset` rows — `(tenant, slug, file)` with `unique_together = ('tenant', 'slug')` (`helpers/models.py`). Allowed extensions are `.png/.jpeg/.jpg/.ico/.svg/.css` (`helpers/constants.py`). Assets are managed/uploaded via the `tenant_assets` router and `TenantAssetSerializer`, which on upload does `update_or_create` keyed on `(tenant, slug)` so re-uploading a slug replaces the file (`serializers.py`).

Assets are referenced from config **by slug**, not by URL — the indirection lets the file behind a slug change without editing config. Two resolution paths exist:

- **Public serve view:** `TenantAssetServeView` serves `GET /api/fx/assets/v1/serve/<tenant_id>/<filename>` with no auth, intended to sit behind a CDN (`dashboard/views/files.py`). It only serves files under `{FX_DASHBOARD_STORAGE_DIR}/{tenant_id}/{CONFIG_FILES_UPLOAD_DIR}/`, guards against `.`/`..` traversal, and sets `Cache-Control: public, max-age=86400`. `TenantAssetSerializer.get_file_url` reverses this route for the asset's current file.
- **Template (shared/default) assets:** the **template tenant** — the `TenantConfig` whose `external_key == settings.FX_TEMPLATE_TENANT_SITE` (default `template.futurex.sa`) — holds the shared default asset set. `get_all_tenants_info` builds a `template_tenant.assets` dict of `{slug: file.url}` from that tenant's `TenantAsset` rows (`helpers/tenants.py`). Slugs starting with `_` are reserved for system staff. See [The Template Tenant](#the-template-tenant).

`fx_css_override_asset_slug` ties config to an asset: `get_fx_theme_css_override` reads the current request's config (`fx_css_override_asset_slug`, `fx_dev_css_enabled`), looks the slug up in the template tenant's asset map, and returns `{css_override_file, dev_css_enabled}` for the theme to inject a custom CSS override and/or enable a dev-CSS mode (`helpers/tenants.py`). Note `get_config_current_request` itself honors the `theme-preview` cookie when resolving published-vs-draft, so the CSS override respects preview mode too.

> The two asset URL forms differ: `template_tenant.assets` maps `slug -> asset.file.url` (the raw storage URL), whereas `TenantAssetSerializer.get_file_url` returns the reversed `/api/fx/assets/v1/serve/...` route. Both are exposed; which one the theme consumes for a given asset is not fully determinable from this repo.

### eox_theming integration and the preview mechanism

The plugin enables a **preview-before-publish** UX so editors can see draft changes rendered live before publishing.

1. **Arm preview:** `GET /api/fx/redirect/set_theme_preview/` (`SetThemePreviewCookieView`, `dashboard/views/misc.py`, routed at `urls.py`) renders `set_theme_preview.html`, which sets the cookie `theme-preview=yes; path=/` via JS and redirects to `next` (`dashboard/templates/set_theme_preview.html`).
2. **Force a renderable theme:** `FutureXThemePreviewMiddleware` runs **after** `EoxThemeMiddleware`; if the `theme-preview` cookie equals `yes`, it overrides `request.site_theme` with a synthetic `indigo` site theme (`dashboard/middlewares.py`, hardcoding `site_id=1`, theme id `1`, `theme_dir_name='indigo'`). This guarantees a concrete comprehensive theme is active so draft values can be rendered.
3. **Serve draft values:** with the cookie set, `get_config_current_request` resolves `published_only=False`, overlaying drafts (`tenants.py`); the theme calling `/values/` likewise passes `published_only=0` to get the draft overlay.

So preview = `theme-preview` cookie → `indigo` theme forced + draft values served, all without publishing.

### Where the theme editor lives

`get_fx_dashboard_url` builds the NELC dashboard (theme editor) URL for users who are system staff or hold any `CourseAccessRole`, and who have access to the current site's tenant: `{scheme}://{settings.NELC_DASHBOARD_BASE}/{lang}/{tenant_id}` with `lang` `en`/`ar` (`helpers/theme.py`). It returns `None` when prerequisites (site/domain/`NELC_DASHBOARD_BASE`) are missing or the user lacks access. The theme surfaces this link so authorized users can jump to the editor.

### End-to-end flow

1. **Edit (draft):** the NELC dashboard theme editor writes `theme_v2.*` keys via `PUT /api/fx/config/v1/draft/<tenant_id>/`, which validates the key is writable and stores a `DraftConfig` row with optimistic-concurrency `current_revision_id` (`configs.py`). Drafts never touch the live `lms_configs`.
2. **Preview:** the editor arms `set_theme_preview` (cookie) and browses the tenant site; the middleware forces `indigo` and the theme reads `/values/?published_only=0`, so drafts render live without affecting real visitors (`middlewares.py`, `tenants.py`).
3. **Publish:** `POST /api/fx/config/v1/publish/` validates a `draft_hash` against the current draft (concurrency guard), then `publish_tenant_config` folds all `DraftConfig` rows into `TenantConfig.lms_configs`, deletes the drafts, and runs `ConfigMirror.sync_tenant` to propagate mirrored keys like `PLATFORM_NAME` (`configs.py`, `tenants.py`).
4. **Render (live):** for normal visitors (no preview cookie), futurex-theme reads `GET /api/fx/config/v1/values/?published_only=1` to get published `theme_v2` values and resolves asset slugs (template-tenant asset map and/or the `/api/fx/assets/v1/serve/...` CDN-backed view) to render the tenant site.

### How it fits together

The four pillars of the theming system form a single chain:

1. **The template tenant** is the prototype. Its `lms_configs` is cloned (with `{{platform_name}}`/`{{sub_domain}}` substitution) to bootstrap every new tenant, and its `TenantAsset` set is the shared/default asset pool (logos, CSS override) served to others. Every editable key is validated against its config in Django admin.
2. **Config access control** is the gate over each tenant's `lms_configs`. The `ConfigAccessControl` whitelist maps flat editor keys to `theme_v2.*` (and a few legacy) paths and marks each readable or writable, so the dashboard can only touch a curated, safe subset of the blob — never the raw config.
3. **Draft & publish** is the safe write path through that gate. Edits accumulate in `DraftConfig` (guarded by per-key `revision_id` and a whole-draft `draft_hash`), can be previewed live via the `theme-preview` cookie, and only land in `TenantConfig.lms_configs` on an explicit, access-checked, hash-guarded publish — which then runs `ConfigMirror` to keep legacy settings like `PLATFORM_NAME` in sync.
4. **Theme consumption** closes the loop. futurex-theme reads the published values from `GET /api/fx/config/v1/values/?published_only=1`, resolves asset slugs against the template-tenant map or the CDN-backed serve view, and renders the tenant site — while authorized editors jump back into the dashboard via `get_fx_dashboard_url` to start the next draft.

In short: **template tenant (defaults + shared assets) → config access control (what's editable) → draft & publish (how it's safely changed) → theme consumption (how futurex-theme renders the result).**
