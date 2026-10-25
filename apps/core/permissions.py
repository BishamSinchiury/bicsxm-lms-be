"""
Permission classes for LMS role and scope enforcement.
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.core.utils import get_user_status


class IsAdminRole(BasePermission):
    """Requires the authenticated user to have the ADMIN role and admin token."""

    message = "Admin privileges required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        auth_role = getattr(request, "auth_role", None)
        return request.user.role == "ADMIN" and (auth_role is None or auth_role == "admin")


class IsTeacherRole(BasePermission):
    """Requires the authenticated user to have the TEACHER role and teacher token."""

    message = "Teacher privileges required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        auth_role = getattr(request, "auth_role", None)
        return request.user.role == "TEACHER" and (auth_role is None or auth_role == "teacher")


class IsStudentRole(BasePermission):
    """Requires the authenticated user to have the STUDENT role and student token."""

    message = "Student privileges required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        auth_role = getattr(request, "auth_role", None)
        return request.user.role == "STUDENT" and (auth_role is None or auth_role == "student")


class HasFullScope(BasePermission):
    """
    Requires the access token to have scope='full' AND the user to be ACTIVE.
    Blocks limited-scope tokens (e.g. unverified email, pending or rejected teachers).
    """

    message = "Full access required. Please complete email verification or await approval."

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False

        auth_scope = getattr(request, "auth_scope", "full")
        if auth_scope != "full":
            return False

        status = get_user_status(request.user)
        if status != "ACTIVE":
            if status == "EMAIL_UNVERIFIED":
                self.message = "Email verification required."
            elif status == "PENDING_APPROVAL":
                self.message = "Account is pending administrator approval."
            elif status == "REJECTED":
                self.message = "Your teacher account application was rejected."
            else:
                self.message = "Account is inactive."
            return False

        return True


class AllowLimitedScope(BasePermission):
    """
    Permits requests with either scope='limited' or scope='full'.
    Used for endpoints that unverified or pending users are allowed to access:
    (verify-otp, resend-otp, logout, me, token/refresh).
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(request.user and request.user.is_authenticated)


# Composites for full-access role endpoints
IsActiveAdmin = IsAdminRole & HasFullScope
IsActiveTeacher = IsTeacherRole & HasFullScope
IsActiveStudent = IsStudentRole & HasFullScope
