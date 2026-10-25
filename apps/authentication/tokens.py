"""
Custom JWT token generator and validator with per-role isolation and scope control.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

import jwt
from django.conf import settings
from rest_framework import exceptions

from apps.accounts.models import User
from apps.core.utils import (
    get_user_status,
    is_token_invalidated_by_timestamp,
    is_token_jti_blacklisted,
)


def determine_token_scope(user: User) -> str:
    """
    Determine token scope based on user's live status:
    - Status ACTIVE -> 'full'
    - Otherwise (EMAIL_UNVERIFIED, PENDING_APPROVAL, REJECTED, INACTIVE) -> 'limited'
    """
    status = get_user_status(user)
    return "full" if status == "ACTIVE" else "limited"


def generate_tokens_for_user(
    user: User,
    role: str | None = None,
    scope: str | None = None,
) -> dict[str, str]:
    """
    Generate an access token and refresh token pair for a user with role and scope claims.
    Uses the role's isolated signing key.
    """
    target_role = (role or user.role).lower()
    signing_key = settings.JWT_SIGNING_KEYS.get(target_role)
    if not signing_key:
        raise ValueError(f"No JWT signing key configured for role: {target_role}")

    if scope is None:
        scope = determine_token_scope(user)

    now = datetime.datetime.now(datetime.UTC)
    now_ts = int(now.timestamp())

    access_exp = now + settings.JWT_ACCESS_TOKEN_LIFETIME
    refresh_exp = now + settings.JWT_REFRESH_TOKEN_LIFETIME

    access_jti = str(uuid.uuid4())
    refresh_jti = str(uuid.uuid4())

    access_payload = {
        "token_type": "access",
        "jti": access_jti,
        "user_id": str(user.id),
        "role": target_role,
        "scope": scope,
        "iat": now_ts,
        "exp": int(access_exp.timestamp()),
    }

    refresh_payload = {
        "token_type": "refresh",
        "jti": refresh_jti,
        "user_id": str(user.id),
        "role": target_role,
        "scope": scope,
        "iat": now_ts,
        "exp": int(refresh_exp.timestamp()),
    }

    access_token = jwt.encode(access_payload, signing_key, algorithm=settings.JWT_ALGORITHM)
    refresh_token = jwt.encode(refresh_payload, signing_key, algorithm=settings.JWT_ALGORITHM)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "access_jti": access_jti,
        "refresh_jti": refresh_jti,
        "scope": scope,
    }


def verify_refresh_token(raw_refresh_token: str, expected_role: str) -> dict[str, Any]:
    """
    Decode and validate a refresh token.
    Ensures:
    1. Signed with the correct role's secret
    2. token_type is 'refresh'
    3. role matches expected_role
    4. jti is not blacklisted
    5. Token iat is not prior to tokens_valid_after timestamp
    """
    role = expected_role.lower()
    signing_key = settings.JWT_SIGNING_KEYS.get(role)
    if not signing_key:
        raise exceptions.AuthenticationFailed("Invalid role for token refresh.")

    try:
        payload: dict[str, Any] = jwt.decode(
            raw_refresh_token,
            signing_key,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": True},
        )
    except jwt.ExpiredSignatureError:
        raise exceptions.AuthenticationFailed("Refresh token has expired.") from None
    except jwt.InvalidTokenError:
        raise exceptions.AuthenticationFailed("Invalid refresh token.") from None

    if payload.get("token_type") != "refresh":
        raise exceptions.AuthenticationFailed("Provided token is not a refresh token.")

    if str(payload.get("role", "")).lower() != role:
        raise exceptions.AuthenticationFailed("Token role mismatch.")

    jti = payload.get("jti")
    if jti and is_token_jti_blacklisted(jti, role):
        raise exceptions.AuthenticationFailed("Refresh token has been revoked.")

    user_id = payload.get("user_id")
    iat = payload.get("iat")
    if user_id and iat:
        if is_token_invalidated_by_timestamp(user_id, iat):
            raise exceptions.AuthenticationFailed(
                "Refresh token has been invalidated due to a password reset."
            )

    return payload
