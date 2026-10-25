"""Custom user manager for the LMS User model."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import BaseUserManager


class UserManager(BaseUserManager):
    """Manager for the custom User model (email-based, no username)."""

    def _create_user(
        self,
        email: str,
        password: str | None,
        **extra_fields: Any,
    ) -> Any:  # returns User, but avoids circular import
        """Create and persist a user with the given email and password."""
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> Any:
        """Create a regular user with role-aware defaults."""
        from apps.accounts.models import User

        role = extra_fields.get("role", User.Role.STUDENT)

        if role == User.Role.STUDENT:
            extra_fields.setdefault("is_approved", True)
            extra_fields.setdefault("approval_status", User.ApprovalStatus.APPROVED)
        elif role == User.Role.TEACHER:
            extra_fields.setdefault("is_approved", False)
            extra_fields.setdefault("approval_status", User.ApprovalStatus.PENDING)
        elif role == User.Role.ADMIN:
            extra_fields.setdefault("is_approved", True)
            extra_fields.setdefault("approval_status", User.ApprovalStatus.APPROVED)
            extra_fields.setdefault("is_email_verified", True)
            extra_fields.setdefault("is_staff", True)

        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> Any:
        """Create a superuser (always role=ADMIN)."""
        from apps.accounts.models import User

        extra_fields["role"] = User.Role.ADMIN
        extra_fields["is_staff"] = True
        extra_fields["is_superuser"] = True
        extra_fields["is_email_verified"] = True
        extra_fields["is_approved"] = True
        extra_fields["approval_status"] = User.ApprovalStatus.APPROVED
        return self._create_user(email, password, **extra_fields)
