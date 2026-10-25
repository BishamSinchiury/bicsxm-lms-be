"""
Tests for courses/services.py
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


class TestSanitiseHtml:
    def test_allows_safe_tags(self):
        from apps.courses.services import sanitise_html

        result = sanitise_html("<p>Hello <strong>world</strong></p>")
        assert "<p>" in result
        assert "<strong>" in result

    def test_strips_script_tags(self):
        from apps.courses.services import sanitise_html

        result = sanitise_html("<script>alert('xss')</script><p>ok</p>")
        assert "<script>" not in result
        assert "alert" not in result
        assert "<p>ok</p>" in result

    def test_strips_event_handlers(self):
        from apps.courses.services import sanitise_html

        result = sanitise_html('<a href="http://x.com" onclick="evil()">click</a>')
        assert "onclick" not in result

    def test_empty_string(self):
        from apps.courses.services import sanitise_html

        assert sanitise_html("") == ""

    def test_plain_text_unchanged(self):
        from apps.courses.services import sanitise_html

        assert sanitise_html("just text") == "just text"


class TestAutoSetOrder:
    def test_returns_one_for_empty_queryset(self, require_mongo):
        from apps.courses.models import Unit
        from apps.courses.services import auto_set_order

        qs = Unit.objects.using("mongodb").filter(course_id="nonexistent-id")
        assert auto_set_order(qs) == 1

    def test_returns_max_plus_one(self, require_mongo, unit_fixture, draft_course):
        from apps.courses.models import Unit
        from apps.courses.services import auto_set_order

        qs = Unit.objects.using("mongodb").filter(course_id=draft_course.pk)
        result = auto_set_order(qs)
        assert result == unit_fixture.order + 1


class TestRecomputeCourseStats:
    def test_recomputes_counters(self, require_mongo, lesson_fixture, draft_course):
        from apps.courses.models import Course
        from apps.courses.services import recompute_course_stats

        recompute_course_stats(draft_course.pk)
        updated = Course.objects.using("mongodb").get(pk=draft_course.pk)
        assert updated.unit_count == 1
        assert updated.lesson_count == 1
        assert updated.total_duration_seconds == 300

    def test_zeros_on_empty_course(self, require_mongo, draft_course):
        from apps.courses.models import Course
        from apps.courses.services import recompute_course_stats

        recompute_course_stats(draft_course.pk)
        updated = Course.objects.using("mongodb").get(pk=draft_course.pk)
        assert updated.unit_count == 0
        assert updated.lesson_count == 0
        assert updated.total_duration_seconds == 0


class TestCanUserViewCourse:
    def test_admin_can_view_any_course(self, admin_user, draft_course):
        from apps.courses.services import can_user_view_course

        assert can_user_view_course(admin_user, draft_course) is True

    def test_teacher_can_view_any_course(self, teacher_user, draft_course):
        from apps.courses.services import can_user_view_course

        assert can_user_view_course(teacher_user, draft_course) is True

    def test_student_can_view_published(self, student_user, published_course):
        from apps.courses.services import can_user_view_course

        assert can_user_view_course(student_user, published_course) is True

    def test_student_cannot_view_draft(self, student_user, draft_course):
        from apps.courses.services import can_user_view_course

        assert can_user_view_course(student_user, draft_course) is False


class TestResolveCreatedByNames:
    def test_returns_name_map(self, teacher_user):
        from apps.courses.services import resolve_created_by_names

        result = resolve_created_by_names([str(teacher_user.pk)])
        assert str(teacher_user.pk) in result
        assert result[str(teacher_user.pk)] == teacher_user.full_name

    def test_empty_list(self):
        from apps.courses.services import resolve_created_by_names

        assert resolve_created_by_names([]) == {}

    def test_missing_user_excluded(self):
        from apps.courses.services import resolve_created_by_names

        result = resolve_created_by_names(["00000000-0000-0000-0000-000000000000"])
        assert result == {}
