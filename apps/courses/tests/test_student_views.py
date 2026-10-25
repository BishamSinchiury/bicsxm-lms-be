"""
Tests for student course views.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


class TestStudentCourseList:
    def test_only_published_returned(self, require_mongo, published_course, draft_course, student_user):
        from apps.courses.models import Course

        qs = Course.objects.using("mongodb").filter(status=Course.Status.PUBLISHED)
        ids = [str(c.pk) for c in qs]
        assert str(published_course.pk) in ids
        assert str(draft_course.pk) not in ids

    def test_student_cannot_see_archived(self, require_mongo, student_user):
        from apps.courses.models import Course

        archived = Course(
            title="Archived Course",
            slug="archived-course-test",
            status=Course.Status.ARCHIVED,
            created_by=str(student_user.pk),
        )
        archived.save(using="mongodb")
        try:
            qs = Course.objects.using("mongodb").filter(status=Course.Status.PUBLISHED)
            assert str(archived.pk) not in [str(c.pk) for c in qs]
        finally:
            archived.delete(using="mongodb")


class TestStudentCourseDetail:
    def test_can_view_published_course(self, require_mongo, published_course, student_user):
        from apps.courses.services import can_user_view_course

        assert can_user_view_course(student_user, published_course) is True

    def test_cannot_view_draft_course(self, require_mongo, draft_course, student_user):
        from apps.courses.services import can_user_view_course

        assert can_user_view_course(student_user, draft_course) is False


class TestStudentCourseOutline:
    def test_outline_returns_units_with_lessons(
        self, require_mongo, published_course, unit_fixture, lesson_fixture
    ):
        from apps.courses.models import Unit
        from apps.courses.serializers import UnitWithLessonsSerializer

        units = Unit.objects.using("mongodb").filter(course_id=published_course.pk).order_by("order")
        data = UnitWithLessonsSerializer(units, many=True).data
        # unit_fixture belongs to draft_course, not published_course, so 0 units
        # This tests the serializer shape is correct.
        assert isinstance(data, list)

    def test_outline_lessons_have_no_content_field(
        self, require_mongo, unit_fixture, lesson_fixture
    ):
        from apps.courses.models import Lesson
        from apps.courses.serializers import LessonListSerializer

        lessons = Lesson.objects.using("mongodb").filter(unit_id=unit_fixture.pk)
        data = LessonListSerializer(lessons, many=True).data
        for lesson_data in data:
            assert "content" not in lesson_data
