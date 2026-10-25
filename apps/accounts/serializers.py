"""Serializers for admin-facing teacher and user management endpoints."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.accounts.models import AuditLog, StudentProfile, TeacherProfile, User
from apps.core.utils import get_user_status


# ---------------------------------------------------------------------------
# Teacher management (existing)
# ---------------------------------------------------------------------------


class TeacherListSerializer(serializers.ModelSerializer):
    """Read-only serializer for listing teachers with approval state."""

    status = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "is_email_verified",
            "approval_status",
            "is_approved",
            "status",
            "date_joined",
        ]
        read_only_fields = fields

    def get_status(self, obj: User) -> str:
        return get_user_status(obj)


class TeacherActionSerializer(serializers.Serializer):
    """Empty serializer for approve / reject actions (no body required)."""

    pass


# ---------------------------------------------------------------------------
# Profile serializers (nested)
# ---------------------------------------------------------------------------


class TeacherProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherProfile
        fields = ["phone", "department", "bio", "created_at", "updated_at"]


class StudentProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentProfile
        fields = ["phone", "enrollment_id", "enrollment_date", "created_at", "updated_at"]


# ---------------------------------------------------------------------------
# Admin user management
# ---------------------------------------------------------------------------


class UserListSerializer(serializers.ModelSerializer):
    """
    Lightweight read-only serializer for the paginated user list.
    Includes computed status and teacher approval_status.
    """

    status = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "role",
            "status",
            "is_active",
            "is_email_verified",
            "approval_status",
            "date_joined",
            "last_login",
        ]
        read_only_fields = fields

    def get_status(self, obj: User) -> str:
        return get_user_status(obj)


class UserDetailSerializer(serializers.ModelSerializer):
    """
    Detailed user serializer including nested profile and effective status.
    Used for GET /api/admin/users/{id}/.
    """

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
            "is_active",
            "is_email_verified",
            "is_approved",
            "approval_status",
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


class UserUpdateSerializer(serializers.ModelSerializer):
    """
    PATCH serializer — allows editing full_name and is_active only.
    Never touches role, password, or approval_status.
    """

    class Meta:
        model = User
        fields = ["full_name", "is_active"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        # Admins cannot have their full_name or is_active changed via this path
        # (only activate/deactivate endpoints handle is_active for any user).
        # We expose is_active here for completeness but guard it in the view.
        return attrs


class AuditLogSerializer(serializers.ModelSerializer):
    """Read-only serializer for AuditLog records."""

    actor_email = serializers.SerializerMethodField()
    target_email = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "actor_email",
            "target_email",
            "action",
            "ip",
            "timestamp",
            "metadata",
        ]

    def get_actor_email(self, obj: AuditLog) -> str | None:
        return obj.actor.email if obj.actor else None

    def get_target_email(self, obj: AuditLog) -> str | None:
        return obj.target.email if obj.target else None

