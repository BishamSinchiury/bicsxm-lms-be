"""
Account models — User, TeacherProfile, StudentProfile.

The User model uses email as the USERNAME_FIELD and a UUID primary key.
Profiles are auto-created via post_save signals (see signals.py).
"""

from __future__ import annotations

import uuid

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from apps.accounts.managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """Custom LMS user — email-based authentication with role support."""

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        TEACHER = "TEACHER", "Teacher"
        STUDENT = "STUDENT", "Student"

    class ApprovalStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, max_length=255)
    full_name = models.CharField(max_length=255)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT)

    # Account state
    is_email_verified = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=True)
    approval_status = models.CharField(
        max_length=10,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.APPROVED,
        help_text="Tracks approval state for teachers (PENDING/APPROVED/REJECTED).",
    )

    # Django flags
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    # Timestamps
    date_joined = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    objects = UserManager()

    class Meta:
        db_table = "users"
        ordering = ["-date_joined"]

    def __str__(self) -> str:
        return f"{self.email} ({self.get_role_display()})"

    def save(self, *args, **kwargs) -> None:
        """Keep is_approved in sync with approval_status."""
        self.is_approved = self.approval_status == self.ApprovalStatus.APPROVED
        self.email = self.email.lower()
        super().save(*args, **kwargs)


class TeacherProfile(models.Model):
    """Extended profile for teacher accounts."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="teacher_profile",
        primary_key=True,
    )
    phone = models.CharField(max_length=20, blank=True, default="")
    department = models.CharField(max_length=255, blank=True, default="")
    bio = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "teacher_profiles"

    def __str__(self) -> str:
        return f"TeacherProfile({self.user.email})"


class StudentProfile(models.Model):
    """Extended profile for student accounts."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="student_profile",
        primary_key=True,
    )
    phone = models.CharField(max_length=20, blank=True, default="")
    enrollment_id = models.CharField(max_length=50, blank=True, default="")
    enrollment_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "student_profiles"

    def __str__(self) -> str:
        return f"StudentProfile({self.user.email})"


class AuditLog(models.Model):
    """
    Records every admin action on a user account.

    actor  — the admin who performed the action
    target — the affected user (nullable: survives target deletion)
    action — short code string, e.g. 'activate', 'deactivate', 'resend_verification'
    ip     — the request originator IP address
    metadata — arbitrary context (reason, old/new values, …)
    """

    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_actions",
    )
    target = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_records",
    )
    action = models.CharField(max_length=64)
    ip = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["actor"]),
            models.Index(fields=["target"]),
            models.Index(fields=["action"]),
        ]

    def __str__(self) -> str:
        return f"AuditLog({self.action} by {self.actor_id} on {self.target_id})"

