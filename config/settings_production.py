"""
Production settings overlay. Activate with:
    DJANGO_SETTINGS_MODULE=config.settings_production

Everything not overridden here falls through to config/settings.py — this
file only tightens what must be tightened for a real deployment, so the two
files can't silently drift apart on things like INSTALLED_APPS or REST_FRAMEWORK.
"""
from .settings import *  # noqa: F401,F403
from .settings import env, BASE_DIR

DEBUG = False

# No default here on purpose — an unset SECRET_KEY must fail loudly in
# production rather than silently falling back to the dev key.
SECRET_KEY = env("SECRET_KEY")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")  # required, no wildcard default in production

# No SQLite fallback in production — DATABASE_URL must point at real Postgres.
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["OPTIONS"] = {"connect_timeout": 10}

# --- Security headers ---
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# --- CORS/CSRF: explicit allowlist only, no wildcard in production ---
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=CORS_ALLOWED_ORIGINS)

# --- Email: real SMTP required in production, no console backend ---
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")

# --- Logging: structured, no DEBUG-level noise, ready to ship to a log
# aggregator by pointing this handler at stdout (12-factor: the platform,
# not Django, owns log routing/rotation) ---
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "format": '{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "celery": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

# --- Static/media in production: whitenoise serves static; media should be
# swapped to S3/GCS-backed storage for a real deployment — flagged explicitly
# rather than left on local disk, which doesn't survive container restarts. ---
if env("MEDIA_STORAGE_BACKEND", default="") == "s3":
    STORAGES["default"] = {"BACKEND": "storages.backends.s3.S3Storage"}
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="")
    AWS_DEFAULT_ACL = None
