"""
Django base settings for the LMS project.

All environment-specific values are read via django-environ.
See .env.example for the full list of variables.
"""

from datetime import timedelta
from pathlib import Path

import environ

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Core Django
# ---------------------------------------------------------------------------
SECRET_KEY: str = env("DJANGO_SECRET_KEY")
DEBUG = False  # overridden in dev.py

ALLOWED_HOSTS: list[str] = env.list("DJANGO_ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS: list[str] = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# ---------------------------------------------------------------------------
# Installed apps
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "corsheaders",
    "drf_spectacular",
    # Local
    "apps.accounts",
    "apps.authentication",
    "apps.core",
    "apps.courses",
]

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    # CsrfViewMiddleware protects the Django admin (session-based).
    # API endpoints use DRF's APIView which applies @csrf_exempt; our custom
    # cookie-auth classes enforce a double-submit CSRF check independently.
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# ---------------------------------------------------------------------------
# URL configuration
# ---------------------------------------------------------------------------
ROOT_URLCONF = "config.urls"

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# WSGI / ASGI
# ---------------------------------------------------------------------------
WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Database — PostgreSQL
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", default="localhost"),
        "PORT": env.int("POSTGRES_PORT", default=5432),
    },
    "mongodb": {
        "ENGINE": "django_mongodb_backend",
        "NAME": env("MONGODB_NAME", default="lms"),
        "CLIENT": {
            "host": env(
                "MONGODB_URI",
                default="mongodb://localhost:27017/?replicaSet=rs0",
            ),
        },
        "TEST": {
            "NAME": env("MONGODB_TEST_NAME", default="lms_test_mongo"),
        },
    },
}

DATABASE_ROUTERS = ["config.db_router.CourseRouter"]

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------
REDIS_URL: str = env("REDIS_URL", default="redis://localhost:6379")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"{REDIS_URL}/0",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    },
    # DB 4 — course list / detail / outline cache
    "courses": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"{REDIS_URL}/4",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    },
}

# OTP / rate-limit Redis connection (DB 1)
OTP_REDIS_URL: str = f"{REDIS_URL}/1"

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL: str = f"{REDIS_URL}/2"
CELERY_RESULT_BACKEND: str = f"{REDIS_URL}/3"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = False

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "otp_email": env("THROTTLE_OTP_EMAIL", default="5/hour"),
        "otp_ip": env("THROTTLE_OTP_IP", default="10/hour"),
        "login_email": env("THROTTLE_LOGIN_EMAIL", default="10/hour"),
        "login_ip": env("THROTTLE_LOGIN_IP", default="20/hour"),
    },
}

# ---------------------------------------------------------------------------
# JWT — per-role signing keys & lifetimes
# ---------------------------------------------------------------------------
JWT_SIGNING_KEYS: dict[str, str] = {
    "admin": env("JWT_SIGNING_KEY_ADMIN", default=SECRET_KEY + "-admin"),
    "teacher": env("JWT_SIGNING_KEY_TEACHER", default=SECRET_KEY + "-teacher"),
    "student": env("JWT_SIGNING_KEY_STUDENT", default=SECRET_KEY + "-student"),
}

JWT_ACCESS_TOKEN_LIFETIME: timedelta = timedelta(
    minutes=env.int("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=15),
)
JWT_REFRESH_TOKEN_LIFETIME: timedelta = timedelta(
    days=env.int("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=7),
)
JWT_ALGORITHM = "HS256"
JWT_COOKIE_SECURE: bool = env.bool("JWT_COOKIE_SECURE", default=False)
JWT_COOKIE_SAMESITE: str = env("JWT_COOKIE_SAMESITE", default="Lax")

# ---------------------------------------------------------------------------
# OTP
# ---------------------------------------------------------------------------
OTP_HMAC_SECRET: str = env("OTP_HMAC_SECRET", default=SECRET_KEY)
OTP_LENGTH: int = env.int("OTP_LENGTH", default=6)
OTP_TTL: int = env.int("OTP_TTL", default=300)
OTP_MAX_ATTEMPTS: int = env.int("OTP_MAX_ATTEMPTS", default=5)
OTP_RESEND_COOLDOWN: int = env.int("OTP_RESEND_COOLDOWN", default=60)

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND: str = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST: str = env("EMAIL_HOST", default="")
EMAIL_PORT: int = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER: str = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD: str = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS: bool = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL: str = env("DEFAULT_FROM_EMAIL", default="noreply@lms.local")

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS: list[str] = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# drf-spectacular (OpenAPI)
# ---------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "LMS API",
    "DESCRIPTION": "Learning Management System — Authentication, User Management & Courses API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/",
    "TAGS": [
        {"name": "Admin Auth", "description": "Admin authentication (2-step OTP login)"},
        {"name": "Admin Teachers", "description": "Teacher approval management"},
        {"name": "Admin Users", "description": "Admin user management (search, filter, activate, deactivate, soft-delete, resend verification)"},
        {"name": "Admin Courses", "description": "Admin course management (all statuses)"},
        {"name": "Teacher Auth", "description": "Teacher authentication endpoints"},
        {"name": "Teacher Courses", "description": "Teacher course authoring (own courses only)"},
        {"name": "Student Auth", "description": "Student authentication endpoints"},
        {"name": "Student Courses", "description": "Student course discovery (published only)"},
        {"name": "Dashboard", "description": "Protected ping endpoints (permission proof)"},
        {"name": "Health", "description": "Service health & connectivity checks"},
    ],
    "SECURITY": [],
    "COMPONENT_SPLIT_REQUEST": True,
}

# ---------------------------------------------------------------------------
# Frontend / CSRF
# ---------------------------------------------------------------------------
FRONTEND_ORIGIN: str = env("FRONTEND_ORIGIN", default="http://localhost:3000")
FRONTEND_BASE_URL: str = env("FRONTEND_BASE_URL", default="http://localhost:5173")

# ---------------------------------------------------------------------------
# User-state cache TTL (seconds) — auth classes cache is_active / status
# ---------------------------------------------------------------------------
USER_STATE_CACHE_TTL: int = env.int("USER_STATE_CACHE_TTL", default=15)
