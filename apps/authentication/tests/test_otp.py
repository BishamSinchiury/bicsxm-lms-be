"""
Tests for OTPService: generation, cooldown, verification, and max attempts.
"""

import pytest

from apps.authentication.services import OTPService
from apps.core.exceptions import (
    OTPCooldownError,
    OTPExpiredError,
    OTPInvalidError,
    OTPMaxAttemptsError,
)


class TestOTPService:
    def test_generate_and_verify_otp(self):
        email = "testotp@example.com"
        OTPService.delete_otp("signup_verify", email)

        otp = OTPService.generate_otp("signup_verify", email)
        assert len(otp) == 6
        assert otp.isdigit()

        # Verifying with the correct code succeeds
        verified = OTPService.verify_otp("signup_verify", email, otp)
        assert verified is True

        # Re-verifying fails because OTP is single-use and was deleted
        with pytest.raises(OTPExpiredError):
            OTPService.verify_otp("signup_verify", email, otp)

    def test_otp_cooldown(self):
        email = "cooldown@example.com"
        OTPService.delete_otp("signup_verify", email)

        OTPService.generate_otp("signup_verify", email)
        # Attempting to generate again immediately raises OTPCooldownError
        with pytest.raises(OTPCooldownError):
            OTPService.generate_otp("signup_verify", email)

        OTPService.delete_otp("signup_verify", email)

    def test_invalid_otp_and_attempt_counter(self):
        email = "invalid@example.com"
        OTPService.delete_otp("signup_verify", email)

        otp = OTPService.generate_otp("signup_verify", email)

        # Attempt with wrong code
        with pytest.raises(OTPInvalidError):
            OTPService.verify_otp(
                "signup_verify", email, "000000" if otp != "000000" else "111111"
            )

        OTPService.delete_otp("signup_verify", email)

    def test_max_attempts_exceeded(self):
        email = "maxattempts@example.com"
        OTPService.delete_otp("signup_verify", email)

        otp = OTPService.generate_otp("signup_verify", email)
        wrong_code = "999999" if otp != "999999" else "888888"

        # 4 failed attempts raise OTPInvalidError
        for _ in range(4):
            with pytest.raises(OTPInvalidError):
                OTPService.verify_otp("signup_verify", email, wrong_code)

        # 5th failed attempt raises OTPMaxAttemptsError and deletes key
        with pytest.raises(OTPMaxAttemptsError):
            OTPService.verify_otp("signup_verify", email, wrong_code)

        # Subsequent attempt raises OTPExpiredError
        with pytest.raises(OTPExpiredError):
            OTPService.verify_otp("signup_verify", email, wrong_code)
