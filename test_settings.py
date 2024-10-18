"""
These settings are here to use during tests, because django requires them.

In a real-world use case, apps in this project are installed into other
Django applications, so these settings will not be used.
"""

from os.path import abspath, dirname, join

from test_utils.eox_settings import *


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
    'django.contrib.sessions',
    # 'futurex_openedx_extensions.dashboard',
    'futurex_openedx_extensions.helpers',
    'eox_tenant',
    'common',
    'fake_models',
    'openedx',
    'organizations',
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

FX_CLICKHOUSE_USER = 'dummy_test_user'
FX_CLICKHOUSE_PASSWORD = 'dummy_test_password'

REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_RATES': {
        'fx_anonymous_data_retrieve': '60/minute',
    },
}

LMS_ROOT_URL = 'https://lms.example.com'
CMS_ROOT_URL = 'https://studio.example.com'
LMS_BASE = 'example.com'
