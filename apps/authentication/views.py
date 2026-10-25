"""
Authentication views for Student, Teacher, and Admin portals.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.authentication.cookie_utils import clear_auth_cookies, set_auth_cookies
from apps.authentication.serializers import (
    AdminResendOTPSerializer,
    AdminVerifyOTPSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    SignupSerializer,
    UserMeSerializer,
    VerifyOTPSerializer,
)
from apps.authentication.services import OTPService
from apps.authentication.tokens import (
    determine_token_scope,
    generate_tokens_for_user,
    verify_refresh_token,
)
from apps.core.authentication import (
    AdminJWTCookieAuthentication,
    StudentJWTCookieAuthentication,
    TeacherJWTCookieAuthentication,
)
from apps.core.exceptions import OTPCooldownError
from apps.core.permissions import AllowLimitedScope, IsActiveAdmin
from apps.core.tasks import send_otp_email
from apps.core.throttles import (
    LoginEmailRateThrottle,
    LoginIPRateThrottle,
    OTPEmailRateThrottle,
    OTPIPRateThrottle,
)
from apps.core.utils import (
    blacklist_token_jti,
    get_user_status,
    invalidate_all_user_tokens,
)


class BaseAuthView(APIView):
    """Base class providing common role identification."""

    role: str = ""
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []


# ===========================================================================
# Student & Teacher Auth Views
# ===========================================================================


class RoleSignupView(BaseAuthView):
    """
    Signup endpoint for Students and Teachers.
    Creates account and sends verification OTP.
    Also sets limited-scope cookies so the user can verify immediately.
    """

    throttle_classes = [OTPEmailRateThrottle, OTPIPRateThrottle]

    @extend_schema(
        summary="User signup",
        description="Register a new student or teacher. Automatically sends an email verification code and sets limited-scope session cookies.",
        request=SignupSerializer,
        responses={
            201: OpenApiResponse(description="Account created; OTP sent"),
            200: OpenApiResponse(description="Existing unverified account; OTP resent"),
            400: OpenApiResponse(description="Validation error"),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        full_name = serializer.validated_data["full_name"]
        password = serializer.validated_data["password"]
        target_role = self.role.upper()

        existing_user = User.objects.filter(email=email).first()
        if existing_user:
            if existing_user.is_email_verified:
                raise exceptions.ValidationError(
                    {"email": ["An account with this email already exists."]}
                )
            # Unverified account exists — update credentials and resend OTP
            existing_user.full_name = full_name
            existing_user.set_password(password)
            existing_user.role = target_role
            existing_user.save()
            user = existing_user
            status_code = status.HTTP_200_OK
            msg = "Account already exists but was unverified. Verification code resent to your email."
        else:
            user = User.objects.create_user(
                email=email,
                password=password,
                full_name=full_name,
                role=target_role,
            )
            status_code = status.HTTP_201_CREATED
            msg = "Account created. Verification code sent to your email."

        # Generate and dispatch OTP
        otp = OTPService.generate_otp("signup_verify", email)
        send_otp_email.delay(
            email, otp, "account verification",
            role=self.role, purpose_slug="verify-email",
        )

        # Set limited-scope cookies immediately per amendment 1
        tokens = generate_tokens_for_user(user, role=self.role, scope="limited")
        response = Response(
            {
                "message": msg,
                "status": get_user_status(user),
                "scope": "limited",
            },
            status=status_code,
        )
        set_auth_cookies(response, self.role, tokens["access_token"], tokens["refresh_token"])
        return response


class RoleLoginView(BaseAuthView):
    """
    Login endpoint for Students and Teachers.
    Authenticates email and password, auto-sends OTP if unverified, and sets role cookies.
    """

    throttle_classes = [LoginEmailRateThrottle, LoginIPRateThrottle]

    @extend_schema(
        summary="User login",
        description="Authenticate student or teacher. Sets HttpOnly cookies. If unverified, auto-dispatches OTP.",
        request=LoginSerializer,
        responses={
            200: OpenApiResponse(description="Login successful"),
            400: OpenApiResponse(description="Validation error"),
            401: OpenApiResponse(description="Authentication failed"),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        user = User.objects.filter(email=email).first()
        if not user or not user.check_password(password):
            raise exceptions.AuthenticationFailed("Invalid email or password.")

        if user.role != self.role.upper():
            raise exceptions.AuthenticationFailed("Invalid credentials for this portal.")

        if not user.is_active:
            raise exceptions.AuthenticationFailed("This account has been deactivated.")

        user_status = get_user_status(user)

        # Auto-send OTP if unverified (respecting cooldown)
        if user_status == "EMAIL_UNVERIFIED":
            try:
                otp = OTPService.generate_otp("signup_verify", user.email)
                send_otp_email.delay(
                    user.email, otp, "account verification",
                    role=self.role, purpose_slug="verify-email",
                )
            except OTPCooldownError:
                pass

        # Determine scope: ACTIVE -> full; unverified/pending/rejected -> limited
        scope = determine_token_scope(user)
        tokens = generate_tokens_for_user(user, role=self.role, scope=scope)

        response = Response(
            {
                "message": "Login successful.",
                "status": user_status,
                "scope": scope,
            },
            status=status.HTTP_200_OK,
        )
        set_auth_cookies(response, self.role, tokens["access_token"], tokens["refresh_token"])
        return response


class RoleVerifyOTPView(BaseAuthView):
    """
    Verify signup OTP for the authenticated user.
    Upgrades token scope to full upon verification (if approved).
    """

    permission_classes = [AllowLimitedScope]

    @extend_schema(
        summary="Verify email OTP",
        description="Verify 6-digit email OTP for the authenticated student or teacher.",
        request=VerifyOTPSerializer,
        responses={
            200: OpenApiResponse(description="Email verified successfully"),
            400: OpenApiResponse(description="Invalid or expired OTP"),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        otp = serializer.validated_data["otp"]
        user = request.user

        OTPService.verify_otp("signup_verify", user.email, otp)

        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])

        new_status = get_user_status(user)
        new_scope = determine_token_scope(user)

        # Issue upgraded tokens
        tokens = generate_tokens_for_user(user, role=self.role, scope=new_scope)
        response = Response(
            {
                "message": "Email verified successfully.",
                "status": new_status,
                "scope": new_scope,
            },
            status=status.HTTP_200_OK,
        )
        set_auth_cookies(response, self.role, tokens["access_token"], tokens["refresh_token"])
        return response


class RoleResendOTPView(BaseAuthView):
    """
    Resend verification OTP for the authenticated user (cooldown enforced).
    """

    permission_classes = [AllowLimitedScope]
    throttle_classes = [OTPEmailRateThrottle, OTPIPRateThrottle]

    @extend_schema(
        summary="Resend verification OTP",
        description="Resend verification code to the authenticated user's email. Enforces a 60-second cooldown.",
        request=None,
        responses={
            200: OpenApiResponse(description="Verification code resent"),
            429: OpenApiResponse(description="Cooldown active"),
        },
    )
    def post(self, request: Request) -> Response:
        user = request.user
        if user.is_email_verified:
            return Response(
                {"message": "Email is already verified."},
                status=status.HTTP_200_OK,
            )

        otp = OTPService.generate_otp("signup_verify", user.email)
        send_otp_email.delay(
            user.email, otp, "account verification",
            role=self.role, purpose_slug="verify-email",
        )

        return Response(
            {"message": "Verification code resent."},
            status=status.HTTP_200_OK,
        )


class RoleTokenRefreshView(BaseAuthView):
    """
    Refresh access token from the role's refresh cookie.
    Re-evaluates user status dynamically and rotates the refresh token.
    """

    @extend_schema(
        summary="Refresh access token",
        description="Refresh access token using HttpOnly refresh cookie. Evaluates approval and account state changes.",
        request=None,
        responses={
            200: OpenApiResponse(description="Token refreshed"),
            401: OpenApiResponse(description="Invalid or expired refresh token"),
        },
    )
    def post(self, request: Request) -> Response:
        cookie_name = f"{self.role}_refresh"
        raw_refresh = request.COOKIES.get(cookie_name)
        if not raw_refresh:
            raise exceptions.AuthenticationFailed("Refresh token cookie not provided.")

        payload = verify_refresh_token(raw_refresh, self.role)
        old_jti = payload.get("jti")
        user_id = payload.get("user_id")

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed("User not found.") from None

        if not user.is_active:
            raise exceptions.AuthenticationFailed("User account is inactive.")

        # Blacklist old refresh token (rotation)
        if old_jti:
            blacklist_token_jti(
                old_jti,
                self.role,
                int(settings.JWT_REFRESH_TOKEN_LIFETIME.total_seconds()),
            )

        new_status = get_user_status(user)
        new_scope = determine_token_scope(user)
        tokens = generate_tokens_for_user(user, role=self.role, scope=new_scope)

        response = Response(
            {
                "message": "Token refreshed.",
                "status": new_status,
                "scope": new_scope,
            },
            status=status.HTTP_200_OK,
        )
        set_auth_cookies(response, self.role, tokens["access_token"], tokens["refresh_token"])
        return response


class RoleLogoutView(BaseAuthView):
    """
    Logout: Blacklists the access token jti and refresh token jti in Redis,
    and clears only this role's cookies.
    """

    permission_classes = [AllowLimitedScope]

    @extend_schema(
        summary="User logout",
        description="Revoke access/refresh tokens in Redis and delete role-scoped cookies.",
        request=None,
        responses={200: OpenApiResponse(description="Logged out successfully")},
    )
    def post(self, request: Request) -> Response:
        payload = getattr(request, "auth_token_payload", {}) or {}
        access_jti = payload.get("jti")
        if access_jti:
            blacklist_token_jti(
                access_jti,
                self.role,
                int(settings.JWT_ACCESS_TOKEN_LIFETIME.total_seconds()),
            )

        # Also blacklist refresh token if present
        refresh_cookie_name = f"{self.role}_refresh"
        raw_refresh = request.COOKIES.get(refresh_cookie_name)
        if raw_refresh:
            try:
                refresh_payload = verify_refresh_token(raw_refresh, self.role)
                refresh_jti = refresh_payload.get("jti")
                if refresh_jti:
                    blacklist_token_jti(
                        refresh_jti,
                        self.role,
                        int(settings.JWT_REFRESH_TOKEN_LIFETIME.total_seconds()),
                    )
            except Exception:
                pass

        response = Response({"message": "Logged out successfully."}, status=status.HTTP_200_OK)
        clear_auth_cookies(response, self.role)
        return response


class RoleMeView(BaseAuthView):
    """
    Return profile and live status for authenticated user.
    """

    permission_classes = [AllowLimitedScope]

    @extend_schema(
        summary="Current user profile",
        description="Retrieve account details, role, status, and profile information.",
        responses={200: UserMeSerializer},
    )
    def get(self, request: Request) -> Response:
        serializer = UserMeSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class RolePasswordResetRequestView(BaseAuthView):
    """
    Request password reset OTP. Returns generic response to prevent email harvesting.
    """

    throttle_classes = [OTPEmailRateThrottle, OTPIPRateThrottle]

    @extend_schema(
        summary="Request password reset",
        description="Dispatch a password reset OTP. Always returns a generic response.",
        request=PasswordResetRequestSerializer,
        responses={200: OpenApiResponse(description="Generic confirmation response")},
    )
    def post(self, request: Request) -> Response:
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        user = User.objects.filter(email=email, role=self.role.upper()).first()

        if user and user.is_active:
            try:
                otp = OTPService.generate_otp("password_reset", email)
                send_otp_email.delay(
                    email, otp, "password reset",
                    role=self.role, purpose_slug="reset-password",
                )
            except OTPCooldownError:
                pass

        return Response(
            {
                "message": (
                    "If an account with that email exists, a password reset code has been sent."
                )
            },
            status=status.HTTP_200_OK,
        )


class RolePasswordResetConfirmView(BaseAuthView):
    """
    Confirm password reset with OTP and invalidate all prior tokens.
    """

    @extend_schema(
        summary="Confirm password reset",
        description="Set a new password using OTP verification. Invalidates all active tokens.",
        request=PasswordResetConfirmSerializer,
        responses={
            200: OpenApiResponse(description="Password reset successful"),
            400: OpenApiResponse(description="Invalid OTP or password validation error"),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        otp = serializer.validated_data["otp"]
        new_password = serializer.validated_data["new_password"]

        OTPService.verify_otp("password_reset", email, otp)

        user = User.objects.filter(email=email, role=self.role.upper()).first()
        if not user:
            raise exceptions.NotFound("Account not found.")

        user.set_password(new_password)
        user.save()

        # Invalidate all prior tokens via Redis timestamp cutoff (amendment 4)
        invalidate_all_user_tokens(user.id)

        return Response(
            {"message": "Password reset successful. You may now log in with your new password."},
            status=status.HTTP_200_OK,
        )


# ===========================================================================
# Admin Auth Views
# ===========================================================================


class AdminLoginView(BaseAuthView):
    """
    Step 1 of Admin 2-step authentication:
    Verifies credentials and dispatches an OTP. Sets no cookies.
    """

    role = "admin"
    throttle_classes = [LoginEmailRateThrottle, LoginIPRateThrottle]

    @extend_schema(
        tags=["Admin Auth"],
        summary="Admin login (Step 1)",
        description="Verify credentials and dispatch admin OTP. Does not issue tokens.",
        request=LoginSerializer,
        responses={
            200: OpenApiResponse(description="OTP sent; requires_otp=true"),
            401: OpenApiResponse(description="Invalid credentials"),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        user = User.objects.filter(email=email).first()
        if not user or not user.check_password(password):
            raise exceptions.AuthenticationFailed("Invalid email or password.")

        if user.role != User.Role.ADMIN:
            raise exceptions.AuthenticationFailed("Admin credentials required.")

        if not user.is_active:
            raise exceptions.AuthenticationFailed("Admin account is deactivated.")

        otp = OTPService.generate_otp("admin_login", email)
        send_otp_email.delay(
            email, otp, "admin portal login",
            role="admin", purpose_slug="login/verify-otp",
        )

        return Response(
            {
                "message": "Admin verification code sent to your email.",
                "requires_otp": True,
            },
            status=status.HTTP_200_OK,
        )


class AdminVerifyOTPView(BaseAuthView):
    """
    Step 2 of Admin 2-step authentication:
    Verifies the OTP and email, sets admin cookies.
    """

    role = "admin"
    throttle_classes = [OTPEmailRateThrottle, OTPIPRateThrottle]

    @extend_schema(
        tags=["Admin Auth"],
        summary="Admin login OTP verification (Step 2)",
        description="Verify OTP from Step 1 and set admin HttpOnly session cookies.",
        request=AdminVerifyOTPSerializer,
        responses={
            200: OpenApiResponse(description="Admin login successful"),
            400: OpenApiResponse(description="Invalid or expired OTP"),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = AdminVerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        otp = serializer.validated_data["otp"]

        OTPService.verify_otp("admin_login", email, otp)

        user = User.objects.filter(email=email, role=User.Role.ADMIN).first()
        if not user or not user.is_active:
            raise exceptions.AuthenticationFailed("Admin user not found or inactive.")

        tokens = generate_tokens_for_user(user, role="admin", scope="full")
        response = Response(
            {
                "message": "Admin login successful.",
                "status": "ACTIVE",
                "scope": "full",
            },
            status=status.HTTP_200_OK,
        )
        set_auth_cookies(response, "admin", tokens["access_token"], tokens["refresh_token"])
        return response


class AdminResendOTPView(BaseAuthView):
    """
    Resend admin login OTP without requiring cookies (per amendment 2).
    Accepts email in body, returns generic response, enforces cooldown and rate limits.
    """

    role = "admin"
    throttle_classes = [OTPEmailRateThrottle, OTPIPRateThrottle]

    @extend_schema(
        tags=["Admin Auth"],
        summary="Resend admin login OTP",
        description="Resend OTP code for admin login step 2. Enforces cooldown and generic response.",
        request=AdminResendOTPSerializer,
        responses={200: OpenApiResponse(description="Generic confirmation response")},
    )
    def post(self, request: Request) -> Response:
        serializer = AdminResendOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        user = User.objects.filter(email=email, role=User.Role.ADMIN).first()

        if user and user.is_active:
            try:
                otp = OTPService.generate_otp("admin_login", email)
                send_otp_email.delay(
                    email, otp, "admin portal login",
                    role="admin", purpose_slug="login/verify-otp",
                )
            except OTPCooldownError:
                pass

        return Response(
            {
                "message": "If an admin account exists with this email, a verification code has been resent."
            },
            status=status.HTTP_200_OK,
        )


# ===========================================================================
# Concrete Role Views for URL Routing
# ===========================================================================


# Student
class StudentSignupView(RoleSignupView):
    role = "student"


class StudentLoginView(RoleLoginView):
    role = "student"


class StudentVerifyOTPView(RoleVerifyOTPView):
    role = "student"
    authentication_classes = [StudentJWTCookieAuthentication]


class StudentResendOTPView(RoleResendOTPView):
    role = "student"
    authentication_classes = [StudentJWTCookieAuthentication]


class StudentTokenRefreshView(RoleTokenRefreshView):
    role = "student"


class StudentLogoutView(RoleLogoutView):
    role = "student"
    authentication_classes = [StudentJWTCookieAuthentication]


class StudentMeView(RoleMeView):
    role = "student"
    authentication_classes = [StudentJWTCookieAuthentication]


class StudentPasswordResetRequestView(RolePasswordResetRequestView):
    role = "student"


class StudentPasswordResetConfirmView(RolePasswordResetConfirmView):
    role = "student"


# Teacher
class TeacherSignupView(RoleSignupView):
    role = "teacher"


class TeacherLoginView(RoleLoginView):
    role = "teacher"


class TeacherVerifyOTPView(RoleVerifyOTPView):
    role = "teacher"
    authentication_classes = [TeacherJWTCookieAuthentication]


class TeacherResendOTPView(RoleResendOTPView):
    role = "teacher"
    authentication_classes = [TeacherJWTCookieAuthentication]


class TeacherTokenRefreshView(RoleTokenRefreshView):
    role = "teacher"


class TeacherLogoutView(RoleLogoutView):
    role = "teacher"
    authentication_classes = [TeacherJWTCookieAuthentication]


class TeacherMeView(RoleMeView):
    role = "teacher"
    authentication_classes = [TeacherJWTCookieAuthentication]


class TeacherPasswordResetRequestView(RolePasswordResetRequestView):
    role = "teacher"


class TeacherPasswordResetConfirmView(RolePasswordResetConfirmView):
    role = "teacher"


# Admin Concrete
class AdminTokenRefreshView(RoleTokenRefreshView):
    role = "admin"


class AdminLogoutView(RoleLogoutView):
    role = "admin"
    authentication_classes = [AdminJWTCookieAuthentication]
    permission_classes = [IsActiveAdmin]


class AdminMeView(RoleMeView):
    role = "admin"
    authentication_classes = [AdminJWTCookieAuthentication]
    permission_classes = [IsActiveAdmin]


class AdminPasswordResetRequestView(RolePasswordResetRequestView):
    role = "admin"


class AdminPasswordResetConfirmView(RolePasswordResetConfirmView):
    role = "admin"
