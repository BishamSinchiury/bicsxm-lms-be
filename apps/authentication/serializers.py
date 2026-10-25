"""
Serializers for authentication endpoints across all roles.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.accounts.models import StudentProfile, TeacherProfile, User
from apps.core.utils import get_user_status


class SignupSerializer(serializers.Serializer):
    """Signup payload for Student and Teacher registration."""

    email = serializers.EmailField(max_length=255)
    full_name = serializers.CharField(max_length=255)
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value

    def validate_email(self, value: str) -> str:
        return value.lower().strip()


class LoginSerializer(serializers.Serializer):
    """Email + password login payload."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate_email(self, value: str) -> str:
        return value.lower().strip()


class VerifyOTPSerializer(serializers.Serializer):
    """OTP code payload for authenticated requests (Student & Teacher)."""

    otp = serializers.CharField(min_length=6, max_length=6, trim_whitespace=True)


class AdminVerifyOTPSerializer(serializers.Serializer):
    """Admin step 2 login payload (requires email + OTP because no cookies are set yet)."""

    email = serializers.EmailField()
    otp = serializers.CharField(min_length=6, max_length=6, trim_whitespace=True)

    def validate_email(self, value: str) -> str:
        return value.lower().strip()


class AdminResendOTPSerializer(serializers.Serializer):
    """Admin resend-otp payload (no cookies present before completing OTP step 2)."""

    email = serializers.EmailField()

    def validate_email(self, value: str) -> str:
        return value.lower().strip()


class PasswordResetRequestSerializer(serializers.Serializer):
    """Request password reset OTP by email."""

    email = serializers.EmailField()

    def validate_email(self, value: str) -> str:
        return value.lower().strip()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Confirm password reset with OTP and set a new password."""

    email = serializers.EmailField()
    otp = serializers.CharField(min_length=6, max_length=6, trim_whitespace=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value: str) -> str:
        return value.lower().strip()

    def validate_new_password(self, value: str) -> str:
        validate_password(value)
        return value


class TeacherProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherProfile
        fields = ["phone", "department", "bio", "created_at", "updated_at"]


class StudentProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentProfile
        fields = ["phone", "enrollment_id", "enrollment_date", "created_at", "updated_at"]


class UserMeSerializer(serializers.ModelSerializer):
    """Detailed user profile serializer with dynamic status and profile nesting."""

    status = serializers.SerializerMethodField()
    profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "role",
            "status",
            "is_email_verified",
            "is_approved",
            "approval_status",
            "is_active",
            "date_joined",
            "last_login",
            "profile",
        ]
        read_only_fields = fields

    def get_status(self, obj: User) -> str:
        return get_user_status(obj)

    def get_profile(self, obj: User) -> dict[str, Any] | None:
        if obj.role == User.Role.TEACHER and hasattr(obj, "teacher_profile"):
            return TeacherProfileSerializer(obj.teacher_profile).data
        if obj.role == User.Role.STUDENT and hasattr(obj, "student_profile"):
            return StudentProfileSerializer(obj.student_profile).data
        return None
