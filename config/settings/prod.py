"""
Production settings — extends base.py.

Enforces: secure cookies, strict CORS, HSTS, SMTP email.
"""

from .base import *  # noqa: F401, F403

DEBUG = False

# Security hardening
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)  # noqa: F405
SESSION_COOKIE_SECURE = True

# Secure JWT cookies
JWT_COOKIE_SECURE = True
JWT_COOKIE_SAMESITE = env("JWT_COOKIE_SAMESITE", default="Lax")  # noqa: F405
