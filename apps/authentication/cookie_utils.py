"""
Utilities for setting and clearing role-scoped HttpOnly JWT cookies and CSRF cookies.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from rest_framework.response import Response

ROLE_COOKIE_CONFIG = {
    "admin": {
        "access": "admin_access",
        "refresh": "admin_refresh",
        "path": "/api/admin/",
    },
    "teacher": {
        "access": "teacher_access",
        "refresh": "teacher_refresh",
        "path": "/api/teacher/",
    },
    "student": {
        "access": "student_access",
        "refresh": "student_refresh",
        "path": "/api/student/",
    },
}


def get_cookie_config(role: str) -> dict[str, str]:
    config = ROLE_COOKIE_CONFIG.get(role.lower())
    if not config:
        raise ValueError(f"Unknown role for cookie configuration: {role}")
    return config


def set_auth_cookies(
    response: Response,
    role: str,
    access_token: str,
    refresh_token: str,
) -> None:
    """
    Set HttpOnly access and refresh token cookies restricted to the role's URL path.
    Also sets a non-HttpOnly CSRF double-submit cookie so the client can send X-CSRFToken.
    """
    config = get_cookie_config(role)
    path = config["path"]

    access_max_age = int(settings.JWT_ACCESS_TOKEN_LIFETIME.total_seconds())
    refresh_max_age = int(settings.JWT_REFRESH_TOKEN_LIFETIME.total_seconds())
    secure = settings.JWT_COOKIE_SECURE
    samesite = settings.JWT_COOKIE_SAMESITE

    # Access token cookie
    response.set_cookie(
        key=config["access"],
        value=access_token,
        max_age=access_max_age,
        path=path,
        httponly=True,
        secure=secure,
        samesite=samesite,
    )

    # Refresh token cookie
    response.set_cookie(
        key=config["refresh"],
        value=refresh_token,
        max_age=refresh_max_age,
        path=path,
        httponly=True,
        secure=secure,
        samesite=samesite,
    )

    # Non-HttpOnly CSRF double-submit token — role-specific so multi-role
    # sessions in the same browser don't clobber each other's tokens.
    csrf_cookie_name = f"{role}_csrf"
    csrf_token = secrets.token_hex(32)
    response.set_cookie(
        key=csrf_cookie_name,
        value=csrf_token,
        max_age=refresh_max_age,
        path="/",
        httponly=False,
        secure=secure,
        samesite=samesite,
    )


def clear_auth_cookies(response: Response, role: str) -> None:
    """
    Delete this role's access and refresh cookies ONLY.
    Does not touch other role cookies (ensuring multi-role isolation).
    """
    config = get_cookie_config(role)
    path = config["path"]
    samesite = settings.JWT_COOKIE_SAMESITE

    response.delete_cookie(config["access"], path=path, samesite=samesite)
    response.delete_cookie(config["refresh"], path=path, samesite=samesite)
    # Also clear the role-specific CSRF cookie
    response.delete_cookie(f"{role}_csrf", path="/", samesite=samesite)
