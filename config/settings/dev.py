"""
Development settings — extends base.py.

Activates: DEBUG, console email, permissive CORS, Celery eager mode for tests.
"""

from .base import *  # noqa: F401, F403

DEBUG = True

# Allow all origins in dev (credentials still require explicit origin list)
CORS_ALLOW_ALL_ORIGINS = True

# Console email backend:
# NOTE: Check your runserver terminal for the OTP email!
# If you want REAL emails sent during dev, comment out this line:
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Celery runs tasks synchronously in dev
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Insecure cookies in dev
JWT_COOKIE_SECURE = False

# Fallback to LocMemCache if Redis is unreachable in local dev
try:
    import redis
    _r = redis.Redis.from_url(REDIS_URL, socket_connect_timeout=1)
    _r.ping()
except Exception:
    import logging
    logging.getLogger("django").warning(
        "Redis is unreachable on %s; falling back to LocMemCache in dev mode.",
        REDIS_URL,
    )
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "dev-cache",
        },
        "otp": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "dev-otp-cache",
        },
        "courses": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "dev-courses-cache",
        },
    }

# Browsable API renderer in dev
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]