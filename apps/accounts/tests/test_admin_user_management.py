"""
Tests for Admin User Management endpoints (/api/admin/users/).
Covers:
- List pagination, filtering, searching, ordering
- Detail view with profile
- Patch user (full_name only, admin protection)
- Activate and deactivate (safeguards, token revocation via tokens_valid_after)
- Soft delete via DELETE method
- Resend verification OTP
- AuditLog verification
- Permission enforcement (only IsActiveAdmin with full scope)
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import AuditLog, User
from apps.authentication.tokens import generate_tokens_for_user


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        email="superadmin@example.com",
        password="AdminPassword123!",
        full_name="Super Admin",
    )


@pytest.fixture
def second_admin_user(db):
    return User.objects.create_superuser(
        email="admin2@example.com",
        password="AdminPassword123!",
        full_name="Second Admin",
    )


@pytest.fixture
def teacher_user(db):
    return User.objects.create_user(
        email="teacher@example.com",
        password="TeacherPassword123!",
        full_name="Alice Teacher",
        role=User.Role.TEACHER,
        approval_status=User.ApprovalStatus.PENDING,
        is_email_verified=True,
    )


@pytest.fixture
def student_user(db):
    return User.objects.create_user(
        email="student@example.com",
        password="StudentPassword123!",
        full_name="Charlie Student",
        role=User.Role.STUDENT,
        is_email_verified=False,
    )


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    tokens = generate_tokens_for_user(admin_user, role="admin", scope="full")
    client.cookies["admin_access"] = tokens["access_token"]
    client.cookies["admin_csrf"] = "admin-csrf-test"
    client.credentials(HTTP_X_CSRFTOKEN="admin-csrf-test")
    return client


@pytest.fixture
def student_client(student_user):
    client = APIClient()
    tokens = generate_tokens_for_user(student_user, role="student", scope="full")
    client.cookies["student_access"] = tokens["access_token"]
    client.cookies["student_csrf"] = "student-csrf-test"
    client.credentials(HTTP_X_CSRFTOKEN="student-csrf-test")
    return client


@pytest.mark.django_db
class TestAdminUserManagementList:
    def test_list_users_as_admin(self, admin_client, teacher_user, student_user, admin_user):
        response = admin_client.get("/api/admin/users/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "count" in data
        assert "results" in data
        assert data["count"] >= 3
        emails = [u["email"] for u in data["results"]]
        assert admin_user.email in emails
        assert teacher_user.email in emails
        assert student_user.email in emails

    def test_list_users_filter_role(self, admin_client, teacher_user, student_user):
        response = admin_client.get("/api/admin/users/?role=teacher")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        for user in data["results"]:
            assert user["role"] == "TEACHER"

    def test_list_users_filter_active(self, admin_client, student_user):
        student_user.is_active = False
        student_user.save()

        res_inactive = admin_client.get("/api/admin/users/?is_active=false")
        assert res_inactive.status_code == status.HTTP_200_OK
        emails = [u["email"] for u in res_inactive.json()["results"]]
        assert student_user.email in emails

        res_active = admin_client.get("/api/admin/users/?is_active=true")
        assert res_active.status_code == status.HTTP_200_OK
        active_emails = [u["email"] for u in res_active.json()["results"]]
        assert student_user.email not in active_emails

    def test_list_users_filter_email_verified(self, admin_client, teacher_user, student_user):
        response = admin_client.get("/api/admin/users/?is_email_verified=false")
        assert response.status_code == status.HTTP_200_OK
        emails = [u["email"] for u in response.json()["results"]]
        assert student_user.email in emails
        assert teacher_user.email not in emails

    def test_list_users_filter_status(self, admin_client, teacher_user, student_user):
        # Teacher is PENDING_APPROVAL
        res = admin_client.get("/api/admin/users/?status=PENDING_APPROVAL")
        assert res.status_code == status.HTTP_200_OK
        emails = [u["email"] for u in res.json()["results"]]
        assert teacher_user.email in emails

        # Student is EMAIL_UNVERIFIED
        res_unverified = admin_client.get("/api/admin/users/?status=EMAIL_UNVERIFIED")
        assert res_unverified.status_code == status.HTTP_200_OK
        emails_unverified = [u["email"] for u in res_unverified.json()["results"]]
        assert student_user.email in emails_unverified

    def test_list_users_search(self, admin_client, student_user):
        response = admin_client.get(f"/api/admin/users/?search={student_user.full_name}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["results"]) >= 1
        assert any(u["email"] == student_user.email for u in data["results"])

    def test_list_users_ordering(self, admin_client):
        response = admin_client.get("/api/admin/users/?ordering=full_name")
        assert response.status_code == status.HTTP_200_OK
        names = [u["full_name"] for u in response.json()["results"]]
        assert names == sorted(names)


@pytest.mark.django_db
class TestAdminUserDetailAndEdit:
    def test_get_user_detail(self, admin_client, teacher_user):
        response = admin_client.get(f"/api/admin/users/{teacher_user.id}/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["email"] == teacher_user.email
        assert data["role"] == "TEACHER"
        assert "profile" in data
        assert data["profile"] is not None

    def test_patch_user_full_name(self, admin_client, student_user, admin_user):
        response = admin_client.patch(
            f"/api/admin/users/{student_user.id}/",
            {"full_name": "Charlie Updated"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        student_user.refresh_from_db()
        assert student_user.full_name == "Charlie Updated"

        # Check audit log
        log = AuditLog.objects.filter(target=student_user, action="edit_user").first()
        assert log is not None
        assert log.actor == admin_user

    def test_patch_admin_user_forbidden(self, admin_client, second_admin_user):
        response = admin_client.patch(
            f"/api/admin/users/{second_admin_user.id}/",
            {"full_name": "Hacked Name"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestAdminUserActivationAndSafeguards:
    def test_deactivate_and_activate_user(self, admin_client, student_user, admin_user):
        # Generate active tokens for student
        student_tokens = generate_tokens_for_user(student_user, role="student", scope="full")

        # Deactivate
        res_deact = admin_client.post(f"/api/admin/users/{student_user.id}/deactivate/")
        assert res_deact.status_code == status.HTTP_200_OK
        student_user.refresh_from_db()
        assert student_user.is_active is False

        # Token must be rejected immediately on request (inactive account -> 403 ACCOUNT_INACTIVE)
        st_client = APIClient()
        st_client.cookies["student_access"] = student_tokens["access_token"]
        st_client.cookies["student_csrf"] = "st-csrf"
        st_client.credentials(HTTP_X_CSRFTOKEN="st-csrf")
        res_ping = st_client.get("/api/student/dashboard/ping/")
        assert res_ping.status_code == status.HTTP_403_FORBIDDEN
        assert res_ping.json()["error"]["code"] == "ACCOUNT_INACTIVE"

        # Check audit log
        assert AuditLog.objects.filter(target=student_user, action="deactivate").exists()

        # Activate
        res_act = admin_client.post(f"/api/admin/users/{student_user.id}/activate/")
        assert res_act.status_code == status.HTTP_200_OK
        student_user.refresh_from_db()
        assert student_user.is_active is True
        assert AuditLog.objects.filter(target=student_user, action="activate").exists()

    def test_cannot_deactivate_self(self, admin_client, admin_user):
        response = admin_client.post(f"/api/admin/users/{admin_user.id}/deactivate/")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        admin_user.refresh_from_db()
        assert admin_user.is_active is True

    def test_cannot_deactivate_last_active_admin(self, admin_client, second_admin_user, admin_user):
        # When second_admin_user is the ONLY other active admin:
        # If admin_user deactivates second_admin_user, that's allowed (admin_user is still active).
        res1 = admin_client.post(f"/api/admin/users/{second_admin_user.id}/deactivate/")
        assert res1.status_code == status.HTTP_200_OK

        # Now only admin_user is active. Any attempt to deactivate the last active admin fails.
        res_self = admin_client.post(f"/api/admin/users/{admin_user.id}/deactivate/")
        assert res_self.status_code == status.HTTP_403_FORBIDDEN

    def test_soft_delete_user(self, admin_client, student_user):
        response = admin_client.delete(f"/api/admin/users/{student_user.id}/")
        assert response.status_code == status.HTTP_200_OK
        student_user.refresh_from_db()
        assert student_user.is_active is False
        assert AuditLog.objects.filter(target=student_user, action="soft_delete").exists()

    def test_cannot_delete_self(self, admin_client, admin_user):
        response = admin_client.delete(f"/api/admin/users/{admin_user.id}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestAdminResendVerification:
    @patch("apps.core.tasks.send_otp_email.delay")
    def test_resend_verification_for_unverified_user(self, mock_email, admin_client, student_user):
        assert student_user.is_email_verified is False
        response = admin_client.post(f"/api/admin/users/{student_user.id}/resend-verification/")
        assert response.status_code == status.HTTP_200_OK
        assert mock_email.called
        assert AuditLog.objects.filter(target=student_user, action="resend_verification").exists()

    def test_resend_verification_for_already_verified_user(self, admin_client, teacher_user):
        assert teacher_user.is_email_verified is True
        response = admin_client.post(f"/api/admin/users/{teacher_user.id}/resend-verification/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestAdminPermissions:
    def test_student_cannot_access_admin_users(self, student_client):
        response = student_client.get("/api/admin/users/")
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_limited_scope_admin_cannot_access(self, admin_user):
        client = APIClient()
        tokens = generate_tokens_for_user(admin_user, role="admin", scope="limited")
        client.cookies["admin_access"] = tokens["access_token"]
        client.cookies["admin_csrf"] = "test-csrf"
        client.credentials(HTTP_X_CSRFTOKEN="test-csrf")

        response = client.get("/api/admin/users/")
        assert response.status_code == status.HTTP_403_FORBIDDEN
