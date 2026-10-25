"""
Tests for Account models: User, TeacherProfile, StudentProfile, and UserManager.
"""

import pytest

from apps.accounts.models import User


@pytest.mark.django_db
class TestUserModel:
    def test_create_student_defaults(self):
        user = User.objects.create_user(
            email="student@example.com",
            password="securepassword123",
            full_name="John Student",
            role=User.Role.STUDENT,
        )
        assert user.role == User.Role.STUDENT
        assert user.is_email_verified is False
        assert user.is_approved is True
        assert user.approval_status == User.ApprovalStatus.APPROVED
        assert user.is_active is True
        assert user.is_staff is False
        assert hasattr(user, "student_profile")
        assert not hasattr(user, "teacher_profile")

    def test_create_teacher_defaults(self):
        user = User.objects.create_user(
            email="teacher@example.com",
            password="securepassword123",
            full_name="Jane Teacher",
            role=User.Role.TEACHER,
        )
        assert user.role == User.Role.TEACHER
        assert user.is_email_verified is False
        assert user.is_approved is False
        assert user.approval_status == User.ApprovalStatus.PENDING
        assert user.is_active is True
        assert user.is_staff is False
        assert hasattr(user, "teacher_profile")
        assert not hasattr(user, "student_profile")

    def test_create_admin_defaults(self):
        user = User.objects.create_superuser(
            email="admin@example.com",
            password="adminpassword123",
            full_name="Root Admin",
        )
        assert user.role == User.Role.ADMIN
        assert user.is_email_verified is True
        assert user.is_approved is True
        assert user.approval_status == User.ApprovalStatus.APPROVED
        assert user.is_active is True
        assert user.is_staff is True
        assert user.is_superuser is True

    def test_approval_status_syncs_with_is_approved(self):
        teacher = User.objects.create_user(
            email="teacher2@example.com",
            password="securepassword123",
            full_name="Teacher Two",
            role=User.Role.TEACHER,
        )
        assert teacher.is_approved is False
        assert teacher.approval_status == User.ApprovalStatus.PENDING

        teacher.approval_status = User.ApprovalStatus.APPROVED
        teacher.save()
        teacher.refresh_from_db()
        assert teacher.is_approved is True

        teacher.approval_status = User.ApprovalStatus.REJECTED
        teacher.save()
        teacher.refresh_from_db()
        assert teacher.is_approved is False

    def test_email_lowercased(self):
        user = User.objects.create_user(
            email="MixedCase@EXAMPLE.COM",
            password="securepassword123",
            full_name="Test User",
        )
        assert user.email == "mixedcase@example.com"
