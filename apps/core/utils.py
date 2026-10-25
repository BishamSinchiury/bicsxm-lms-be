"""
Core utilities: user status calculation, user state cache, and token invalidation helpers.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

import redis
from django.conf import settings
from django.core.cache import cache

if TYPE_CHECKING:
    from apps.accounts.models import User

# Redis client for OTP & token state (DB 1 per spec)
_otp_redis_client: redis.Redis | None = None


def get_otp_redis() -> redis.Redis:
    """Return a Redis client connection to DB 1 (OTP and token blacklisting)."""
    global _otp_redis_client
    if _otp_redis_client is None:
        try:
            client = redis.Redis.from_url(settings.OTP_REDIS_URL, decode_responses=True, socket_connect_timeout=1)
            client.ping()
            _otp_redis_client = client
        except Exception:
            if settings.DEBUG:
                import fakeredis
                _otp_redis_client = fakeredis.FakeRedis(decode_responses=True)
            else:
                raise
    return _otp_redis_client


def get_user_status(user: User) -> str:
    """
    Calculate the effective account status for a user.

    Returns one of:
    - "INACTIVE"          (user.is_active is False)
    - "EMAIL_UNVERIFIED"  (email not yet verified via OTP)
    - "REJECTED"          (teacher whose application was rejected)
    - "PENDING_APPROVAL"  (teacher awaiting admin approval)
    - "ACTIVE"            (fully verified and active)
    """
    if not user.is_active:
        return "INACTIVE"

    if not user.is_email_verified:
        return "EMAIL_UNVERIFIED"

    if user.role == "TEACHER":
        from apps.accounts.models import User as UserModel

        if user.approval_status == UserModel.ApprovalStatus.REJECTED:
            return "REJECTED"
        if user.approval_status == UserModel.ApprovalStatus.PENDING or not user.is_approved:
            return "PENDING_APPROVAL"
        return "ACTIVE"

    # Students and Admins who are active and verified are ACTIVE
    return "ACTIVE"


def get_user_state_cache_key(user_id: str | uuid.UUID) -> str:
    return f"user_state:{user_id}"


def invalidate_user_state_cache(user_id: str | uuid.UUID) -> None:
    """Clear cached user status in Redis DB 0 (Django cache)."""
    cache.delete(get_user_state_cache_key(user_id))


# ---------------------------------------------------------------------------
# Token invalidation & blacklisting helpers (Redis DB 1)
# ---------------------------------------------------------------------------


def invalidate_all_user_tokens(user_id: str | uuid.UUID) -> int:
    """
    Record that all tokens issued before the current timestamp for `user_id` are invalid.
    Used during password reset.
    Returns the cutoff unix timestamp.
    """
    r = get_otp_redis()
    now_ts = int(time.time())
    key = f"tokens_valid_after:{user_id}"
    # TTL matches the refresh token lifetime (e.g. 7 days = 604800 seconds)
    ttl = int(settings.JWT_REFRESH_TOKEN_LIFETIME.total_seconds())
    r.setex(key, ttl, str(now_ts))
    invalidate_user_state_cache(user_id)
    return now_ts


def is_token_invalidated_by_timestamp(user_id: str | uuid.UUID, iat: int | float | None) -> bool:
    """Check if token was issued prior to a password-reset invalidation cutoff."""
    if iat is None:
        return False
    r = get_otp_redis()
    key = f"tokens_valid_after:{user_id}"
    valid_after_val = r.get(key)
    if not valid_after_val:
        return False
    try:
        valid_after = int(valid_after_val)
        return int(iat) < valid_after
    except (ValueError, TypeError):
        return False


def blacklist_token_jti(jti: str, role: str, expires_in_seconds: int = 604800) -> None:
    """
    Add a token's jti to the Redis blacklist.
    Used on logout for access token and refresh token.
    """
    if not jti:
        return
    r = get_otp_redis()
    key = f"token_blacklist:{role.lower()}:{jti}"
    # Ensure minimum TTL of 60 seconds
    ttl = max(60, expires_in_seconds)
    r.setex(key, ttl, "blacklisted")


def is_token_jti_blacklisted(jti: str, role: str) -> bool:
    """Check if token's jti is in the Redis blacklist."""
    if not jti:
        return False
    r = get_otp_redis()
    key = f"token_blacklist:{role.lower()}:{jti}"
    return bool(r.exists(key))
