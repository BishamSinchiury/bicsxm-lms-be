"""
Cache helpers for the Courses app.

All course caching lives in Redis DB 4 (cache alias ``courses``).

Strategy
--------
- Version keys: ``course:ver:<id>`` — incremented on every write, embedded in
  all related cache keys so stale data ages out naturally without explicit purges.
- Published course detail:  ``course:detail:v{ver}:{id}``   TTL = 5 min
- Published course list:    ``course:list:v{ver}:p{page}:q{hash}``  TTL = 2 min
- Student outline:          ``course:outline:v{ver}:{id}``   TTL = 5 min

Rules
-----
- NEVER cache draft / admin / teacher-specific views.
- Invalidate (bump version) on any write to a course, unit, or lesson.
"""

from __future__ import annotations

import hashlib
import json

from django.core.cache import caches

COURSE_CACHE = "courses"
DETAIL_TTL = 60 * 5   # 5 minutes
LIST_TTL   = 60 * 2   # 2 minutes
OUTLINE_TTL = 60 * 5  # 5 minutes
VERSION_TTL = 60 * 60 * 24  # 24 hours — version key lifetime


def _cache():
    return caches[COURSE_CACHE]


# ---------------------------------------------------------------------------
# Version key
# ---------------------------------------------------------------------------


def _version_key(course_id: str) -> str:
    return f"course:ver:{course_id}"


def get_course_version(course_id: str) -> int:
    """Return the current cache version for a course (0 if not set)."""
    value = _cache().get(_version_key(course_id))
    return int(value) if value is not None else 0


def bump_course_version(course_id: str) -> int:
    """Increment the course version counter and return the new value."""
    cache = _cache()
    key = _version_key(course_id)
    try:
        return cache.incr(key)
    except ValueError:
        # Key does not exist yet — set to 1.
        cache.set(key, 1, timeout=VERSION_TTL)
        return 1


# ---------------------------------------------------------------------------
# Key builders
# ---------------------------------------------------------------------------


def detail_key(course_id: str, version: int | None = None) -> str:
    ver = version if version is not None else get_course_version(course_id)
    return f"course:detail:v{ver}:{course_id}"


def outline_key(course_id: str, version: int | None = None) -> str:
    ver = version if version is not None else get_course_version(course_id)
    return f"course:outline:v{ver}:{course_id}"


def list_key(page: int, query_params: dict, version_tag: str) -> str:
    """Version tag is a short digest of all current course versions (caller supplies it)."""
    param_hash = hashlib.md5(  # noqa: S324  (non-security hash for cache key)
        json.dumps(query_params, sort_keys=True).encode()
    ).hexdigest()[:12]
    return f"course:list:{version_tag}:p{page}:q{param_hash}"


# ---------------------------------------------------------------------------
# Get-or-set helpers
# ---------------------------------------------------------------------------


def get_or_set_cached_detail(course_id: str, callback):
    """
    Return cached course detail data, computing via *callback* on miss.
    *callback* must return a JSON-serialisable dict.
    """
    cache = _cache()
    ver = get_course_version(course_id)
    key = detail_key(course_id, ver)
    data = cache.get(key)
    if data is None:
        data = callback()
        if data is not None:
            cache.set(key, data, timeout=DETAIL_TTL)
    return data


def get_or_set_cached_outline(course_id: str, callback):
    """Return cached student outline, computing via *callback* on miss."""
    cache = _cache()
    ver = get_course_version(course_id)
    key = outline_key(course_id, ver)
    data = cache.get(key)
    if data is None:
        data = callback()
        if data is not None:
            cache.set(key, data, timeout=OUTLINE_TTL)
    return data


def invalidate_course_cache(course_id: str) -> None:
    """
    Bump the version for *course_id*, rendering all existing detail / outline
    keys stale.  Called after any write to a Course, Unit, or Lesson.
    """
    bump_course_version(str(course_id))
