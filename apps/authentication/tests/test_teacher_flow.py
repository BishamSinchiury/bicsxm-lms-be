"""
End-to-end integration tests for Teacher flow:
Signup -> Verify OTP (pending approval) -> Admin approves -> Token refresh (upgrades to full) -> Ping.
Also tests teacher rejection flow (status REJECTED, limited scope).
"""

from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.authentication.tokens import generate_tokens_for_user


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_superuser(
        email="admin@test.com",
        password="adminpassword123",
        full_name="Admin Admin",
    )
    tokens = generate_tokens_for_user(admin, role="admin", scope="full")
    c = APIClient()
    c.cookies["admin_access"] = tokens["access_token"]
    c.cookies["admin_csrf"] = "test-csrf"
    c.credentials(HTTP_X_CSRFTOKEN="test-csrf")
    return c


@pytest.mark.django_db
class TestTeacherFlow:
    @patch("apps.authentication.views.send_otp_email.delay")
    def test_teacher_signup_pending_approval_and_activation(
        self,
        mock_email,
        client,
        admin_client,
    ):
        # 1. Teacher Signup
        signup_payload = {
            "email": "teacher1@example.com",
            "full_name": "Bob Teacher",
            "password": "SecurePassword123!",
        }
        res_signup = client.post("/api/teacher/auth/signup/", signup_payload, format="json")
        assert res_signup.status_code == status.HTTP_201_CREATED
        assert res_signup.data["status"] == "EMAIL_UNVERIFIED"
        assert res_signup.data["scope"] == "limited"
        assert "teacher_access" in res_signup.cookies
        assert "teacher_refresh" in res_signup.cookies
        assert "teacher_csrf" in res_signup.cookies

        # 2. Verify OTP -> becomes PENDING_APPROVAL with limited token
        user = User.objects.get(email="teacher1@example.com")
        otp = mock_email.call_args[0][1]

        res_verify = client.post(
            "/api/teacher/auth/verify-otp/",
            {"otp": otp},
            format="json",
            HTTP_X_CSRFTOKEN=client.cookies["teacher_csrf"].value,
        )
        assert res_verify.status_code == status.HTTP_200_OK
        assert res_verify.data["status"] == "PENDING_APPROVAL"
        assert res_verify.data["scope"] == "limited"

        user.refresh_from_db()
        assert user.is_email_verified is True
        assert user.approval_status == User.ApprovalStatus.PENDING
        assert user.is_approved is False

        # 3. Cannot access dashboard ping while pending (403)
        res_ping = client.get("/api/teacher/dashboard/ping/")
        assert res_ping.status_code == status.HTTP_403_FORBIDDEN

        # 4. Admin approves teacher
        res_approve = admin_client.post(f"/api/admin/teachers/{user.id}/approve/")
        assert res_approve.status_code == status.HTTP_200_OK

        user.refresh_from_db()
        assert user.approval_status == User.ApprovalStatus.APPROVED
        assert user.is_approved is True

        # 5. Teacher refreshes token -> scope upgrades to full!
        res_refresh = client.post(
            "/api/teacher/auth/token/refresh/",
            HTTP_X_CSRFTOKEN=client.cookies["teacher_csrf"].value,
        )
        assert res_refresh.status_code == status.HTTP_200_OK
        assert res_refresh.data["status"] == "ACTIVE"
        assert res_refresh.data["scope"] == "full"

        # 6. Teacher can now access dashboard ping
        res_ping_active = client.get("/api/teacher/dashboard/ping/")
        assert res_ping_active.status_code == status.HTTP_200_OK
        assert res_ping_active.data == {"role": "teacher", "message": "pong"}

    def test_rejected_teacher_flow(self, client, admin_client):
        # Create an unapproved teacher
        teacher = User.objects.create_user(
            email="rejected@example.com",
            password="Password123!",
            full_name="Rejected Teacher",
            role=User.Role.TEACHER,
            is_email_verified=True,
        )

        # Admin rejects teacher
        res_reject = admin_client.post(f"/api/admin/teachers/{teacher.id}/reject/")
        assert res_reject.status_code == status.HTTP_200_OK
        teacher.refresh_from_db()
        assert teacher.approval_status == User.ApprovalStatus.REJECTED
        assert teacher.is_approved is False

        # Teacher logs in -> status REJECTED, limited token only (amendment 3)
        res_login = client.post(
            "/api/teacher/auth/login/",
            {"email": "rejected@example.com", "password": "Password123!"},
            format="json",
        )
        assert res_login.status_code == status.HTTP_200_OK
        assert res_login.data["status"] == "REJECTED"
        assert res_login.data["scope"] == "limited"

        # /me endpoint returns status REJECTED
        res_me = client.get("/api/teacher/auth/me/")
        assert res_me.status_code == status.HTTP_200_OK
        assert res_me.data["status"] == "REJECTED"

        # Dashboard ping fails with 403
        res_ping = client.get("/api/teacher/dashboard/ping/")
        assert res_ping.status_code == status.HTTP_403_FORBIDDEN
