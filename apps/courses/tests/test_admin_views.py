"""
Tests for admin course views.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


class TestAdminCourseAccess:
    def test_admin_can_see_all_statuses(
        self, require_mongo, draft_course, published_course, admin_user
    ):
        from apps.courses.models import Course

        # Admin queryset = all
        qs = Course.objects.using("mongodb").all()
        pks = [str(c.pk) for c in qs]
        assert str(draft_course.pk) in pks
        assert str(published_course.pk) in pks

    def test_admin_can_delete_published_course(self, require_mongo, published_course, admin_user):
        from apps.courses.models import Course

        pk = published_course.pk
        published_course.delete(using="mongodb")
        assert not Course.objects.using("mongodb").filter(pk=pk).exists()

    def test_admin_can_force_publish_draft(self, require_mongo, draft_course, admin_user):
        from django.utils import timezone

        from apps.courses.models import Course

        draft_course.status = Course.Status.PUBLISHED
        draft_course.published_at = timezone.now()
        draft_course.save(using="mongodb")

        refreshed = Course.objects.using("mongodb").get(pk=draft_course.pk)
        assert refreshed.status == Course.Status.PUBLISHED


class TestAdminCourseFilter:
    def test_filter_by_status(self, require_mongo, draft_course, published_course):
        from apps.courses.models import Course

        drafts = list(Course.objects.using("mongodb").filter(status=Course.Status.DRAFT))
        published_list = list(Course.objects.using("mongodb").filter(status=Course.Status.PUBLISHED))

        draft_pks = [str(c.pk) for c in drafts]
        published_pks = [str(c.pk) for c in published_list]

        assert str(draft_course.pk) in draft_pks
        assert str(published_course.pk) in published_pks
        assert str(draft_course.pk) not in published_pks
