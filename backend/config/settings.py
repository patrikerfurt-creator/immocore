from pathlib import Path
from datetime import timedelta
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-change-me-in-production')

DEBUG = os.environ.get('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.postgres',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
]

LOCAL_APPS = [
    'apps.objekte',
    'apps.personen',
    'apps.konten',
    'apps.buchhaltung',
    'apps.rechnungen',
    'apps.prozesse',
    'apps.dokumente',
    'apps.tickets',
    'apps.massenimport',
    'apps.mitarbeiter',
    'apps.abrechnung_wp',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
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
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'immocore'),
        'USER': os.environ.get('DB_USER', 'immocore'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'immocore'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'de-de'
TIME_ZONE = 'Europe/Berlin'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}

# Simple JWT
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# CORS
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
]

CSRF_TRUSTED_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

# Anthropic / KI
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
ANTHROPIC_MODEL = os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-4-5')

# Celery
CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# Vier-Augen-Prinzip für Hausgeld-Sollstellungsläufe.
# Auf False setzen wenn nur ein Benutzer aktiv ist (Demo/Einzelbetrieb).
HAUSGELD_VIER_AUGEN_PFLICHT = os.environ.get('HAUSGELD_VIER_AUGEN_PFLICHT', 'False') == 'True'

# ---------------------------------------------------------------------------
# Auto-Pipeline Hausgeld-Sollstellung & SEPA-Lastschrift
# ---------------------------------------------------------------------------
# Master-Switch: auf 'false' setzen zum Deaktivieren (Notausschalter)
SEPA_AUTOPILOT_AKTIV = os.environ.get('SEPA_AUTOPILOT_AKTIV', 'true').lower() == 'true'
# Tag im Monat, an dem die Pipeline läuft (25 = genug Puffer für SEPA-Frist RCUR)
SEPA_AUTOPILOT_STICHTAG = int(os.environ.get('SEPA_AUTOPILOT_STICHTAG', '25'))
# Ablageordner für erzeugte pain.008-Dateien (UNC-Pfad wird unterstützt)
SEPA_OUTPUT_DIR = os.environ.get('SEPA_OUTPUT_DIR', str(BASE_DIR / 'sepa_output'))
SEPA_OUTPUT_ARCHIVE_DIR = os.environ.get('SEPA_OUTPUT_ARCHIVE_DIR', str(BASE_DIR / 'sepa_archive'))
# Vorlauf in Bankarbeitstagen vor Fälligkeit (RCUR-Mindest: 2 BD; empfohlen: 5)
SEPA_AUTOPILOT_VORLAUF_BD = int(os.environ.get('SEPA_AUTOPILOT_VORLAUF_BD', '5'))

# ---------------------------------------------------------------------------
# Wirtschaftsplan-Beschluss — Hausgeld-Import Feature-Flag
# ---------------------------------------------------------------------------
# Vor Go-Live: True (Massenimport darf quelle='import' setzen).
# Nach Initialimport: Admin schaltet auf False.
HAUSGELD_IMPORT_QUELLE_ERLAUBT = os.environ.get('HAUSGELD_IMPORT_QUELLE_ERLAUBT', 'True') == 'True'

from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    'camt-ordner-scan-alle-2h': {
        'task': 'buchhaltung.camt_ordner_scan',
        'schedule': 7200,
    },
    'rechnungen-ordner-scan-alle-5min': {
        'task': 'rechnungen.ordner_scan',
        'schedule': 300,
    },
    'dokumente-ordner-scan-alle-5min': {
        'task': 'dokumente.ordner_scan',
        'schedule': 300,
    },
    'auto-hausgeld-pipeline': {
        'task': 'buchhaltung.auto_hausgeld_pipeline',
        'schedule': crontab(hour=2, minute=0),
    },
    'archiviere-alte-pain-dateien': {
        'task': 'buchhaltung.archiviere_alte_pain_dateien',
        'schedule': crontab(day_of_week=1, hour=3, minute=0),
    },
}
