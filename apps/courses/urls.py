"""
URL patterns for the Courses app.

Imported by config/urls.py and mounted under the role-prefixed paths:
  /api/teacher/courses/   → teacher_courses_urlpatterns
  /api/admin/courses/     → admin_courses_urlpatterns
  /api/student/courses/   → student_courses_urlpatterns
"""

from __future__ import annotations

from django.urls import path

from apps.courses import views

# ---------------------------------------------------------------------------
# Teacher
# ---------------------------------------------------------------------------

teacher_courses_urlpatterns = [
    # Course CRUD
    path("", views.TeacherCourseListCreateView.as_view(), name="teacher-course-list"),
    path("<str:pk>/", views.TeacherCourseDetailView.as_view(), name="teacher-course-detail"),
    path("<str:pk>/publish/", views.TeacherCoursePublishView.as_view(), name="teacher-course-publish"),
    path("<str:pk>/archive/", views.TeacherCourseArchiveView.as_view(), name="teacher-course-archive"),
    path("<str:pk>/unpublish/", views.TeacherCourseUnpublishView.as_view(), name="teacher-course-unpublish"),
    # Units
    path("<str:course_pk>/units/", views.TeacherUnitListCreateView.as_view(), name="teacher-unit-list"),
    path("<str:course_pk>/units/reorder/", views.TeacherUnitReorderView.as_view(), name="teacher-unit-reorder"),
    path("<str:course_pk>/units/<str:unit_pk>/", views.TeacherUnitDetailView.as_view(), name="teacher-unit-detail"),
    # Lessons
    path(
        "<str:course_pk>/units/<str:unit_pk>/lessons/",
        views.TeacherLessonListCreateView.as_view(),
        name="teacher-lesson-list",
    ),
    path(
        "<str:course_pk>/units/<str:unit_pk>/lessons/reorder/",
        views.TeacherLessonReorderView.as_view(),
        name="teacher-lesson-reorder",
    ),
    path(
        "<str:course_pk>/units/<str:unit_pk>/lessons/<str:lesson_pk>/",
        views.TeacherLessonDetailView.as_view(),
        name="teacher-lesson-detail",
    ),
]

# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

admin_courses_urlpatterns = [
    path("", views.AdminCourseListCreateView.as_view(), name="admin-course-list"),
    path("<str:pk>/", views.AdminCourseDetailView.as_view(), name="admin-course-detail"),
    path("<str:pk>/publish/", views.AdminCoursePublishView.as_view(), name="admin-course-publish"),
    path("<str:pk>/archive/", views.AdminCourseArchiveView.as_view(), name="admin-course-archive"),
    path("<str:pk>/unpublish/", views.AdminCourseUnpublishView.as_view(), name="admin-course-unpublish"),
    # Units
    path("<str:course_pk>/units/", views.AdminUnitListCreateView.as_view(), name="admin-unit-list"),
    path("<str:course_pk>/units/reorder/", views.AdminUnitReorderView.as_view(), name="admin-unit-reorder"),
    path("<str:course_pk>/units/<str:unit_pk>/", views.AdminUnitDetailView.as_view(), name="admin-unit-detail"),
    # Lessons
    path(
        "<str:course_pk>/units/<str:unit_pk>/lessons/",
        views.AdminLessonListCreateView.as_view(),
        name="admin-lesson-list",
    ),
    path(
        "<str:course_pk>/units/<str:unit_pk>/lessons/reorder/",
        views.AdminLessonReorderView.as_view(),
        name="admin-lesson-reorder",
    ),
    path(
        "<str:course_pk>/units/<str:unit_pk>/lessons/<str:lesson_pk>/",
        views.AdminLessonDetailView.as_view(),
        name="admin-lesson-detail",
    ),
]

# ---------------------------------------------------------------------------
# Student
# ---------------------------------------------------------------------------

student_courses_urlpatterns = [
    path("", views.StudentCourseListView.as_view(), name="student-course-list"),
    path("<str:pk>/", views.StudentCourseDetailView.as_view(), name="student-course-detail"),
    path("<str:pk>/outline/", views.StudentCourseOutlineView.as_view(), name="student-course-outline"),
]
