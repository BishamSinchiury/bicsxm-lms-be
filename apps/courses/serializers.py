"""
Serializers for the Courses app.

Hierarchy:
  LessonContentSerializer (polymorphic per lesson_type)
  LessonSerializer        (full CRUD)
  LessonListSerializer    (lightweight — no content field for outline/list)
  UnitSerializer          (CRUD)
  UnitWithLessonsSerializer (unit + ordered lesson metadata, for outline)
  CourseListSerializer    (lightweight — counters, no units/lessons)
  CourseDetailSerializer  (full detail — counters, no nested units)
  CourseWriteSerializer   (create/update — validates slug uniqueness)
"""

from __future__ import annotations

import re
from typing import Any

from rest_framework import serializers

from apps.courses.models import Course, Lesson, Unit
from apps.courses.services import sanitise_html

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _validate_http_url(value: str, field_name: str = "URL") -> str:
    """Ensure a URL starts with http:// or https://."""
    if value and not _HTTP_URL_RE.match(value):
        raise serializers.ValidationError(f"{field_name} must start with http:// or https://.")
    return value


# ---------------------------------------------------------------------------
# Lesson content — polymorphic validation
# ---------------------------------------------------------------------------


class VideoContentSerializer(serializers.Serializer):
    video_url = serializers.URLField()
    provider = serializers.ChoiceField(
        choices=["youtube", "vimeo", "other"],
        default="other",
    )

    def validate_video_url(self, value: str) -> str:
        return _validate_http_url(value, "video_url")


class TextContentSerializer(serializers.Serializer):
    html = serializers.CharField(allow_blank=True, default="")

    def validate_html(self, value: str) -> str:
        return sanitise_html(value)


class DocumentContentSerializer(serializers.Serializer):
    document_url = serializers.URLField()
    file_name = serializers.CharField(max_length=255, default="")

    def validate_document_url(self, value: str) -> str:
        return _validate_http_url(value, "document_url")


class LinkContentSerializer(serializers.Serializer):
    url = serializers.URLField()
    link_text = serializers.CharField(max_length=255, default="")

    def validate_url(self, value: str) -> str:
        return _validate_http_url(value, "url")


class QuizContentSerializer(serializers.Serializer):
    """Placeholder — no grading logic yet."""


_CONTENT_SERIALIZER_MAP: dict[str, type[serializers.Serializer]] = {
    "VIDEO": VideoContentSerializer,
    "TEXT": TextContentSerializer,
    "DOCUMENT": DocumentContentSerializer,
    "LINK": LinkContentSerializer,
    "QUIZ": QuizContentSerializer,
}


def validate_lesson_content(lesson_type: str, content: dict) -> dict:
    """Validate *content* dict against the schema for *lesson_type*."""
    serializer_cls = _CONTENT_SERIALIZER_MAP.get(lesson_type)
    if serializer_cls is None:
        raise serializers.ValidationError({"lesson_type": f"Unknown lesson type: {lesson_type}"})
    s = serializer_cls(data=content)
    if not s.is_valid():
        raise serializers.ValidationError({"content": s.errors})
    return s.validated_data


# ---------------------------------------------------------------------------
# Lesson serializers
# ---------------------------------------------------------------------------


class LessonSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)
    unit_id = serializers.CharField(read_only=True)
    course_id = serializers.CharField(read_only=True)

    class Meta:
        model = Lesson
        fields = [
            "id",
            "unit_id",
            "course_id",
            "title",
            "lesson_type",
            "order",
            "duration_seconds",
            "is_preview",
            "content",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "unit_id", "course_id", "order", "created_at", "updated_at"]

    def validate(self, attrs: dict) -> dict:
        # On create lesson_type is required; on partial update it may be absent.
        lesson_type = attrs.get("lesson_type") or (
            self.instance.lesson_type if self.instance else None
        )
        content = attrs.get("content")

        if lesson_type and content is not None:
            attrs["content"] = validate_lesson_content(lesson_type, content)
        elif lesson_type and not self.instance:
            # New lesson — require content.
            raise serializers.ValidationError({"content": "This field is required."})
        return attrs


