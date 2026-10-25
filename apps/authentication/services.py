"""
OTP Service — HMAC-hashed one-time passwords stored in Redis (DB 1).

Handles:
- Cryptographically secure 6-digit generation (secrets.choice)
- HMAC-SHA256 hashing before storing in Redis
- 60-second resend cooldown enforcement
- Constant-time verification with attempt counter
- Automatic invalidation after max failed attempts or expiration
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import string
import time
from typing import Literal

from django.conf import settings

from apps.core.exceptions import (
    OTPCooldownError,
    OTPExpiredError,
    OTPInvalidError,
    OTPMaxAttemptsError,
)
from apps.core.utils import get_otp_redis

OTPPurpose = Literal["signup_verify", "admin_login", "password_reset"]


class OTPService:
    """Manages the lifecycle of one-time passwords in Redis."""

    @classmethod
    def _key(cls, purpose: str, email: str) -> str:
        return f"otp:{purpose}:{email.strip().lower()}"

    @classmethod
    def _hash_otp(cls, otp: str) -> str:
        secret = settings.OTP_HMAC_SECRET.encode("utf-8")
        return hmac.new(secret, otp.encode("utf-8"), hashlib.sha256).hexdigest()

    @classmethod
    def generate_otp(cls, purpose: OTPPurpose, email: str) -> str:
        """
        Generate a new 6-digit OTP, store its HMAC in Redis, and return the plaintext OTP.
        Enforces cooldown: if an OTP was created less than OTP_RESEND_COOLDOWN seconds ago,
        raises OTPCooldownError.
        """
        r = get_otp_redis()
        key = cls._key(purpose, email)
        now_ts = int(time.time())

        # Check existing OTP for cooldown
        existing_raw = r.get(key)
        if existing_raw:
            try:
                existing_data = json.loads(existing_raw)
                elapsed = now_ts - existing_data.get("created_at", 0)
                cooldown = settings.OTP_RESEND_COOLDOWN
                if elapsed < cooldown:
                    remaining = cooldown - elapsed
                    raise OTPCooldownError(
                        detail=f"Please wait {remaining} seconds before requesting a new code.",
                    )
            except (json.JSONDecodeError, TypeError):
                # If existing data is corrupt, overwrite it
                pass

        # Generate 6 digits
        digits = string.digits
        plaintext_otp = "".join(secrets.choice(digits) for _ in range(settings.OTP_LENGTH))
        otp_hash = cls._hash_otp(plaintext_otp)

        payload = {
            "hash": otp_hash,
            "attempts": 0,
            "created_at": now_ts,
        }

        # Store with TTL (default 300s = 5m)
        r.setex(key, settings.OTP_TTL, json.dumps(payload))
        return plaintext_otp

    @classmethod
    def verify_otp(cls, purpose: OTPPurpose, email: str, entered_otp: str) -> bool:
        """
        Verify the supplied OTP against the HMAC stored in Redis.
        - Deletes the key upon successful verification (single-use).
        - Increments attempt counter on failure.
        - Deletes the key and raises OTPMaxAttemptsError if max attempts exceeded.
        - Raises OTPExpiredError if the key does not exist.
        - Raises OTPInvalidError if mismatch.
        """
        r = get_otp_redis()
        key = cls._key(purpose, email)
        data_raw = r.get(key)

        if not data_raw:
            raise OTPExpiredError("OTP has expired or was not requested.")

        try:
            data = json.loads(data_raw)
        except (json.JSONDecodeError, TypeError):
            r.delete(key)
            raise OTPExpiredError("OTP has expired or is invalid.") from None

        stored_hash = data.get("hash", "")
        attempts = data.get("attempts", 0) + 1
        data["attempts"] = attempts

        entered_hash = cls._hash_otp(entered_otp.strip())

        if hmac.compare_digest(stored_hash, entered_hash):
            # Verification successful — delete OTP to prevent replay
            r.delete(key)
            return True

        # Failed attempt: check if max attempts reached
        if attempts >= settings.OTP_MAX_ATTEMPTS:
            r.delete(key)
            raise OTPMaxAttemptsError(
                "Maximum attempts exceeded. Please request a new verification code."
            )

        # Update remaining TTL and attempt count
        ttl = r.ttl(key)
        if ttl > 0:
            r.setex(key, ttl, json.dumps(data))

        remaining_attempts = settings.OTP_MAX_ATTEMPTS - attempts
        raise OTPInvalidError(
            f"Invalid verification code. {remaining_attempts} attempt(s) remaining."
        )

    @classmethod
    def delete_otp(cls, purpose: OTPPurpose, email: str) -> None:
        """Manually clear an OTP key."""
        r = get_otp_redis()
        r.delete(cls._key(purpose, email))
