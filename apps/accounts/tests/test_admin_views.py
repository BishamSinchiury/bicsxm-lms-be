"""
Tests for Admin teacher-management endpoints:
- GET /api/admin/teachers/
- POST /api/admin/teachers/{id}/approve/
- POST /api/admin/teachers/{id}/reject/
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.authentication.tokens import generate_tokens_for_user


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        email="admin@test.com",
        password="adminpassword123",
        full_name="Admin Admin",
    )


@pytest.fixture
def teacher_user(db):
    return User.objects.create_user(
        email="teacher@test.com",
        password="teacherpassword123",
        full_name="Teacher One",
        role=User.Role.TEACHER,
    )


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    tokens = generate_tokens_for_user(admin_user, role="admin", scope="full")
    client.cookies["admin_access"] = tokens["access_token"]
    client.cookies["admin_csrf"] = "test-csrf"
    client.credentials(HTTP_X_CSRFTOKEN="test-csrf")
    return client


@pytest.mark.django_db
class TestAdminTeacherViews:
    def test_list_teachers_unauthenticated(self):
        client = APIClient()
        response = client.get("/api/admin/teachers/")
        assert (
            response.status_code == status.HTTP_401_UNAUTHORIZED
            or response.status_code == status.HTTP_403_FORBIDDEN
        )

    def test_list_teachers_as_admin(self, admin_client, teacher_user):
        response = admin_client.get("/api/admin/teachers/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) >= 1
        assert any(t["email"] == teacher_user.email for t in data)

    def test_filter_teachers_by_status(self, admin_client, teacher_user):
        response = admin_client.get("/api/admin/teachers/?status=pending")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["approval_status"] == "PENDING"

    def test_approve_teacher(self, admin_client, teacher_user):
        url = f"/api/admin/teachers/{teacher_user.id}/approve/"
        response = admin_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        teacher_user.refresh_from_db()
        assert teacher_user.approval_status == User.ApprovalStatus.APPROVED
        assert teacher_user.is_approved is True

    def test_reject_teacher(self, admin_client, teacher_user):
        url = f"/api/admin/teachers/{teacher_user.id}/reject/"
        response = admin_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        teacher_user.refresh_from_db()
        assert teacher_user.approval_status == User.ApprovalStatus.REJECTED
        assert teacher_user.is_approved is False