class LessonListSerializer(serializers.ModelSerializer):
    """Lightweight — no content field; used in outlines and unit lists."""

    id = serializers.CharField(read_only=True)

    class Meta:
        model = Lesson
        fields = [
            "id",
            "title",
            "lesson_type",
            "order",
            "duration_seconds",
            "is_preview",
            "created_at",
            "updated_at",
        ]


# ---------------------------------------------------------------------------
# Unit serializers
# ---------------------------------------------------------------------------


class UnitSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)
    course_id = serializers.CharField(read_only=True)

    class Meta:
        model = Unit
        fields = [
            "id",
            "course_id",
            "title",
            "description",
            "order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "course_id", "order", "created_at", "updated_at"]


class UnitWithLessonsSerializer(serializers.ModelSerializer):
    """Unit + its ordered lessons (metadata only) — for student outline endpoint."""

    id = serializers.CharField(read_only=True)
    lessons = serializers.SerializerMethodField()

    class Meta:
        model = Unit
        fields = ["id", "title", "description", "order", "lessons"]

    def get_lessons(self, unit: Unit) -> list:
        qs = (
            Lesson.objects.using("mongodb")
            .filter(unit_id=unit.pk)
            .order_by("order")
        )
        return LessonListSerializer(qs, many=True).data


# ---------------------------------------------------------------------------
# Course serializers
# ---------------------------------------------------------------------------


class CourseListSerializer(serializers.ModelSerializer):
    """Lightweight list view — counters and metadata, no units/lessons."""

    id = serializers.CharField(read_only=True)

    class Meta:
        model = Course
        fields = [
            "id",
            "title",
            "slug",
            "description",
            "thumbnail_url",
            "status",
            "created_by",
            "created_by_name",
            "tags",
            "unit_count",
            "lesson_count",
            "total_duration_seconds",
            "created_at",
            "updated_at",
            "published_at",
        ]


class CourseDetailSerializer(CourseListSerializer):
    """Full course detail — same as list but explicitly named for schema clarity."""

    class Meta(CourseListSerializer.Meta):
        pass


class CourseWriteSerializer(serializers.ModelSerializer):
    """
    Create / partial-update serializer.

    - slug is optional on create (auto-generated from title if omitted).
    - thumbnail_url must be http/https if provided.
    - tags must be a list of non-empty strings.
    """

    class Meta:
        model = Course
        fields = [
            "title",
            "slug",
            "description",
            "thumbnail_url",
            "tags",
        ]
        extra_kwargs = {
            "slug": {"required": False},
        }

    def validate_thumbnail_url(self, value: str) -> str:
        return _validate_http_url(value, "thumbnail_url") if value else value

    def validate_tags(self, value: Any) -> list:
        if not isinstance(value, list):
            raise serializers.ValidationError("Tags must be a list of strings.")
        cleaned = []
        for tag in value:
            if not isinstance(tag, str) or not tag.strip():
                raise serializers.ValidationError("Each tag must be a non-empty string.")
            cleaned.append(tag.strip()[:100])
        return cleaned

    def validate_slug(self, value: str) -> str:
        """Ensure slug is unique, excluding the current instance on update."""
        qs = Course.objects.using("mongodb").filter(slug=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A course with this slug already exists.")
        return value

    def validate(self, attrs: dict) -> dict:
        # Auto-generate slug from title if not provided on create.
        if not self.instance and not attrs.get("slug"):
            from django.utils.text import slugify

            base = slugify(attrs.get("title", ""))[:270]
            slug = base
            suffix = 1
            while Course.objects.using("mongodb").filter(slug=slug).exists():
                slug = f"{base}-{suffix}"
                suffix += 1
            attrs["slug"] = slug
        return attrs


# ---------------------------------------------------------------------------
# Reorder serializer (shared by units and lessons)
# ---------------------------------------------------------------------------


class ReorderSerializer(serializers.Serializer):
    """
    Accepts an ordered list of IDs and re-assigns ``order`` starting from 1.

    ``ordered_ids`` — list of ObjectId strings in the desired display order.
    """

    ordered_ids = serializers.ListField(
        child=serializers.CharField(),
        min_length=1,
        allow_empty=False,
    )
