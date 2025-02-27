"""
These settings are here to use during tests, because django requires them.

In a real-world use case, apps in this project are installed into other
Django applications, so these settings will not be used.
"""

from os.path import abspath, dirname, join


def root(*args):
    """
    Get the absolute path of the given path relative to the project root.
    """
    return join(abspath(dirname(__file__)), *args)


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'default.db',
        'USER': '',
        'PASSWORD': '',
        'HOST': '',
        'PORT': '',
    }
}

INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.messages',
    'django.contrib.sites',
    'django.contrib.sessions',
    'futurex_openedx_extensions.helpers',
    'eox_tenant',
    'common',
    'fake_models',
    'openedx',
    'organizations',
    'social_django',
)

USE_TZ = True

LOCALE_PATHS = [
    root('futurex_openedx_extensions', 'conf', 'locale'),
]

SECRET_KEY = 'insecure-secret-key'

ROOT_URLCONF = 'tests.test_urls'

MIDDLEWARE = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
)

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'APP_DIRS': False,
    'OPTIONS': {
        'context_processors': [
            'django.contrib.auth.context_processors.auth',  # this is required for admin
            'django.template.context_processors.request',
            'django.contrib.messages.context_processors.messages',  # this is required for admin
        ],
    },
}]

# Avoid warnings about migrations
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

USERNAME_PATTERN = r'(?P<username>[\w.@+-]+)'

# Ensure that the cache is volatile in tests
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# Non-default dashboard settings
FX_CACHE_TIMEOUT_COURSE_ACCESS_ROLES = 60 * 31  # 31 minutes
FX_CACHE_TIMEOUT_TENANTS_INFO = 60 * 60 * 3  # 3 hours
FX_CACHE_TIMEOUT_VIEW_ROLES = 60 * 31  # 31 minutes
FX_TASK_MINUTES_LIMIT = 6  # 6 minutes
FX_MAX_PERIOD_CHUNKS_MAP = {
    'day': 365 * 2,
    'month': 12 * 2,
    'quarter': 4 * 2,
    'year': 1 * 2,
}

FX_CLICKHOUSE_USER = 'dummy_test_user'
FX_CLICKHOUSE_PASSWORD = 'dummy_test_password'

REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_RATES': {
        'fx_anonymous_data_retrieve': '60/minute',
    },
}

LMS_ROOT_URL = 'https://lms.example.com'
CMS_ROOT_URL = 'https://studio.example.com'
NELC_DASHBOARD_BASE = 'dashboard.example.com'

FX_DASHBOARD_STORAGE_DIR = 'test_dir'

FX_DEFAULT_COURSE_EFFORT = 20

FX_SSO_INFO = {
    'testing_entity_id1': {
        'external_id_field': 'test_uid',
        'external_id_extractor': lambda value: (
            value[0] if isinstance(value, list) and len(value) == 1 else '' if isinstance(value, list) else value
        )
    },
    'testing_entity_id2': {
        'external_id_field': 'test_uid2',
        'external_id_extractor': lambda value: value,
    },
}

FX_DEFAULT_TENANT_SITE = 'default.example.com'
FX_TENANTS_BASE_DOMAIN = 'local.overhang.io'
