from pathlib import Path
from datetime import timedelta
import os
from dotenv import load_dotenv

try:
    from celery.schedules import crontab as celery_crontab
except ImportError:
    celery_crontab = None

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

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
    'apps.vorgaenge',
    'apps.handwerker',
    'apps.massenimport',
    'apps.mitarbeiter',
    'apps.abrechnung_wp',
    'apps.versammlung',
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
    # Bewusst KEIN 'DEFAULT_THROTTLE_CLASSES' — sonst würde jeder bestehende
    # Endpunkt gethrottelt. Nur der neue öffentliche Auftragsbestätigungs-
    # Endpunkt (Phase C) nutzt ScopedRateThrottle mit throttle_scope
    # 'auftrag_token', explizit an der jeweiligen View gesetzt.
    'DEFAULT_THROTTLE_RATES': {
        'auftrag_token': '30/hour',
    },
    # Bewusst KEIN globales 'DEFAULT_PAGINATION_CLASS' — würde die
    # Antwortform ALLER bestehenden Endpunkte ändern (Frontend erwartet
    # dort reine Listen ohne count/results). Pagination nur am neuen
    # Handwerkerauftrags-Dashboard-ViewSet gesetzt.
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
_cors_extra = os.environ.get('CORS_ALLOWED_ORIGINS', '')
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
] + [o.strip() for o in _cors_extra.split(',') if o.strip()]

_csrf_extra = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
] + [o.strip() for o in _csrf_extra.split(',') if o.strip()]

# Anthropic / KI
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
ANTHROPIC_MODEL = os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-4-5')

# ---------------------------------------------------------------------------
# E-Mail (Handwerkerauftrag Phase B, Patrik-Entscheidung)
# ---------------------------------------------------------------------------
# Default: Konsolen-Backend — lokal wird nichts versendet, sondern nur
# protokolliert. Per Env auf SMTP umstellbar (Live-Betrieb).
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'info@demme-immobilien.de')
# Empfangsadresse für den Rechnungsrücklauf von Handwerkern (Hinweis im Mailtext).
RECHNUNG_EMPFANG_EMAIL = os.environ.get('RECHNUNG_EMPFANG_EMAIL', 'rechnungen@demme-immobilien.de')
# Basis-URL des Frontends für Links in E-Mails (z.B. Auftragsbestätigung).
FRONTEND_BASE_URL = os.environ.get('FRONTEND_BASE_URL', 'http://localhost:3000')

# Celery
CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# ---------------------------------------------------------------------------
# Cache (Phase C — Rate-Limiting für die ersten öffentlichen Endpunkte)
# ---------------------------------------------------------------------------
# Ohne diese Konfiguration greift Djangos Default 'LocMemCache' — der ist
# PRO PROZESS/Gunicorn-Worker, DRF-Throttling (das den Cache als Zähler-
# Backend nutzt) wäre damit bei mehreren Workern praktisch wirkungslos.
# Eigener Redis-DB-Index (1), NICHT der Celery-Broker-Index (0) oben —
# getrennte Nutzung, damit z.B. ein 'redis-cli FLUSHDB' auf dem Cache
# niemals die Celery-Queue mit trifft. Env-überschreibbar.
_redis_basis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
_redis_cache_default_url = _redis_basis_url.rsplit('/', 1)[0] + '/1'
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.environ.get('CACHE_REDIS_URL', _redis_cache_default_url),
    }
}

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
    'wkz-ops-taeglich-03uhr': {
        'task': 'buchhaltung.erzeuge_faellige_wkz_ops',
        'schedule': celery_crontab(hour=3, minute=0) if celery_crontab else 86400,
    },
    'auto-hausgeld-pipeline': {
        'task': 'buchhaltung.auto_hausgeld_pipeline',
        'schedule': crontab(hour=2, minute=0),
    },
    'archiviere-alte-pain-dateien': {
        'task': 'buchhaltung.archiviere_alte_pain_dateien',
        'schedule': crontab(day_of_week=1, hour=3, minute=0),
    },
    'vorgaenge-pruefe-wiedervorlagen-taeglich-06uhr': {
        'task': 'vorgaenge.pruefe_wiedervorlagen',
        'schedule': crontab(hour=6, minute=0),
    },
    'handwerker-pruefe-abgelaufene-auftraege-taeglich-07uhr': {
        'task': 'handwerker.pruefe_abgelaufene_auftraege',
        'schedule': crontab(hour=7, minute=0),
    },
}
