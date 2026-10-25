"""
MongoDB-backed models for the Courses app.

Three collections:
  - Course    — top-level course document
  - Unit      — ordered grouping of lessons within a course
  - Lesson    — individual piece of content within a unit

``created_by`` on Course is a plain CharField storing the Postgres User UUID
string.  There is intentionally no Django ForeignKey across databases.
"""

from __future__ import annotations

from django.db import models
from django_mongodb_backend.fields import ObjectIdField

# ---------------------------------------------------------------------------
# Course
# ---------------------------------------------------------------------------


class Course(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"
        ARCHIVED = "ARCHIVED", "Archived"

    # PK is ObjectId — injected automatically via CoursesConfig.default_auto_field
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True)
    description = models.TextField(blank=True)
    thumbnail_url = models.URLField(blank=True)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    # Reference to accounts.User — stored as UUID string, never a real FK.
    created_by = models.CharField(max_length=36, db_index=True)
    # Denormalised for display (populated via resolve_created_by_names service).
    created_by_name = models.CharField(max_length=255, blank=True)

    # Simple list of tag strings stored as an array field.
    tags = models.JSONField(default=list, blank=True)

    # Denormalised counters — kept consistent by recompute_course_stats().
    unit_count = models.PositiveIntegerField(default=0)
    lesson_count = models.PositiveIntegerField(default=0)
    total_duration_seconds = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "courses"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_by"]),
            models.Index(fields=["status"]),
            models.Index(fields=["slug"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} [{self.status}]"


# ---------------------------------------------------------------------------
# Unit
# ---------------------------------------------------------------------------


class Unit(models.Model):
    # ObjectId reference to the parent Course document.
    course_id = ObjectIdField(db_index=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    # Auto-set to last+1 on create via services.auto_set_order().
    order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "courses"
        ordering = ["order"]
        indexes = [
            models.Index(fields=["course_id", "order"]),
        ]

    def __str__(self) -> str:
        return f"Unit({self.course_id}, order={self.order}): {self.title}"


# ---------------------------------------------------------------------------
# Lesson
# ---------------------------------------------------------------------------


class Lesson(models.Model):
    class LessonType(models.TextChoices):
        VIDEO = "VIDEO", "Video"
        TEXT = "TEXT", "Text"
        DOCUMENT = "DOCUMENT", "Document"
        LINK = "LINK", "Link"
        QUIZ = "QUIZ", "Quiz"  # placeholder — no grading logic

    unit_id = ObjectIdField(db_index=True)
    # Denormalised — stored for efficient filtering without a join.
    course_id = ObjectIdField(db_index=True)

    title = models.CharField(max_length=255)
    lesson_type = models.CharField(
        max_length=10,
        choices=LessonType.choices,
    )
    # Auto-set to last+1 within the unit on create via services.auto_set_order().
    order = models.PositiveIntegerField(default=0)
    duration_seconds = models.PositiveIntegerField(default=0)
    is_preview = models.BooleanField(default=False)

    # Polymorphic content stored as a plain JSON dict; validated per lesson_type
    # by the serializer layer (not at the DB level).
    content = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "courses"
        ordering = ["order"]
        indexes = [
            models.Index(fields=["unit_id", "order"]),
            models.Index(fields=["course_id"]),
        ]

    def __str__(self) -> str:
        return f"Lesson({self.unit_id}, order={self.order}): {self.title}"
