"""
Core URLs — dashboard ping routes for role proof.
"""

from django.urls import path

from apps.core.views import (
    AdminDashboardPingView,
    StudentDashboardPingView,
    TeacherDashboardPingView,
)

urlpatterns = [
    path("admin/dashboard/ping/", AdminDashboardPingView.as_view(), name="admin-dashboard-ping"),
    path(
        "teacher/dashboard/ping/",
        TeacherDashboardPingView.as_view(),
        name="teacher-dashboard-ping",
    ),
    path(
        "student/dashboard/ping/",
        StudentDashboardPingView.as_view(),
        name="student-dashboard-ping",
    ),
]
