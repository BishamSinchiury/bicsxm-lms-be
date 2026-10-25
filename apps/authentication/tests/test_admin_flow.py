"""
End-to-end integration tests for Admin authentication flow:
Step 1 Login -> Resend OTP without cookies -> Step 2 Verify OTP -> Ping -> /me.
"""

from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        email="superadmin@example.com",
        password="AdminSecurePassword123!",
        full_name="Super Admin",
    )


@pytest.fixture
def client():
    return APIClient()


@pytest.mark.django_db
class TestAdminFlow:
    @patch("apps.authentication.views.send_otp_email.delay")
    def test_complete_admin_login_flow(self, mock_email, client, admin_user):
        # 1. Step 1: Login with email + password
        login_payload = {
            "email": "superadmin@example.com",
            "password": "AdminSecurePassword123!",
        }
        res_step1 = client.post("/api/admin/auth/login/", login_payload, format="json")
        assert res_step1.status_code == status.HTTP_200_OK
        assert res_step1.data["requires_otp"] is True

        # Ensure NO cookies are set in Step 1
        assert "admin_access" not in res_step1.cookies
        assert "admin_refresh" not in res_step1.cookies

        # 2. Resend OTP without cookies (amendment 2)
        # Cooldown check: immediate resend triggers cooldown error or generic response
        res_resend = client.post(
            "/api/admin/auth/resend-otp/",
            {"email": "superadmin@example.com"},
            format="json",
        )
        assert res_resend.status_code == status.HTTP_200_OK

        # 3. Step 2: Verify OTP
        otp = mock_email.call_args[0][1]
        verify_payload = {
            "email": "superadmin@example.com",
            "otp": otp,
        }
        res_step2 = client.post("/api/admin/auth/login/verify-otp/", verify_payload, format="json")
        assert res_step2.status_code == status.HTTP_200_OK
        assert res_step2.data["status"] == "ACTIVE"
        assert res_step2.data["scope"] == "full"

        # Cookies MUST be set in Step 2
        assert "admin_access" in res_step2.cookies
        assert "admin_refresh" in res_step2.cookies
        assert "admin_csrf" in res_step2.cookies

        # 4. Admin Dashboard Ping
        res_ping = client.get("/api/admin/dashboard/ping/")
        assert res_ping.status_code == status.HTTP_200_OK
        assert res_ping.data == {"role": "admin", "message": "pong"}

        # 5. Admin /me
        res_me = client.get("/api/admin/auth/me/")
        assert res_me.status_code == status.HTTP_200_OK
        assert res_me.data["email"] == "superadmin@example.com"
        assert res_me.data["role"] == "ADMIN"
        assert res_me.data["status"] == "ACTIVE"
