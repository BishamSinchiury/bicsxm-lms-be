"""
Tests for courses/cache.py
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


class TestVersionKey:
    def test_initial_version_is_zero(self):
        from apps.courses.cache import get_course_version

        ver = get_course_version("course-does-not-exist")
        assert ver == 0

    def test_bump_increments_version(self):
        from apps.courses.cache import bump_course_version, get_course_version

        cid = "test-cache-version-course"
        bump_course_version(cid)
        assert get_course_version(cid) == 1
        bump_course_version(cid)
        assert get_course_version(cid) == 2

    def test_invalidate_bumps_version(self):
        from apps.courses.cache import get_course_version, invalidate_course_cache

        cid = "test-invalidate-course"
        before = get_course_version(cid)
        invalidate_course_cache(cid)
        after = get_course_version(cid)
        assert after == before + 1


class TestGetOrSetCachedDetail:
    def test_callback_called_on_miss(self):
        from apps.courses.cache import get_or_set_cached_detail

        calls = []

        def callback():
            calls.append(1)
            return {"title": "Cached Course"}

        result = get_or_set_cached_detail("course-miss-123", callback)
        assert result == {"title": "Cached Course"}
        assert len(calls) == 1

    def test_callback_not_called_on_hit(self):
        from apps.courses.cache import get_or_set_cached_detail

        calls = []
        cid = "course-hit-456"

        def callback():
            calls.append(1)
            return {"title": "Cached"}

        # Warm the cache
        get_or_set_cached_detail(cid, callback)
        # Second call — should not invoke callback
        get_or_set_cached_detail(cid, callback)
        assert len(calls) == 1

    def test_invalidation_causes_cache_miss(self):
        from apps.courses.cache import (
            get_or_set_cached_detail,
            invalidate_course_cache,
        )

        calls = []
        cid = "course-invalidate-789"

        def callback():
            calls.append(1)
            return {"title": "Fresh"}

        get_or_set_cached_detail(cid, callback)
        invalidate_course_cache(cid)
        get_or_set_cached_detail(cid, callback)
        # Called twice — once before invalidation, once after.
        assert len(calls) == 2
