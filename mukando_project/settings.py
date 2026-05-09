"""
Django settings for Mukando — Production-ready configuration
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env locally — on Railway env vars are injected directly
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / '.env')
except Exception:
    pass
# ── Security ──────────────────────────────────────────
SECRET_KEY = os.environ.get('SECRET_KEY', 'fallback-insecure-key-change-in-production')

DEBUG = os.environ.get('DEBUG', 'False') == 'True'

_raw_hosts = os.environ.get('ALLOWED_HOSTS', '.up.railway.app,localhost,127.0.0.1')

# ── Apps ──────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'rounds',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'mukando_project.urls'
AUTH_USER_MODEL = 'rounds.User'
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'],
    'APP_DIRS': True,
    'OPTIONS': {
        'context_processors': [
            'django.template.context_processors.debug',
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages',
        ],
    },
}]

WSGI_APPLICATION = 'mukando_project.wsgi.application'

# ── Database ──────────────────────────────────────────
# SQLite: perfectly appropriate for small-to-medium Mukando deployments.
# Switch to PostgreSQL only when you need multi-process write concurrency
# (e.g. multiple gunicorn workers on separate machines).
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
# Production PostgreSQL (uncomment and set env vars):
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': os.environ.get('DB_NAME', 'mukando'),
#         'USER': os.environ.get('DB_USER', 'mukando_user'),
#         'PASSWORD': os.environ.get('DB_PASSWORD', ''),
#         'HOST': os.environ.get('DB_HOST', 'localhost'),
#         'PORT': os.environ.get('DB_PORT', '5432'),
#         'CONN_MAX_AGE': 60,
#     }
# }

# ── REST Framework ────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.TokenAuthentication',   # kept for legacy API clients
        'rest_framework.authentication.SessionAuthentication', # kept for template views
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    # ── Rate limiting ────────────────────────────────────
    # Applied globally; the AI chat endpoint overrides with a tighter limit.
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'user': '200/hour',        # general API calls
        'anon': '30/hour',         # unauthenticated (register/login)
    },
}

# ── SimpleJWT ─────────────────────────────────────────────────────────
from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':     timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME':    timedelta(days=7),
    'ROTATE_REFRESH_TOKENS':     True,
    'BLACKLIST_AFTER_ROTATION':  True,
    'AUTH_HEADER_TYPES':         ('Bearer',),
    'UPDATE_LAST_LOGIN':         True,
}

# ── Internationalisation ──────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Harare'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# ── Static & Media ────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = []
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ── CORS ──────────────────────────────────────────────
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = os.environ.get('CORS_ALLOWED_ORIGINS', '').split(',') if not DEBUG else []

# ── Email ─────────────────────────────────────────────
EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend'
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.sendgrid.net')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', 'apikey')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@mukando.app')

# ── AI Chat (Anthropic) ──────────────────────────────
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

# ── Africa's Talking (SMS & WhatsApp) ────────────────
AT_USERNAME = os.environ.get('AT_USERNAME', '')
AT_API_KEY = os.environ.get('AT_API_KEY', '')

# ── PayNow Zimbabwe ───────────────────────────────────
# Set via environment variables — never hard-code live credentials.
# Register at: https://www.paynow.co.zw/account/integration/browse
PAYNOW_INTEGRATION_ID  = os.environ.get('PAYNOW_INTEGRATION_ID', '')
PAYNOW_INTEGRATION_KEY = os.environ.get('PAYNOW_INTEGRATION_KEY', '')
PAYNOW_TEST_MODE = os.environ.get('PAYNOW_TEST_MODE', 'True') == 'True'

# ── Security headers (production) ────────────────────
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# ── Logging ───────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'rounds': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}
