"""Django settings for the Leash wallet-control app.

Secrets come from leash_app/.env (never committed). Every Jev / Leash API
knob lives here so the apps stay free of hard-coded values.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-not-secret")
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "wallet",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]

ROOT_URLCONF = "leash.urls"
WSGI_APPLICATION = "leash.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Zurich"
USE_TZ = True
STATIC_URL = "static/"

# --- Jev (TypeSafe System One) -------------------------------------------
TYPESAFE_API_KEY = os.getenv("TYPESAFE_API_KEY", "")
TYPESAFE_BASE_URL = os.getenv("TYPESAFE_BASE_URL", "https://api.typesafe.ai")
JEV_MODEL = os.getenv("JEV_MODEL", "jev-latest")
JEV_TIMEOUT_SECONDS = float(os.getenv("JEV_TIMEOUT_SECONDS", "3.0"))

# --- Handler ---------------------------------------------------------------
# Below this top probability the Handler reports review_needed instead of the argmax label.
REVIEW_FLOOR = float(os.getenv("REVIEW_FLOOR", "0.5"))
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "20"))

# --- Viseca Leash sandbox --------------------------------------------------
LEASH_BASE_URL = os.getenv(
    "LEASH_BASE_URL",
    "https://saw26api.ashyground-364e1d07.switzerlandnorth.azurecontainerapps.io",
)
TEAM_API_KEY = os.getenv("TEAM_API_KEY", "")

# Read-only challenge data pack (never written to).
DATA_DIR = Path(os.getenv("LEASH_DATA_DIR", BASE_DIR.parent / "viseca-2026" / "data"))
