"""
Django settings for the Dr Rashel Jo rebuild.

Database: SQLite by default for local dev/tests. Set DATABASE_URL to switch to
Postgres in staging/production (see README) without touching this file again.
"""
import os
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DEBUG=(bool, True))
if (BASE_DIR / ".env").exists():
    environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-secret-key-change-in-production")
DEBUG = env("DEBUG", default=True)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"])

INSTALLED_APPS = [
    "unfold",  # must precede django.contrib.admin — themes the built-in admin
    "unfold.contrib.filters",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "django_filters",
    "corsheaders",
    "accounts",
    "catalog",
    "cart",
    "orders",
    "wishlist",
    "reviews",
    "promotions",
    "shipping",
    "payments",
    "notify",
    "content",
    "admin_reports",
    "admin_api",
    "storefront",  # parallel Django-templates frontend (see README); does not affect the React app or /admin/
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        # Explicit loaders (not APP_DIRS) so the cached.Loader can wrap them even
        # in DEBUG — the storefront's product cards nest ~6 {% include %}s each and
        # a 24-card grid re-compiling every partial per request is ~1.5s of pure
        # template parsing. Cached compiles each partial once.
        "OPTIONS": {
            "loaders": [
                (
                    "django.template.loaders.cached.Loader",
                    [
                        "django.template.loaders.filesystem.Loader",
                        "django.template.loaders.app_directories.Loader",
                    ],
                ),
            ],
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "storefront.context.storefront",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Bilingual: English + Arabic, matching the storefront's /:lang/ routing.
LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", "English"),
    ("ar", "Arabic"),
]
TIME_ZONE = "Asia/Amman"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Prod: whitenoise's hashed+compressed manifest storage. Dev: plain storage so
    # `{% static %}` returns unhashed paths that `runserver` serves straight from
    # the finders — no `collectstatic` needed to iterate, and no stale-manifest
    # surprises for the storefront or the /admin/ theme.
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.AllowAny",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 24,
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=14),
    "ROTATE_REFRESH_TOKENS": True,
}

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS", default=["http://localhost:5173"]
)

CURRENCY_CODE = "JOD"
CURRENCY_SYMBOL_AR = "د.أ"

# Public origin of the storefront — used for absolute URLs in sitemap.xml and
# robots.txt. Override per environment (no trailing slash).
SITE_URL = env("SITE_URL", default="https://dr-rasheljo.com").rstrip("/")
SITE_LANGS = ["en", "ar"]

# --- Celery / Redis ---
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)

CELERY_BEAT_SCHEDULE = {
    "cart-abandonment-reminder": {
        "task": "notify.tasks.cart_abandonment_reminder",
        "schedule": 3600.0,  # hourly
    },
}

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}

# --- Email ------------------------------------------------------------------
# Every EMAIL_* value is read HERE (not only in settings_production) so outbound
# mail — password-reset links especially — works no matter which settings module
# is active on the host. Real SMTP is used automatically whenever it's configured
# (EMAIL_HOST set) or whenever DEBUG is off; the console backend is only a
# local-dev convenience so you don't need a mail server to click around.
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=15)  # never let a dead SMTP host hang a worker

_default_email_backend = (
    "django.core.mail.backends.smtp.EmailBackend"
    if (EMAIL_HOST or not DEBUG)
    else "django.core.mail.backends.console.EmailBackend"
)
EMAIL_BACKEND = env("EMAIL_BACKEND", default=_default_email_backend)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Dr Rashel Jo <no-reply@dr-rasheljo.com>")
SERVER_EMAIL = env("SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)

# Behind Render's TLS-terminating proxy: trust X-Forwarded-Proto so
# request.build_absolute_uri() (the storefront password-reset link) emits https://.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# --- Logging ---
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "[{asctime}] {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}


# --- Django admin theme (django-unfold) ---------------------------------------
# Brands the built-in /admin/ to match the storefront (terracotta primary from
# frontend/src/index.css `--color-brand-primary` #B0472E). Layers on top of the
# existing ModelAdmin classes — no behaviour changes.

def _admin_site_logo(request):
    """Use the uploaded storefront logo (content.SiteSettings.logo) if one is set,
    otherwise unfold falls back to the SITE_HEADER text."""
    try:
        from content.models import SiteSettings

        settings_row = SiteSettings.load()
        return settings_row.logo.url if settings_row.logo else None
    except Exception:
        return None


UNFOLD = {
    "SITE_TITLE": "Dr Rashel Jo Admin",
    "SITE_HEADER": "Dr Rashel Jo",
    "SITE_SUBHEADER": "Store administration",
    "SITE_URL": "/",
    "SITE_SYMBOL": "spa",
    "SITE_LOGO": _admin_site_logo,
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "THEME": None,  # None = respect the OS/browser preference + expose the toggle
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
    },
    "COLORS": {
        "primary": {
            "50": "251 243 240",
            "100": "246 225 219",
            "200": "237 195 182",
            "300": "224 158 137",
            "400": "205 112 89",
            "500": "176 71 46",
            "600": "152 61 39",
            "700": "124 50 32",
            "800": "100 41 27",
            "900": "79 34 22",
            "950": "44 17 11",
        },
    },
}
