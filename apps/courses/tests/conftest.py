"""
Fixtures for courses app tests.

MongoDB tests require a real MongoDB instance (mongomock not compatible with
django-mongodb-backend). If MongoDB is unreachable, tests are skipped
automatically via the ``require_mongo`` fixture.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


# ---------------------------------------------------------------------------
# MongoDB availability check
# ---------------------------------------------------------------------------


def _mongo_available() -> bool:
    """Return True if a real MongoDB server is reachable."""
    try:
        from django.db import connections

        conn = connections["mongodb"]
        conn.ensure_connection()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def mongo_available():
    return _mongo_available()


@pytest.fixture(autouse=False)
def require_mongo(mongo_available):
    """Skip any test that needs a live MongoDB when none is available."""
    if not mongo_available:
        pytest.skip("MongoDB not available — skipping.")


# ---------------------------------------------------------------------------
# User fixtures (Postgres)
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        email="admin@test.com",
        password="AdminPass123!",
        full_name="Admin User",
        role="ADMIN",
        is_email_verified=True,
        is_approved=True,
        is_staff=True,
    )


@pytest.fixture
def teacher_user(db):
    return User.objects.create_user(
        email="teacher@test.com",
        password="TeacherPass123!",
        full_name="Teacher User",
        role="TEACHER",
        is_email_verified=True,
        is_approved=True,
    )


@pytest.fixture
def teacher_user2(db):
    return User.objects.create_user(
        email="teacher2@test.com",
        password="TeacherPass123!",
        full_name="Teacher Two",
        role="TEACHER",
        is_email_verified=True,
        is_approved=True,
    )


@pytest.fixture
def student_user(db):
    return User.objects.create_user(
        email="student@test.com",
        password="StudentPass123!",
        full_name="Student User",
        role="STUDENT",
        is_email_verified=True,
        is_approved=True,
    )


# ---------------------------------------------------------------------------
# Course fixtures (MongoDB)
# ---------------------------------------------------------------------------


@pytest.fixture
def draft_course(require_mongo, teacher_user):
    from apps.courses.models import Course

    course = Course(
        title="Draft Course",
        slug="draft-course",
        description="A draft course.",
        status=Course.Status.DRAFT,
        created_by=str(teacher_user.pk),
        created_by_name=teacher_user.full_name,
    )
    course.save(using="mongodb")
    yield course
    try:
        course.delete(using="mongodb")
    except Exception:
        pass


@pytest.fixture
def published_course(require_mongo, teacher_user):
    from django.utils import timezone

    from apps.courses.models import Course

    course = Course(
        title="Published Course",
        slug="published-course",
        description="A published course.",
        status=Course.Status.PUBLISHED,
        created_by=str(teacher_user.pk),
        created_by_name=teacher_user.full_name,
        published_at=timezone.now(),
    )
    course.save(using="mongodb")
    yield course
    try:
        course.delete(using="mongodb")
    except Exception:
        pass


@pytest.fixture
def unit_fixture(require_mongo, draft_course):
    from apps.courses.models import Unit

    unit = Unit(
        course_id=draft_course.pk,
        title="Unit 1",
        description="First unit.",
        order=1,
    )
    unit.save(using="mongodb")
    yield unit
    try:
        unit.delete(using="mongodb")
    except Exception:
        pass


@pytest.fixture
def lesson_fixture(require_mongo, unit_fixture, draft_course):
    from apps.courses.models import Lesson

    lesson = Lesson(
        unit_id=unit_fixture.pk,
        course_id=draft_course.pk,
        title="Lesson 1",
        lesson_type=Lesson.LessonType.VIDEO,
        order=1,
        duration_seconds=300,
        content={"video_url": "https://youtube.com/watch?v=abc", "provider": "youtube"},
    )
    lesson.save(using="mongodb")
    yield lesson
    try:
        lesson.delete(using="mongodb")
    except Exception:
        pass
