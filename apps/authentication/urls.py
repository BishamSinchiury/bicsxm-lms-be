"""
Authentication URL configuration for Student, Teacher, and Admin portals.
"""

from django.urls import include, path

from apps.authentication.views import (
    AdminLoginView,
    AdminLogoutView,
    AdminMeView,
    AdminPasswordResetConfirmView,
    AdminPasswordResetRequestView,
    AdminResendOTPView,
    AdminTokenRefreshView,
    AdminVerifyOTPView,
    StudentLoginView,
    StudentLogoutView,
    StudentMeView,
    StudentPasswordResetConfirmView,
    StudentPasswordResetRequestView,
    StudentResendOTPView,
    StudentSignupView,
    StudentTokenRefreshView,
    StudentVerifyOTPView,
    TeacherLoginView,
    TeacherLogoutView,
    TeacherMeView,
    TeacherPasswordResetConfirmView,
    TeacherPasswordResetRequestView,
    TeacherResendOTPView,
    TeacherSignupView,
    TeacherTokenRefreshView,
    TeacherVerifyOTPView,
)

student_auth_patterns = [
    path("signup/", StudentSignupView.as_view(), name="student-signup"),
    path("verify-otp/", StudentVerifyOTPView.as_view(), name="student-verify-otp"),
    path("resend-otp/", StudentResendOTPView.as_view(), name="student-resend-otp"),
    path("login/", StudentLoginView.as_view(), name="student-login"),
    path("token/refresh/", StudentTokenRefreshView.as_view(), name="student-token-refresh"),
    path("logout/", StudentLogoutView.as_view(), name="student-logout"),
    path("me/", StudentMeView.as_view(), name="student-me"),
    path(
        "password-reset/request/",
        StudentPasswordResetRequestView.as_view(),
        name="student-password-reset-request",
    ),
    path(
        "password-reset/confirm/",
        StudentPasswordResetConfirmView.as_view(),
        name="student-password-reset-confirm",
    ),
]

teacher_auth_patterns = [
    path("signup/", TeacherSignupView.as_view(), name="teacher-signup"),
    path("verify-otp/", TeacherVerifyOTPView.as_view(), name="teacher-verify-otp"),
    path("resend-otp/", TeacherResendOTPView.as_view(), name="teacher-resend-otp"),
    path("login/", TeacherLoginView.as_view(), name="teacher-login"),
    path("token/refresh/", TeacherTokenRefreshView.as_view(), name="teacher-token-refresh"),
    path("logout/", TeacherLogoutView.as_view(), name="teacher-logout"),
    path("me/", TeacherMeView.as_view(), name="teacher-me"),
    path(
        "password-reset/request/",
        TeacherPasswordResetRequestView.as_view(),
        name="teacher-password-reset-request",
    ),
    path(
        "password-reset/confirm/",
        TeacherPasswordResetConfirmView.as_view(),
        name="teacher-password-reset-confirm",
    ),
]

admin_auth_patterns = [
    path("login/", AdminLoginView.as_view(), name="admin-login"),
    path("login/verify-otp/", AdminVerifyOTPView.as_view(), name="admin-login-verify-otp"),
    path("resend-otp/", AdminResendOTPView.as_view(), name="admin-resend-otp"),
    path("token/refresh/", AdminTokenRefreshView.as_view(), name="admin-token-refresh"),
    path("logout/", AdminLogoutView.as_view(), name="admin-logout"),
    path("me/", AdminMeView.as_view(), name="admin-me"),
    path(
        "password-reset/request/",
        AdminPasswordResetRequestView.as_view(),
        name="admin-password-reset-request",
    ),
    path(
        "password-reset/confirm/",
        AdminPasswordResetConfirmView.as_view(),
        name="admin-password-reset-confirm",
    ),
]

urlpatterns = [
    path("student/auth/", include((student_auth_patterns, "student-auth"))),
    path("teacher/auth/", include((teacher_auth_patterns, "teacher-auth"))),
    path("admin/auth/", include((admin_auth_patterns, "admin-auth"))),
]
