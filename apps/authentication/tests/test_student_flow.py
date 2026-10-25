"""
End-to-end integration tests for the Student authentication flow:
Signup -> Limited cookie -> Verify OTP -> Full cookie -> Dashboard Ping -> Refresh -> Logout.
"""

from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.fixture
def client():
    return APIClient()


@pytest.mark.django_db
class TestStudentFlow:
    @patch("apps.authentication.views.send_otp_email.delay")
    def test_complete_student_flow(self, mock_email_delay, client):
        # 1. Signup
        signup_payload = {
            "email": "student1@example.com",
            "full_name": "Alice Student",
            "password": "StrongPassword123!",
        }
        res_signup = client.post("/api/student/auth/signup/", signup_payload, format="json")
        assert res_signup.status_code == status.HTTP_201_CREATED
        assert res_signup.data["status"] == "EMAIL_UNVERIFIED"
        assert res_signup.data["scope"] == "limited"

        # Cookies must be set on signup (amendment 1)
        assert "student_access" in res_signup.cookies
        assert "student_refresh" in res_signup.cookies
        assert "student_csrf" in res_signup.cookies

        # 2. Ping dashboard with limited token should fail (403)
        res_ping_limited = client.get("/api/student/dashboard/ping/")
        assert res_ping_limited.status_code == status.HTTP_403_FORBIDDEN

        # 3. Verify OTP
        user = User.objects.get(email="student1@example.com")
        assert user.is_email_verified is False

        # Get generated OTP from email task call args
        otp = mock_email_delay.call_args[0][1]
        res_verify = client.post(
            "/api/student/auth/verify-otp/",
            {"otp": otp},
            format="json",
            HTTP_X_CSRFTOKEN=client.cookies["student_csrf"].value,
        )
        assert res_verify.status_code == status.HTTP_200_OK
        assert res_verify.data["status"] == "ACTIVE"
        assert res_verify.data["scope"] == "full"

        user.refresh_from_db()
        assert user.is_email_verified is True

        # 4. Ping dashboard with full token should succeed (200)
        res_ping_full = client.get("/api/student/dashboard/ping/")
        assert res_ping_full.status_code == status.HTTP_200_OK
        assert res_ping_full.data == {"role": "student", "message": "pong"}

        # 5. GET /api/student/auth/me/
        res_me = client.get("/api/student/auth/me/")
        assert res_me.status_code == status.HTTP_200_OK
        assert res_me.data["email"] == "student1@example.com"
        assert res_me.data["status"] == "ACTIVE"
        assert res_me.data["profile"] is not None

        # 6. Refresh token
        res_refresh = client.post(
            "/api/student/auth/token/refresh/",
            HTTP_X_CSRFTOKEN=client.cookies["student_csrf"].value,
        )
        assert res_refresh.status_code == status.HTTP_200_OK
        assert res_refresh.data["status"] == "ACTIVE"

        # 7. Logout
        res_logout = client.post(
            "/api/student/auth/logout/",
            HTTP_X_CSRFTOKEN=client.cookies["student_csrf"].value,
        )
        assert res_logout.status_code == status.HTTP_200_OK

        # After logout, student_access cookie is deleted
        assert client.cookies["student_access"].value == ""

        # Dashboard ping now rejected
        res_ping_logged_out = client.get("/api/student/dashboard/ping/")
        assert (
            res_ping_logged_out.status_code == status.HTTP_401_UNAUTHORIZED
            or res_ping_logged_out.status_code == status.HTTP_403_FORBIDDEN
        )
