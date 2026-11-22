import dj_database_url
from decouple import Csv, config
from django.core.exceptions import ImproperlyConfigured

from .base import *

DEBUG = False

ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='localhost,127.0.0.1',
    cast=Csv(),
)
RENDER_EXTERNAL_HOSTNAME = config('RENDER_EXTERNAL_HOSTNAME', default='')
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='',
    cast=Csv(),
)
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='',
    cast=Csv(),
)

DATABASE_URL = config('DATABASE_URL', default='')
if not DATABASE_URL:
    raise ImproperlyConfigured('DATABASE_URL must be set in production.')

DATABASES = {
    'default': dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
    )
}
DATABASES['default']['DISABLE_SERVER_SIDE_CURSORS'] = True

MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

SERVE_LOCAL_MEDIA = config('SERVE_LOCAL_MEDIA', default=False, cast=bool)
S3_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME', default='').strip()
if S3_BUCKET_NAME:
    STORAGES['default'] = {
        'BACKEND': 'storages.backends.s3.S3Storage',
        'OPTIONS': {
            'access_key': config('AWS_ACCESS_KEY_ID', default=None),
            'secret_key': config('AWS_SECRET_ACCESS_KEY', default=None),
            'bucket_name': S3_BUCKET_NAME,
            'endpoint_url': config('AWS_ENDPOINT_URL_S3', default=None),
            'region_name': config('AWS_REGION', default=None),
            'addressing_style': 'path',
            'signature_version': 's3v4',
            'querystring_auth': True,
            'querystring_expire': config(
                'AWS_QUERYSTRING_EXPIRE', default=3600, cast=int
            ),
            'file_overwrite': False,
            'default_acl': None,
        },
    }

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
