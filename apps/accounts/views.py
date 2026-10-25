"""Admin-facing views for teacher management and user management."""

from __future__ import annotations

import logging

from django.core.paginator import Paginator
from django.db.models import Q, QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import AuditLog, User
from apps.accounts.serializers import (
    TeacherActionSerializer,
    TeacherListSerializer,
    UserDetailSerializer,
    UserListSerializer,
    UserUpdateSerializer,
)
from apps.core.authentication import AdminJWTCookieAuthentication
from apps.core.permissions import IsActiveAdmin
from apps.core.utils import invalidate_all_user_tokens, invalidate_user_state_cache

logger = logging.getLogger(__name__)


def _get_client_ip(request: Request) -> str | None:
    """Extract the client's real IP from headers or REMOTE_ADDR."""
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _audit(
    actor: User,
    target: User | None,
    action: str,
    request: Request,
    metadata: dict | None = None,
) -> None:
    """Create an AuditLog entry for an admin action."""
    AuditLog.objects.create(
        actor=actor,
        target=target,
        action=action,
        ip=_get_client_ip(request),
        metadata=metadata or {},
    )


# ===========================================================================
# Teacher management (existing)
# ===========================================================================


class TeacherListView(APIView):
    """GET /api/admin/teachers/ — paginated list of teachers, filterable by approval status."""

    authentication_classes = [AdminJWTCookieAuthentication]
    permission_classes = [IsActiveAdmin]

    @extend_schema(
        tags=["Admin Teachers"],
        parameters=[
            OpenApiParameter(
                name="status",
                description="Filter by approval status: pending, approved, rejected",
                required=False,
                type=str,
                enum=["pending", "approved", "rejected"],
            ),
            OpenApiParameter("page", int, description="Page number"),
            OpenApiParameter("page_size", int, description="Results per page (max 100)"),
        ],
        responses={200: TeacherListSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        """List teachers with pagination, optionally filtered by approval status."""
        qs = User.objects.filter(role=User.Role.TEACHER).order_by("-date_joined")

        status_filter = request.query_params.get("status")
        if status_filter:
            status_map = {
                "pending": User.ApprovalStatus.PENDING,
                "approved": User.ApprovalStatus.APPROVED,
                "rejected": User.ApprovalStatus.REJECTED,
            }
            approval = status_map.get(status_filter.lower())
            if approval:
                qs = qs.filter(approval_status=approval)

        # Paginate (same logic as UserListView)
        try:
            page_size = min(int(request.query_params.get("page_size", _PAGE_SIZE)), 100)
        except (TypeError, ValueError):
            page_size = _PAGE_SIZE
        paginator = Paginator(qs, page_size)
        try:
            page_num = int(request.query_params.get("page", 1))
        except (TypeError, ValueError):
            page_num = 1
        page_obj = paginator.get_page(page_num)

        serializer = TeacherListSerializer(page_obj.object_list, many=True)
        return Response(
            {
                "count": paginator.count,
                "num_pages": paginator.num_pages,
                "page": page_obj.number,
                "page_size": page_size,
                "results": serializer.data,
            }
        )


class TeacherApproveView(APIView):
    """POST /api/admin/teachers/{id}/approve/ — approve a teacher."""

    authentication_classes = [AdminJWTCookieAuthentication]
    permission_classes = [IsActiveAdmin]

    @extend_schema(
        tags=["Admin Teachers"],
        request=TeacherActionSerializer,
        responses={200: {"type": "object", "properties": {"message": {"type": "string"}}}},
    )
    def post(self, request: Request, pk: str) -> Response:
        """Approve a teacher and send a notification email."""
        user = get_object_or_404(User, pk=pk, role=User.Role.TEACHER)

        user.approval_status = User.ApprovalStatus.APPROVED
        user.save(update_fields=["approval_status", "is_approved"])

        from apps.core.tasks import send_teacher_status_email

        send_teacher_status_email.delay(str(user.id), approved=True)
        _audit(request.user, user, "teacher_approve", request)

        return Response(
            {"message": f"Teacher {user.email} has been approved."},
            status=status.HTTP_200_OK,
        )


class TeacherRejectView(APIView):
    """POST /api/admin/teachers/{id}/reject/ — reject a teacher."""

    authentication_classes = [AdminJWTCookieAuthentication]
    permission_classes = [IsActiveAdmin]

    @extend_schema(
        tags=["Admin Teachers"],
        request=TeacherActionSerializer,
        responses={200: {"type": "object", "properties": {"message": {"type": "string"}}}},
    )
    def post(self, request: Request, pk: str) -> Response:
        """Reject a teacher and send a notification email."""
        user = get_object_or_404(User, pk=pk, role=User.Role.TEACHER)

        user.approval_status = User.ApprovalStatus.REJECTED
        user.save(update_fields=["approval_status", "is_approved"])

        from apps.core.tasks import send_teacher_status_email

        send_teacher_status_email.delay(str(user.id), approved=False)
        _audit(request.user, user, "teacher_reject", request)

        return Response(
            {"message": f"Teacher {user.email} has been rejected."},
            status=status.HTTP_200_OK,
        )


# ===========================================================================
# User management — GET/PATCH /api/admin/users/ and sub-actions
# ===========================================================================

_PAGE_SIZE = 20

_ROLE_FILTER_MAP = {
    "admin": User.Role.ADMIN,
    "teacher": User.Role.TEACHER,
    "student": User.Role.STUDENT,
}

_APPROVAL_FILTER_MAP = {
    "pending": User.ApprovalStatus.PENDING,
    "approved": User.ApprovalStatus.APPROVED,
    "rejected": User.ApprovalStatus.REJECTED,
}


def _user_queryset_base() -> QuerySet:
    """Return a base queryset with select_related for profile tables to avoid N+1."""
    return User.objects.select_related("teacher_profile", "student_profile")


class UserListView(APIView):
    """
    GET /api/admin/users/ — paginated, filterable, searchable user list.

    Query params:
      page          integer  (default 1)
      page_size     integer  (default 20, max 100)
      role          admin | teacher | student
      is_active     true | false
      is_email_verified  true | false
      approval_status    pending | approved | rejected
      search        email or full_name substring
      ordering      date_joined | -date_joined | last_login | -last_login | full_name | -full_name
    """

    authentication_classes = [AdminJWTCookieAuthentication]
    permission_classes = [IsActiveAdmin]

    @extend_schema(
        tags=["Admin Users"],
        summary="List all users",
        description="Paginated, filterable, searchable list of all LMS users.",
        parameters=[
            OpenApiParameter("page", int, description="Page number"),
            OpenApiParameter("page_size", int, description="Results per page (max 100)"),
            OpenApiParameter("role", str, enum=["admin", "teacher", "student"]),
            OpenApiParameter("is_active", str, enum=["true", "false"]),
            OpenApiParameter("is_email_verified", str, enum=["true", "false"]),
            OpenApiParameter(
                "approval_status", str, enum=["pending", "approved", "rejected"]
            ),
            OpenApiParameter("search", str, description="Email or name substring"),
            OpenApiParameter(
                "ordering",
                str,
                enum=["date_joined", "-date_joined", "last_login", "-last_login",
                      "full_name", "-full_name"],
            ),
        ],
        responses={200: UserListSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        qs = _user_queryset_base()

        # --- Filters ---
        role = request.query_params.get("role", "").lower()
        if role in _ROLE_FILTER_MAP:
            qs = qs.filter(role=_ROLE_FILTER_MAP[role])

        is_active = request.query_params.get("is_active", "").lower()
        if is_active in ("true", "false"):
            qs = qs.filter(is_active=(is_active == "true"))

        is_verified = request.query_params.get("is_email_verified", "").lower()
        if is_verified in ("true", "false"):
            qs = qs.filter(is_email_verified=(is_verified == "true"))

        approval = request.query_params.get("approval_status", "").lower()
        if approval in _APPROVAL_FILTER_MAP:
            qs = qs.filter(approval_status=_APPROVAL_FILTER_MAP[approval])

        status_param = request.query_params.get("status", "").upper()
        if status_param == "EMAIL_UNVERIFIED":
            qs = qs.filter(is_email_verified=False)
        elif status_param == "PENDING_APPROVAL":
            qs = qs.filter(role=User.Role.TEACHER, approval_status=User.ApprovalStatus.PENDING, is_email_verified=True)
        elif status_param == "REJECTED":
            qs = qs.filter(role=User.Role.TEACHER, approval_status=User.ApprovalStatus.REJECTED)
        elif status_param == "ACTIVE":
            qs = qs.filter(
                is_active=True,
                is_email_verified=True,
            ).filter(
                Q(role__in=[User.Role.STUDENT, User.Role.ADMIN])
                | Q(role=User.Role.TEACHER, approval_status=User.ApprovalStatus.APPROVED)
            )

        # --- Search ---
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(Q(email__icontains=search) | Q(full_name__icontains=search))

        # --- Ordering ---
        allowed_orderings = {
            "date_joined", "-date_joined",
            "last_login", "-last_login",
            "full_name", "-full_name",
        }
        ordering = request.query_params.get("ordering", "-date_joined")
        if ordering not in allowed_orderings:
            ordering = "-date_joined"
        qs = qs.order_by(ordering)

        # --- Pagination ---
        try:
            page_size = min(int(request.query_params.get("page_size", _PAGE_SIZE)), 100)
        except (TypeError, ValueError):
            page_size = _PAGE_SIZE

        paginator = Paginator(qs, page_size)
        try:
            page_num = int(request.query_params.get("page", 1))
        except (TypeError, ValueError):
            page_num = 1
        page_obj = paginator.get_page(page_num)

        serializer = UserListSerializer(page_obj.object_list, many=True)
        return Response(
            {
                "count": paginator.count,
                "num_pages": paginator.num_pages,
                "page": page_obj.number,
                "page_size": page_size,
                "results": serializer.data,
            }
        )


class UserDetailView(APIView):
    """
    GET  /api/admin/users/{id}/ — full user detail including profile
    PATCH /api/admin/users/{id}/ — edit full_name only (never role/password)
    """

    authentication_classes = [AdminJWTCookieAuthentication]
    permission_classes = [IsActiveAdmin]

    def _get_user(self, pk: str) -> User:
        return get_object_or_404(
            _user_queryset_base(), pk=pk
        )

    @extend_schema(
        tags=["Admin Users"],
        summary="Get user detail",
        responses={200: UserDetailSerializer},
    )
    def get(self, request: Request, pk: str) -> Response:
        user = self._get_user(pk)
        return Response(UserDetailSerializer(user).data)

    @extend_schema(
        tags=["Admin Users"],
        summary="Edit user",
        description="Update full_name only. Role and password cannot be changed here.",
        request=UserUpdateSerializer,
        responses={
            200: UserDetailSerializer,
            400: OpenApiResponse(description="Validation error"),
            403: OpenApiResponse(description="Cannot edit admin accounts"),
        },
    )
    def patch(self, request: Request, pk: str) -> Response:
        user = self._get_user(pk)

        # Safeguard: admins cannot be edited by other admins
        if user.role == User.Role.ADMIN:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Admin accounts cannot be modified through this endpoint.")

        serializer = UserUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        # Only allow full_name via PATCH; is_active has its own endpoints
        allowed = {k: v for k, v in serializer.validated_data.items() if k == "full_name"}
        if not allowed:
            return Response(UserDetailSerializer(user).data)
        for field, value in allowed.items():
            setattr(user, field, value)
        user.save(update_fields=list(allowed.keys()))

        _audit(request.user, user, "edit_user", request, metadata={"fields": list(allowed.keys())})
        return Response(UserDetailSerializer(user).data)

    @extend_schema(
        tags=["Admin Users"],
        summary="Soft delete user",
        description="Soft deletes the user by deactivating their account and revoking all active tokens. Hard delete is disallowed to preserve foreign key references.",
        responses={
            200: OpenApiResponse(description="User soft-deleted / deactivated"),
            403: OpenApiResponse(description="Cannot delete yourself or the last active admin"),
        },
    )
    def delete(self, request: Request, pk: str) -> Response:
        from rest_framework.exceptions import PermissionDenied

        user = self._get_user(pk)

        # Safeguard: cannot delete yourself
        if str(user.id) == str(request.user.id):
            raise PermissionDenied("You cannot delete your own account.")

        # Safeguard: cannot delete last active admin
        if user.role == User.Role.ADMIN:
            active_admin_count = User.objects.filter(
                role=User.Role.ADMIN, is_active=True
            ).exclude(pk=user.pk).count()
            if active_admin_count == 0:
                raise PermissionDenied(
                    "Cannot delete the last active administrator account."
                )

        user.is_active = False
        user.save(update_fields=["is_active"])
        invalidate_all_user_tokens(user.id)

        _audit(request.user, user, "soft_delete", request)
        return Response({"message": f"User {user.email} has been deactivated (soft-deleted)."})


class UserActivateView(APIView):
    """POST /api/admin/users/{id}/activate/"""

    authentication_classes = [AdminJWTCookieAuthentication]
    permission_classes = [IsActiveAdmin]

    @extend_schema(
        tags=["Admin Users"],
        summary="Activate user account",
        request=None,
        responses={200: OpenApiResponse(description="User activated")},
    )
    def post(self, request: Request, pk: str) -> Response:
        user = get_object_or_404(User, pk=pk)

        if str(user.id) == str(request.user.id):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You cannot activate yourself.")

        user.is_active = True
        user.save(update_fields=["is_active"])
        invalidate_user_state_cache(user.id)

        _audit(request.user, user, "activate", request)
        return Response({"message": f"User {user.email} has been activated."})


class UserDeactivateView(APIView):
    """POST /api/admin/users/{id}/deactivate/ — also revokes all tokens."""

    authentication_classes = [AdminJWTCookieAuthentication]
    permission_classes = [IsActiveAdmin]

    @extend_schema(
        tags=["Admin Users"],
        summary="Deactivate user account",
        description="Deactivates the user and immediately revokes all their tokens via tokens_valid_after.",
        request=None,
        responses={
            200: OpenApiResponse(description="User deactivated"),
            403: OpenApiResponse(description="Cannot deactivate yourself or last active admin"),
        },
    )
    def post(self, request: Request, pk: str) -> Response:
        from rest_framework.exceptions import PermissionDenied

        user = get_object_or_404(User, pk=pk)

        # Safeguard: cannot deactivate yourself
        if str(user.id) == str(request.user.id):
            raise PermissionDenied("You cannot deactivate your own account.")

        # Safeguard: cannot deactivate the last active admin
        if user.role == User.Role.ADMIN:
            active_admin_count = User.objects.filter(
                role=User.Role.ADMIN, is_active=True
            ).exclude(pk=user.pk).count()
            if active_admin_count == 0:
                raise PermissionDenied(
                    "Cannot deactivate the last active administrator account."
                )

        user.is_active = False
        user.save(update_fields=["is_active"])

        # Revoke all existing tokens immediately
        invalidate_all_user_tokens(user.id)

        _audit(request.user, user, "deactivate", request)
        return Response({"message": f"User {user.email} has been deactivated and all tokens revoked."})


class UserResendVerificationView(APIView):
    """POST /api/admin/users/{id}/resend-verification/ — send a fresh signup OTP."""

    authentication_classes = [AdminJWTCookieAuthentication]
    permission_classes = [IsActiveAdmin]

    @extend_schema(
        tags=["Admin Users"],
        summary="Resend email verification to user",
        request=None,
        responses={
            200: OpenApiResponse(description="Verification email sent"),
            400: OpenApiResponse(description="User already verified or invalid state"),
        },
    )
    def post(self, request: Request, pk: str) -> Response:
        from rest_framework.exceptions import ValidationError

        from apps.authentication.services import OTPService
        from apps.core.exceptions import OTPCooldownError
        from apps.core.tasks import send_otp_email

        user = get_object_or_404(User, pk=pk)

        if user.is_email_verified:
            raise ValidationError({"detail": "User's email is already verified."})

        role = user.role.lower()
        try:
            otp = OTPService.generate_otp("signup_verify", user.email)
            send_otp_email.delay(
                user.email, otp, "account verification",
                role=role, purpose_slug="verify-email",
            )
        except OTPCooldownError:
            pass  # cooldown is OK; admin triggered it recently

        _audit(request.user, user, "resend_verification", request)
        return Response({"message": f"Verification email sent to {user.email}."})
