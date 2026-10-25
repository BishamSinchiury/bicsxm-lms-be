"""
Tests for Password Reset Flow and Token Invalidation:
- Request password reset (generic response)
- Confirm reset with OTP
- Verification that tokens issued BEFORE reset are invalidated (amendment 4)
- Verification that tokens issued AFTER reset work normally
"""

import time
from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.authentication.tokens import generate_tokens_for_user


@pytest.fixture
def student(db):
    return User.objects.create_user(
        email="reset_student@example.com",
        password="OldPassword123!",
        full_name="Reset Student",
        role=User.Role.STUDENT,
        is_email_verified=True,
    )


@pytest.fixture
def client():
    return APIClient()


@pytest.mark.django_db
class TestPasswordReset:
    @patch("apps.authentication.views.send_otp_email.delay")
    def test_password_reset_invalidates_all_previous_tokens(self, mock_email, client, student):
        # 1. Issue a valid token prior to password reset
        old_tokens = generate_tokens_for_user(student, role="student", scope="full")

        client.cookies["student_access"] = old_tokens["access_token"]
        res_ping_before = client.get("/api/student/dashboard/ping/")
        assert res_ping_before.status_code == status.HTTP_200_OK

        # 2. Request password reset
        res_req = client.post(
            "/api/student/auth/password-reset/request/",
            {"email": "reset_student@example.com"},
            format="json",
        )
        assert res_req.status_code == status.HTTP_200_OK
        assert "password reset code has been sent" in res_req.data["message"]

        # Ensure delay so timestamp increases
        time.sleep(1)

        # 3. Confirm password reset
        otp = mock_email.call_args[0][1]
        res_confirm = client.post(
            "/api/student/auth/password-reset/confirm/",
            {
                "email": "reset_student@example.com",
                "otp": otp,
                "new_password": "NewSecurePassword456!",
            },
            format="json",
        )
        assert res_confirm.status_code == status.HTTP_200_OK

        # Verify password actually changed
        student.refresh_from_db()
        assert student.check_password("NewSecurePassword456!") is True

        # 4. Old token MUST BE INVALIDATED via tokens_valid_after timestamp check (amendment 4)
        client.cookies["student_access"] = old_tokens["access_token"]
        res_ping_after = client.get("/api/student/dashboard/ping/")
        assert res_ping_after.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

        # 5. Login with new password issues a valid token that works
        res_login = client.post(
            "/api/student/auth/login/",
            {"email": "reset_student@example.com", "password": "NewSecurePassword456!"},
            format="json",
        )
        assert res_login.status_code == status.HTTP_200_OK

        res_ping_new = client.get("/api/student/dashboard/ping/")
        assert res_ping_new.status_code == status.HTTP_200_OK
