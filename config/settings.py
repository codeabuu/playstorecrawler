"""
Django settings for the Play Store competitor-gap tool.

Design notes for this project:
- SQLite is used deliberately: the user asked for no infrastructure.
  Swapping to PostgreSQL later only changes DATABASES (plus psycopg2).
- The scraper is a plain service module, so moving to Celery/Django-Q
  later is a call-site change, not a rewrite.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Safety -------------------------------------------------------------
# Dev-only key. Override via env for anything real.
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-playstore-gap-tool-change-me",
)
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# --- Apps ---------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "apps.apps.StoreCrawlerConfig",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Vite dev server
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Database -----------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {"timeout": 20},
    }
}

# --- Auth ---------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- i18n ---------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Project-specific ---------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PAGINATION_CLASS": None,
    "UNAUTHENTICATED_USER": None,
}

# Play Store locale used for every scrape.
PLAY_LANG = os.environ.get("PLAY_LANG", "en")
PLAY_COUNTRY = os.environ.get("PLAY_COUNTRY", "us")

# Search fan-out: how many raw search hits become similarity candidates.
SEARCH_N_HITS = int(os.environ.get("SEARCH_N_HITS", "30"))
# How many similar apps we surface after ranking.
SIMILAR_MAX_APPS = int(os.environ.get("SIMILAR_MAX_APPS", "8"))
# Minimum cosine similarity (0..1) for a candidate to count as "similar".
SIMILAR_MIN_SCORE = float(os.environ.get("SIMILAR_MIN_SCORE", "0.55"))

# Reviews pulled per app. google-play-scraper paginates internally.
REVIEWS_PER_APP = int(os.environ.get("REVIEWS_PER_APP", "400"))

# Scrape cache TTL in seconds (repeat searches are served from SQLite).
SCRAPE_TTL_SECONDS = int(os.environ.get("SCRAPE_TTL_SECONDS", str(60 * 60 * 12)))

# Politeness: minimum seconds between Play Store HTTP calls.
SCRAPE_MIN_INTERVAL = float(os.environ.get("SCRAPE_MIN_INTERVAL", "1.0"))
SCRAPE_MAX_RETRIES = int(os.environ.get("SCRAPE_MAX_RETRIES", "4"))
SCRAPE_BACKOFF_BASE = float(os.environ.get("SCRAPE_BACKOFF_BASE", "2.0"))

# Embedding model (fastembed / ONNX; no torch).
EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "apps": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
