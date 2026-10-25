"""
Tests for courses/permissions.py
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.django_db


class TestIsCourseOwnerOrAdmin:
    def test_admin_always_allowed(self, admin_user, draft_course):
        from apps.courses.permissions import IsCourseOwnerOrAdmin

        request = MagicMock()
        request.user = admin_user
        perm = IsCourseOwnerOrAdmin()
        assert perm.has_object_permission(request, None, draft_course) is True

    def test_owner_teacher_allowed(self, teacher_user, draft_course):
        from apps.courses.permissions import IsCourseOwnerOrAdmin

        request = MagicMock()
        request.user = teacher_user
        perm = IsCourseOwnerOrAdmin()
        assert perm.has_object_permission(request, None, draft_course) is True

    def test_non_owner_teacher_denied(self, teacher_user2, draft_course):
        from apps.courses.permissions import IsCourseOwnerOrAdmin

        request = MagicMock()
        request.user = teacher_user2
        perm = IsCourseOwnerOrAdmin()
        assert perm.has_object_permission(request, None, draft_course) is False

    def test_student_denied(self, student_user, draft_course):
        from apps.courses.permissions import IsCourseOwnerOrAdmin

        request = MagicMock()
        request.user = student_user
        perm = IsCourseOwnerOrAdmin()
        assert perm.has_object_permission(request, None, draft_course) is False


class TestCanViewCourse:
    def test_student_can_view_published(self, student_user, published_course):
        from apps.courses.permissions import CanViewCourse

        request = MagicMock()
        request.user = student_user
        perm = CanViewCourse()
        assert perm.has_object_permission(request, None, published_course) is True

    def test_student_cannot_view_draft(self, student_user, draft_course):
        from apps.courses.permissions import CanViewCourse

        request = MagicMock()
        request.user = student_user
        perm = CanViewCourse()
        assert perm.has_object_permission(request, None, draft_course) is False

    def test_admin_can_view_any(self, admin_user, draft_course):
        from apps.courses.permissions import CanViewCourse

        request = MagicMock()
        request.user = admin_user
        perm = CanViewCourse()
        assert perm.has_object_permission(request, None, draft_course) is True
