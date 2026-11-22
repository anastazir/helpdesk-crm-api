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
