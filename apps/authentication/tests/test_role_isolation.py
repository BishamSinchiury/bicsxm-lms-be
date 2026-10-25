"""
Tests for Role Isolation, Cookie Path Scoping, and Multi-Role Session Independence:
1. Students cannot access teacher or admin dashboards.
2. Teachers cannot access student or admin dashboards.
3. Cryptographic isolation: Student token passed as admin cookie fails signature/role check.
4. Independent logout: Logging out of student does not clear or invalidate teacher cookies.
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.authentication.tokens import generate_tokens_for_user


@pytest.fixture
def student_user(db):
    return User.objects.create_user(
        email="student_iso@example.com",
        password="Password123!",
        full_name="Student Iso",
        role=User.Role.STUDENT,
        is_email_verified=True,
    )


@pytest.fixture
def teacher_user(db):
    user = User.objects.create_user(
        email="teacher_iso@example.com",
        password="Password123!",
        full_name="Teacher Iso",
        role=User.Role.TEACHER,
        is_email_verified=True,
    )
    user.approval_status = User.ApprovalStatus.APPROVED
    user.save()
    return user


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        email="admin_iso@example.com",
        password="Password123!",
        full_name="Admin Iso",
    )


@pytest.mark.django_db
class TestRoleIsolation:
    def test_student_cannot_access_teacher_or_admin(self, student_user):
        tokens = generate_tokens_for_user(student_user, role="student", scope="full")
        client = APIClient()
        client.cookies["student_access"] = tokens["access_token"]

        # Student accesses student ping -> OK
        res_student = client.get("/api/student/dashboard/ping/")
        assert res_student.status_code == status.HTTP_200_OK

        # Student cannot access teacher ping (no teacher cookie) -> 401
        res_teacher = client.get("/api/teacher/dashboard/ping/")
        assert res_teacher.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

        # Student cannot access admin ping -> 401
        res_admin = client.get("/api/admin/dashboard/ping/")
        assert res_admin.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_cryptographic_isolation_across_roles(self, student_user):
        """Passing a student token inside the admin_access cookie fails verification."""
        student_tokens = generate_tokens_for_user(student_user, role="student", scope="full")

        client = APIClient()
        client.cookies["admin_access"] = student_tokens["access_token"]

        res = client.get("/api/admin/dashboard/ping/")
        assert res.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_multi_role_simultaneous_sessions_and_independent_logout(
        self,
        student_user,
        teacher_user,
    ):
        """A user logged into student and teacher tabs can log out of student without losing teacher session."""
        student_tokens = generate_tokens_for_user(student_user, role="student", scope="full")
        teacher_tokens = generate_tokens_for_user(teacher_user, role="teacher", scope="full")

        client = APIClient()
        client.cookies["student_access"] = student_tokens["access_token"]
        client.cookies["student_refresh"] = student_tokens["refresh_token"]
        client.cookies["student_csrf"] = "csrf123"
        client.cookies["teacher_access"] = teacher_tokens["access_token"]
        client.cookies["teacher_refresh"] = teacher_tokens["refresh_token"]
        client.cookies["teacher_csrf"] = "csrf456"
        client.credentials(HTTP_X_CSRFTOKEN="csrf123")

        # Both pings work
        assert client.get("/api/student/dashboard/ping/").status_code == status.HTTP_200_OK
        assert client.get("/api/teacher/dashboard/ping/").status_code == status.HTTP_200_OK

        # Logout of student
        res_logout = client.post("/api/student/auth/logout/")
        assert res_logout.status_code == status.HTTP_200_OK

        # Student cookie is deleted, teacher cookie is preserved!
        assert client.cookies["student_access"].value == ""
        assert client.cookies["teacher_access"].value == teacher_tokens["access_token"]
        assert client.cookies["teacher_csrf"].value == "csrf456"

        # Teacher ping still succeeds
        assert client.get("/api/teacher/dashboard/ping/").status_code == status.HTTP_200_OK
