"""URL patterns for admin teacher-management and user-management endpoints."""

from django.urls import path

from apps.accounts.views import (
    TeacherApproveView,
    TeacherListView,
    TeacherRejectView,
    UserActivateView,
    UserDeactivateView,
    UserDetailView,
    UserListView,
    UserResendVerificationView,
)

app_name = "accounts"

# Mounted at /api/admin/teachers/
teacher_urlpatterns = [
    path("", TeacherListView.as_view(), name="teacher-list"),
    path("<uuid:pk>/approve/", TeacherApproveView.as_view(), name="teacher-approve"),
    path("<uuid:pk>/reject/", TeacherRejectView.as_view(), name="teacher-reject"),
]

# Mounted at /api/admin/users/
user_urlpatterns = [
    path("", UserListView.as_view(), name="user-list"),
    path("<uuid:pk>/", UserDetailView.as_view(), name="user-detail"),
    path("<uuid:pk>/activate/", UserActivateView.as_view(), name="user-activate"),
    path("<uuid:pk>/deactivate/", UserDeactivateView.as_view(), name="user-deactivate"),
    path(
        "<uuid:pk>/resend-verification/",
        UserResendVerificationView.as_view(),
        name="user-resend-verification",
    ),
]

# Default for legacy include("apps.accounts.urls")
urlpatterns = teacher_urlpatterns

