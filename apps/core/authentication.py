"""
Role-specific JWT Cookie Authentication classes.

Performs:
1. Role-specific cookie extraction (with Bearer header fallback for APIs/tests)
2. Decryption using role-isolated HMAC signing key
3. Claim verification: role, token_type, jti blacklist, tokens_valid_after timestamp
4. 15-second Redis user-state cache to avoid repetitive DB hits
5. Double-submit CSRF cookie enforcement on unsafe methods
"""

from __future__ import annotations

import hmac
import uuid
from typing import Any

import jwt
from django.conf import settings
from django.core.cache import cache
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication
from rest_framework.request import Request

from apps.accounts.models import User
from apps.core.utils import (
    get_user_state_cache_key,
    is_token_invalidated_by_timestamp,
    is_token_jti_blacklisted,
)


class BaseJWTCookieAuthentication(BaseAuthentication):
    """
    Abstract base class for role-isolated JWT cookie authentication.
    Subclasses define `role`, `cookie_name`, and `refresh_cookie_name`.
    """

    role: str = ""
    cookie_name: str = ""
    refresh_cookie_name: str = ""

    def authenticate(self, request: Request) -> tuple[User, dict[str, Any]] | None:
        raw_token, is_cookie = self._extract_token(request)
        if not raw_token:
            return None

        payload = self._decode_and_validate_token(raw_token)

        # Enforce double-submit CSRF check for cookie-authenticated unsafe requests
        if is_cookie and request.method not in ("GET", "HEAD", "OPTIONS", "TRACE"):
            self._enforce_csrf(request)

        user = self._get_user(payload)

        # Attach request metadata
        request.auth_role = self.role
        request.auth_scope = payload.get("scope", "full")
        request.auth_token_payload = payload

        return user, payload

    def _extract_token(self, request: Request) -> tuple[str | None, bool]:
        """
        Extract token from role-specific cookie first.
        Falls back to Authorization: Bearer <token> header for convenience in testing.
        Returns (raw_token, is_cookie_source).
        """
        token = request.COOKIES.get(self.cookie_name)
        if token:
            return token, True

        # Fallback to Authorization header
        auth_header = request.headers.get("Authorization") or request.META.get(
            "HTTP_AUTHORIZATION"
        )
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header.split(" ", 1)[1].strip(), False

        return None, False

    def _decode_and_validate_token(self, raw_token: str) -> dict[str, Any]:
        """Decode token using the role-specific signing key and validate all claims."""
        key = settings.JWT_SIGNING_KEYS.get(self.role)
        if not key:
            raise exceptions.AuthenticationFailed("JWT signing key not configured for role.")

        try:
            payload: dict[str, Any] = jwt.decode(
                raw_token,
                key,
                algorithms=[settings.JWT_ALGORITHM],
                options={"verify_exp": True},
            )
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("Access token has expired.") from None
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed("Invalid access token.") from None

        # Validate token_type
        if payload.get("token_type") != "access":
            raise exceptions.AuthenticationFailed("Invalid token type; access token required.")

        # Validate role
        token_role = payload.get("role")
        if str(token_role).lower() != self.role.lower():
            raise exceptions.AuthenticationFailed(
                f"Token role mismatch: expected {self.role}, got {token_role}."
            )

        # Check JTI blacklist
        jti = payload.get("jti")
        if jti and is_token_jti_blacklisted(jti, self.role):
            raise exceptions.AuthenticationFailed("Access token has been revoked.")

        # Check password reset invalidation timestamp
        user_id = payload.get("user_id")
        iat = payload.get("iat")
        if user_id and iat:
            if is_token_invalidated_by_timestamp(user_id, iat):
                raise exceptions.AuthenticationFailed(
                    "Token has been invalidated due to a password reset."
                )

        return payload

    def _get_user(self, payload: dict[str, Any]) -> User:
        user_id_raw = payload.get("user_id")
        if not user_id_raw:
            raise exceptions.AuthenticationFailed("Token does not contain a user ID.")

        try:
            user_uuid = uuid.UUID(str(user_id_raw))
        except ValueError:
            raise exceptions.AuthenticationFailed("Invalid user ID format in token.") from None

        # Check short-lived user state cache (15s)
        cache_key = get_user_state_cache_key(user_uuid)
        cached_state = cache.get(cache_key)

        if cached_state and not cached_state.get("is_active", True):
            raise exceptions.AuthenticationFailed("User account is inactive.")

        try:
            user = User.objects.get(id=user_uuid)
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed("User not found.") from None

        if not user.is_active:
            cache.set(cache_key, {"is_active": False}, timeout=settings.USER_STATE_CACHE_TTL)
            raise exceptions.AuthenticationFailed("User account is inactive.")

        # Update cache
        cache.set(
            cache_key,
            {
                "is_active": True,
                "role": user.role,
                "is_email_verified": user.is_email_verified,
                "is_approved": user.is_approved,
                "approval_status": user.approval_status,
            },
            timeout=settings.USER_STATE_CACHE_TTL,
        )

        return user

    def _enforce_csrf(self, request: Request) -> None:
        """
        Double-submit CSRF cookie enforcement:
        X-CSRFToken header must match the role-specific CSRF cookie
        ({role}_csrf, e.g. student_csrf).
        Bypassed if _dont_enforce_csrf_checks is True (e.g. Django test client).
        """
        if getattr(request, "_dont_enforce_csrf_checks", False):
            return

        csrf_cookie_name = f"{self.role}_csrf"
        csrf_cookie = request.COOKIES.get(csrf_cookie_name)
        csrf_header = request.headers.get("X-CSRFToken") or request.META.get("HTTP_X_CSRFTOKEN")

        if not csrf_cookie or not csrf_header:
            raise exceptions.PermissionDenied("CSRF cookie or token missing.")

        if not hmac.compare_digest(csrf_cookie, csrf_header):
            raise exceptions.PermissionDenied("CSRF token mismatch.")

    def authenticate_header(self, request: Request) -> str:
        return f'Bearer realm="{self.role}"'


class AdminJWTCookieAuthentication(BaseJWTCookieAuthentication):
    """Admin-specific JWT cookie authentication (/api/admin/)."""

    role = "admin"
    cookie_name = "admin_access"
    refresh_cookie_name = "admin_refresh"


class TeacherJWTCookieAuthentication(BaseJWTCookieAuthentication):
    """Teacher-specific JWT cookie authentication (/api/teacher/)."""

    role = "teacher"
    cookie_name = "teacher_access"
    refresh_cookie_name = "teacher_refresh"


class StudentJWTCookieAuthentication(BaseJWTCookieAuthentication):
    """Student-specific JWT cookie authentication (/api/student/)."""

    role = "student"
    cookie_name = "student_access"
    refresh_cookie_name = "student_refresh"
