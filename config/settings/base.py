from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'drf_spectacular',
    # Local
    'apps.users',
    'apps.zones',
    'apps.complaints',
    'apps.exports',
    'apps.assistant',
    'apps.whatsapp',
    'seed',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

AUTH_USER_MODEL = 'users.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'core.responses.custom_exception_handler',
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Help Desk CRM API',
    'DESCRIPTION': 'Internal complaint management system API',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'ENUM_NAME_OVERRIDES': {
        'ExportColumnEnum': 'apps.exports.serializers.COLUMN_CHOICES',
        'ComplaintStatusEnum': 'apps.complaints.models.STATUS_CHOICES',
    },
}

CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:5173',
    cast=Csv(),
)

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

OPENROUTER_API_KEY = (
    config('OPEN_ROUTER_API_KEY_DEV', default='')
    or config('OPENROUTER_API_KEY', default='')
)
OPENROUTER_MODEL = config(
    'OPENROUTER_MODEL',
    default='deepseek/deepseek-v4.1-flash-1017',
)
OPENROUTER_BASE_URL = config(
    'OPENROUTER_BASE_URL',
    default='https://openrouter.ai/api/v1',
)
OPENROUTER_TIMEOUT = config('OPENROUTER_TIMEOUT', default=45, cast=int)
OPENROUTER_PROVIDER_SORT = config('OPENROUTER_PROVIDER_SORT', default='price')
OPENROUTER_DATA_COLLECTION = config(
    'OPENROUTER_DATA_COLLECTION',
    default='deny',
)
AI_BRIEFING_ENABLED = config('AI_BRIEFING_ENABLED', default=True, cast=bool)
AI_BRIEFING_MAX_TOKENS = config('AI_BRIEFING_MAX_TOKENS', default=900, cast=int)
AI_BRIEFING_TEMPERATURE = config(
    'AI_BRIEFING_TEMPERATURE',
    default=0.2,
    cast=float,
)
AI_BRIEFING_REASONING_EFFORT = config(
    'AI_BRIEFING_REASONING_EFFORT',
    default='none',
)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {name} — {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'apps': {'handlers': ['console'], 'level': 'DEBUG', 'propagate': False},
        'core': {'handlers': ['console'], 'level': 'DEBUG', 'propagate': False},
    },
    'root': {'handlers': ['console'], 'level': 'WARNING'},
}

AI_CHAT_MAX_TOKENS = config('AI_CHAT_MAX_TOKENS', default=1200, cast=int)
AI_CHAT_REASONING_EFFORT = config(
    'AI_CHAT_REASONING_EFFORT',
    default='none',
)
AI_COPILOT_MAX_TOKENS = config('AI_COPILOT_MAX_TOKENS', default=700, cast=int)
AI_PLAN_MAX_TOKENS = config('AI_PLAN_MAX_TOKENS', default=700, cast=int)
AI_TRIAGE_MAX_TOKENS = config('AI_TRIAGE_MAX_TOKENS', default=500, cast=int)

USD_TO_INR_RATE = config('USD_TO_INR_RATE', default=88.0, cast=float)


ANALYTICS_ENABLED = config('ANALYTICS_ENABLED', default=True, cast=bool)
ANALYTICS_DATABASE_URL = config('ANALYTICS_DATABASE_URL', default='')
ANALYTICS_QUERY_TIMEOUT_MS = config(
    'ANALYTICS_QUERY_TIMEOUT_MS',
    default=8000,
    cast=int,
)
ANALYTICS_MAX_ROWS = config('ANALYTICS_MAX_ROWS', default=1000, cast=int)
AI_ANALYTICS_MAX_TOKENS = config(
    'AI_ANALYTICS_MAX_TOKENS',
    default=1200,
    cast=int,
)
AI_ANALYTICS_REASONING_EFFORT = config(
    'AI_ANALYTICS_REASONING_EFFORT',
    default='none',
)


GEOCODE_BASE_URL = config(
    'GEOCODE_BASE_URL',
    default='https://nominatim.openstreetmap.org',
)
GEOCODE_USER_AGENT = config(
    'GEOCODE_USER_AGENT',
    default='HelpDeskCRM/1.0 (+https://localhost)',
)
GEOCODE_TIMEOUT = config('GEOCODE_TIMEOUT', default=12, cast=int)
GEOCODE_CACHE_DAYS = config('GEOCODE_CACHE_DAYS', default=30, cast=int)
GEOCODE_AI_ENABLED = config('GEOCODE_AI_ENABLED', default=True, cast=bool)

WHATSAPP_ENABLED = config('WHATSAPP_ENABLED', default=False, cast=bool)
USE_WHATSAPP = config('USE_WHATSAPP', default=True, cast=bool)
WHATSAPP_GRAPH_VERSION = config('WHATSAPP_GRAPH_VERSION', default='v23.0')
WHATSAPP_PHONE_NUMBER_ID = config('WHATSAPP_PHONE_ID', default='')
WHATSAPP_BUSINESS_ACCOUNT_ID = config('WHATSAPP_ACCOUNT_ID', default='')
WHATSAPP_ACCESS_TOKEN = config('WHATSAPP_ACCESS_TOKEN', default='')
WHATSAPP_APP_SECRET = config('WHATSAPP_APP_SECRET', default='')
WHATSAPP_VERIFY_TOKEN = config('WHATSAPP_VERIFY_TOKEN', default='')
WHATSAPP_TEMPLATE_ASSIGNED = config(
    'WHATSAPP_TEMPLATE_ASSIGNED',
    default='complaint_assigned_engineer',
)
WHATSAPP_TEMPLATE_LANGUAGE = config(
    'WHATSAPP_TEMPLATE_LANGUAGE',
    default='en_US',
)
WHATSAPP_DEFAULT_COUNTRY_CODE = config(
    'WHATSAPP_DEFAULT_COUNTRY_CODE',
    default='91',
)
WHATSAPP_REQUEST_TIMEOUT = config('WHATSAPP_REQUEST_TIMEOUT', default=10, cast=int)
WHATSAPP_SEND_SYNC = config('WHATSAPP_SEND_SYNC', default=True, cast=bool)

AI_FEATURES_ENABLED = config('AI_FEATURES_ENABLED', default=True, cast=bool)
