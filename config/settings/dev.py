"""
Development settings — extends base.py.

Activates: DEBUG, console email, permissive CORS, Celery eager mode for tests.
"""

from .base import *  # noqa: F401, F403

DEBUG = True

# Allow all origins in dev (credentials still require explicit origin list)
CORS_ALLOW_ALL_ORIGINS = True

# Console email backend (no real SMTP in dev)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Celery runs tasks synchronously in dev (override in test conftest if needed)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

try:
    from config.celery import app as celery_app
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
    )
except Exception:
    pass

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
