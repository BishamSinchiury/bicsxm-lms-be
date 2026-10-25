"""
Root URL configuration for LMS.

Mounts:
- /api/schema/, /api/docs/, /api/redoc/ -> OpenAPI documentation
- /api/{student,teacher,admin}/auth/   -> Role-isolated authentication
- /api/admin/teachers/                 -> Admin teacher management
- /api/{admin,teacher,student}/dashboard/ping/ -> Protected dashboard proof endpoints
- /api/{admin,teacher,student}/courses/ -> Course management (MongoDB-backed)
- /api/health/                         -> Service health check
- /admin/                              -> Django admin
"""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.accounts.urls import teacher_urlpatterns, user_urlpatterns
from apps.courses.urls import (
    admin_courses_urlpatterns,
    student_courses_urlpatterns,
    teacher_courses_urlpatterns,
)

urlpatterns = [
    # Django Admin
    path("admin/", admin.site.urls),
    # OpenAPI / Swagger / ReDoc
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # Role-based Authentication Endpoints
    path("api/", include("apps.authentication.urls")),
    # Admin Teacher Management
    path("api/admin/teachers/", include((teacher_urlpatterns, "admin-teachers"))),
    # Admin User Management
    path("api/admin/users/", include((user_urlpatterns, "admin-users"))),
    # Role Dashboard Ping Endpoints
    path("api/", include("apps.core.urls")),
    # ── Courses (MongoDB-backed) ─────────────────────────────────────────────
    path("api/teacher/courses/", include((teacher_courses_urlpatterns, "teacher-courses"))),
    path("api/admin/courses/", include((admin_courses_urlpatterns, "admin-courses"))),
    path("api/student/courses/", include((student_courses_urlpatterns, "student-courses"))),
    # Service health check
    path("api/health/", include("apps.core.health_urls")),
]
