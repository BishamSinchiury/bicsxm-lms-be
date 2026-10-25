"""
Courses application configuration.

``default_auto_field`` is set to ObjectIdAutoField so that every model in this
app gets a MongoDB ObjectId primary key instead of the project-wide BigAutoField
used for PostgreSQL models.
"""

from django.apps import AppConfig


class CoursesConfig(AppConfig):
    name = "apps.courses"
    verbose_name = "Courses"
    # Per-app override — does NOT affect other apps.
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
