"""
Business-logic service layer for the Courses app.

All DB-level orchestration (counter recomputation, ordering, access logic,
cross-DB user resolution, HTML sanitisation) lives here so views stay thin.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import nh3
from django.db import models as django_models
from django.utils import timezone

from apps.courses.models import Course, Lesson, Unit

if TYPE_CHECKING:
    from django.contrib.auth import get_user_model

    User = get_user_model()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Tags that nh3 allows through in TEXT lesson HTML content.
_ALLOWED_HTML_TAGS: frozenset[str] = frozenset(
    {
        "a",
        "b",
        "blockquote",
        "br",
        "code",
        "em",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "i",
        "li",
        "ol",
        "p",
        "pre",
        "s",
        "strong",
        "sub",
        "sup",
        "table",
        "tbody",
        "td",
        "th",
        "thead",
        "tr",
        "u",
        "ul",
    }
)


# ---------------------------------------------------------------------------
# HTML sanitisation
# ---------------------------------------------------------------------------


def sanitise_html(html_string: str) -> str:
    """
    Sanitise an HTML string using nh3, allowing a safe subset of tags.

    Strips scripts, iframes, event handlers, and any tag not in the allowlist.
    """
    return nh3.clean(html_string, tags=_ALLOWED_HTML_TAGS)


# ---------------------------------------------------------------------------
# Order helpers
# ---------------------------------------------------------------------------


def auto_set_order(queryset: django_models.QuerySet, field: str = "order") -> int:
    """
    Return the next available order value (max + 1) for a queryset.

    If the queryset is empty, returns 1.
    """
    result = queryset.aggregate(max_order=django_models.Max(field))
    current_max: int = result.get("max_order") or 0
    return current_max + 1


# ---------------------------------------------------------------------------
# Counter recomputation
# ---------------------------------------------------------------------------


def recompute_course_stats(course_id: object) -> None:
    """
    Recompute and atomically update the denormalised counters on a Course.

    Runs an aggregation over the Unit and Lesson collections:
    - unit_count              → number of Unit documents for this course
    - lesson_count            → number of Lesson documents for this course
    - total_duration_seconds  → sum of Lesson.duration_seconds for this course

    Called synchronously after every Unit/Lesson create, update, or delete.
    """
    try:
        unit_count = Unit.objects.using("mongodb").filter(course_id=course_id).count()

        lesson_agg = Lesson.objects.using("mongodb").filter(course_id=course_id).aggregate(
            total_duration=django_models.Sum("duration_seconds"),
            lesson_count=django_models.Count("id"),
        )
        lesson_count: int = lesson_agg.get("lesson_count") or 0
        total_duration: int = lesson_agg.get("total_duration") or 0

        Course.objects.using("mongodb").filter(pk=course_id).update(
            unit_count=unit_count,
            lesson_count=lesson_count,
            total_duration_seconds=total_duration,
            updated_at=timezone.now(),
        )
    except Exception:
        logger.exception("Failed to recompute course stats for course_id=%s", course_id)


# ---------------------------------------------------------------------------
# Access control helper
# ---------------------------------------------------------------------------


def can_user_view_course(user: User, course: Course) -> bool:
    """
    Return True if *user* is permitted to read *course*.

    - ADMIN / TEACHER: always True (ownership already filtered at list level).
    - STUDENT: only PUBLISHED courses.
    """
    if user.role in ("ADMIN", "TEACHER"):
        return True
    return course.status == Course.Status.PUBLISHED


# ---------------------------------------------------------------------------
# Cross-DB user name resolution
# ---------------------------------------------------------------------------


def resolve_created_by_names(uuid_list: list[str]) -> dict[str, str]:
    """
    Given a list of UUID strings (course.created_by values), return a mapping
    of ``{uuid_str: full_name}`` by issuing a single Postgres query.

    Missing users are silently excluded (returns an empty string for them
    when the caller falls back to ``dict.get``).
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()

    if not uuid_list:
        return {}

    users = User.objects.using("default").filter(pk__in=uuid_list).values("id", "full_name")
    return {str(u["id"]): u["full_name"] for u in users}
