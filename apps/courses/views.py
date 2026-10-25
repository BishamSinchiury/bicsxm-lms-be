"""
Views for the Courses app.

Three role-namespaced view groups:
  Teacher  — full CRUD on own courses + unit/lesson management
  Admin    — full CRUD on all courses + unit/lesson management
  Student  — read-only, published courses only

All views require full-scope tokens (no limited-scope access).
"""

from __future__ import annotations

import logging

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.authentication import (
    AdminJWTCookieAuthentication,
    StudentJWTCookieAuthentication,
    TeacherJWTCookieAuthentication,
)
from apps.core.permissions import IsActiveAdmin, IsActiveStudent, IsActiveTeacher
from apps.courses import cache as course_cache
from apps.courses.models import Course, Lesson, Unit
from apps.courses.pagination import CoursePagination
from apps.courses.permissions import CanViewCourse
from apps.courses.serializers import (
    CourseDetailSerializer,
    CourseListSerializer,
    CourseWriteSerializer,
    LessonSerializer,
    ReorderSerializer,
    UnitSerializer,
    UnitWithLessonsSerializer,
)
from apps.courses.services import (
    auto_set_order,
    can_user_view_course,
    recompute_course_stats,
    resolve_created_by_names,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------


class CourseQuerysetMixin:
    """
    Base mixin that provides get_course_queryset() per role.

    - Teacher: own courses only (404 on non-owner access — existence not leaked).
    - Admin:   all courses.
    - Student: published courses only.
    """

    def get_course_queryset(self, request: Request):
        role = getattr(request, "auth_role", None)
        qs = Course.objects.using("mongodb")
        if role == "teacher":
            return qs.filter(created_by=str(request.user.pk))
        if role == "admin":
            return qs.all()
        # student
        return qs.filter(status=Course.Status.PUBLISHED)

    def get_course_or_404(self, pk: str, request: Request) -> Course:
        qs = self.get_course_queryset(request)
        try:
            return qs.get(pk=pk)
        except Course.DoesNotExist as exc:
            raise NotFound("Course not found.") from exc

    def enrich_with_creator_names(self, courses) -> list[dict]:
        """Batch-resolve Postgres user names and inject into serialized data."""
        ids = list({c.created_by for c in courses if c.created_by})
        name_map = resolve_created_by_names(ids)
        data = CourseListSerializer(courses, many=True).data
        for item in data:
            item["created_by_name"] = name_map.get(item.get("created_by", ""), "")
        return data


class UnitQuerysetMixin:
    def get_unit_or_404(self, course_id: str, unit_pk: str) -> Unit:
        try:
            return Unit.objects.using("mongodb").get(pk=unit_pk, course_id=course_id)
        except Unit.DoesNotExist as exc:
            raise NotFound("Unit not found.") from exc


class LessonQuerysetMixin:
    def get_lesson_or_404(self, unit_id: str, lesson_pk: str) -> Lesson:
        try:
            return Lesson.objects.using("mongodb").get(pk=lesson_pk, unit_id=unit_id)
        except Lesson.DoesNotExist as exc:
            raise NotFound("Lesson not found.") from exc


# ---------------------------------------------------------------------------
# ─── TEACHER views ──────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


@extend_schema(tags=["Teacher Courses"])
class TeacherCourseListCreateView(CourseQuerysetMixin, APIView):
    authentication_classes = [TeacherJWTCookieAuthentication]
    permission_classes = [IsActiveTeacher]
    pagination_class = CoursePagination

    @extend_schema(summary="List my courses", responses={200: CourseListSerializer(many=True)})
    def get(self, request: Request) -> Response:
        qs = self.get_course_queryset(request).order_by("-created_at")

        # Manual pagination
        paginator = CoursePagination()
        page = paginator.paginate_queryset(list(qs), request)
        data = self.enrich_with_creator_names(page)
        return paginator.get_paginated_response(data)

    @extend_schema(summary="Create a draft course", request=CourseWriteSerializer, responses={201: CourseDetailSerializer})
    def post(self, request: Request) -> Response:
        serializer = CourseWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        course = serializer.save(
            created_by=str(request.user.pk),
            created_by_name=request.user.full_name,
            status=Course.Status.DRAFT,
        )
        course.save(using="mongodb")
        return Response(CourseDetailSerializer(course).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Teacher Courses"])
class TeacherCourseDetailView(CourseQuerysetMixin, APIView):
    authentication_classes = [TeacherJWTCookieAuthentication]
    permission_classes = [IsActiveTeacher]

    @extend_schema(summary="Get my course detail", responses={200: CourseDetailSerializer})
    def get(self, request: Request, pk: str) -> Response:
        course = self.get_course_or_404(pk, request)
        return Response(CourseDetailSerializer(course).data)

    @extend_schema(summary="Update my course", request=CourseWriteSerializer, responses={200: CourseDetailSerializer})
    def patch(self, request: Request, pk: str) -> Response:
        course = self.get_course_or_404(pk, request)
        serializer = CourseWriteSerializer(course, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        course = serializer.save()
        course.save(using="mongodb")
        course_cache.invalidate_course_cache(str(course.pk))
        return Response(CourseDetailSerializer(course).data)

    @extend_schema(summary="Delete my draft course", responses={204: None})
    def delete(self, request: Request, pk: str) -> Response:
        course = self.get_course_or_404(pk, request)
        if course.status != Course.Status.DRAFT:
            raise ValidationError(
                {"detail": "Only DRAFT courses can be deleted. Archive it first."}
            )
        course_cache.invalidate_course_cache(str(course.pk))
        course.delete(using="mongodb")
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Teacher Courses"])
class TeacherCoursePublishView(CourseQuerysetMixin, APIView):
    authentication_classes = [TeacherJWTCookieAuthentication]
    permission_classes = [IsActiveTeacher]

    @extend_schema(summary="Publish a draft course", responses={200: CourseDetailSerializer})
    def post(self, request: Request, pk: str) -> Response:
        course = self.get_course_or_404(pk, request)
        if course.status != Course.Status.DRAFT:
            raise ValidationError({"detail": "Only DRAFT courses can be published."})
        course.status = Course.Status.PUBLISHED
        course.published_at = timezone.now()
        course.save(using="mongodb")
        course_cache.invalidate_course_cache(str(course.pk))
        return Response(CourseDetailSerializer(course).data)


@extend_schema(tags=["Teacher Courses"])
class TeacherCourseArchiveView(CourseQuerysetMixin, APIView):
    authentication_classes = [TeacherJWTCookieAuthentication]
    permission_classes = [IsActiveTeacher]

    @extend_schema(summary="Archive a published course", responses={200: CourseDetailSerializer})
    def post(self, request: Request, pk: str) -> Response:
        course = self.get_course_or_404(pk, request)
        if course.status != Course.Status.PUBLISHED:
            raise ValidationError({"detail": "Only PUBLISHED courses can be archived."})
        course.status = Course.Status.ARCHIVED
        course.save(using="mongodb")
        course_cache.invalidate_course_cache(str(course.pk))
        return Response(CourseDetailSerializer(course).data)


@extend_schema(tags=["Teacher Courses"])
class TeacherCourseUnpublishView(CourseQuerysetMixin, APIView):
    authentication_classes = [TeacherJWTCookieAuthentication]
    permission_classes = [IsActiveTeacher]

    @extend_schema(summary="Unpublish (revert to draft)", responses={200: CourseDetailSerializer})
    def post(self, request: Request, pk: str) -> Response:
        course = self.get_course_or_404(pk, request)
        if course.status != Course.Status.PUBLISHED:
            raise ValidationError({"detail": "Only PUBLISHED courses can be unpublished."})
        course.status = Course.Status.DRAFT
        course.published_at = None
        course.save(using="mongodb")
        course_cache.invalidate_course_cache(str(course.pk))
        return Response(CourseDetailSerializer(course).data)


# Unit views — teacher

@extend_schema(tags=["Teacher Courses"])
class TeacherUnitListCreateView(CourseQuerysetMixin, UnitQuerysetMixin, APIView):
    authentication_classes = [TeacherJWTCookieAuthentication]
    permission_classes = [IsActiveTeacher]

    @extend_schema(summary="List units for my course", responses={200: UnitSerializer(many=True)})
    def get(self, request: Request, course_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)  # ownership check
        units = Unit.objects.using("mongodb").filter(course_id=course_pk).order_by("order")
        return Response(UnitSerializer(units, many=True).data)

    @extend_schema(summary="Create a unit", request=UnitSerializer, responses={201: UnitSerializer})
    def post(self, request: Request, course_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)
        serializer = UnitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        next_order = auto_set_order(
            Unit.objects.using("mongodb").filter(course_id=course_pk)
        )
        unit = serializer.save(course_id=course_pk, order=next_order)
        unit.save(using="mongodb")
        recompute_course_stats(course_pk)
        course_cache.invalidate_course_cache(course_pk)
        return Response(UnitSerializer(unit).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Teacher Courses"])
class TeacherUnitDetailView(CourseQuerysetMixin, UnitQuerysetMixin, APIView):
    authentication_classes = [TeacherJWTCookieAuthentication]
    permission_classes = [IsActiveTeacher]

    @extend_schema(summary="Get unit", responses={200: UnitSerializer})
    def get(self, request: Request, course_pk: str, unit_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)
        unit = self.get_unit_or_404(course_pk, unit_pk)
        return Response(UnitSerializer(unit).data)

    @extend_schema(summary="Update unit", request=UnitSerializer, responses={200: UnitSerializer})
    def patch(self, request: Request, course_pk: str, unit_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)
        unit = self.get_unit_or_404(course_pk, unit_pk)
        serializer = UnitSerializer(unit, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        unit = serializer.save()
        unit.save(using="mongodb")
        course_cache.invalidate_course_cache(course_pk)
        return Response(UnitSerializer(unit).data)

    @extend_schema(summary="Delete unit", responses={204: None})
    def delete(self, request: Request, course_pk: str, unit_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)
        unit = self.get_unit_or_404(course_pk, unit_pk)
        # Delete all lessons in this unit first.
        Lesson.objects.using("mongodb").filter(unit_id=unit_pk).delete()
        unit.delete(using="mongodb")
        recompute_course_stats(course_pk)
        course_cache.invalidate_course_cache(course_pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Teacher Courses"])
class TeacherUnitReorderView(CourseQuerysetMixin, APIView):
    authentication_classes = [TeacherJWTCookieAuthentication]
    permission_classes = [IsActiveTeacher]

    @extend_schema(summary="Reorder units", request=ReorderSerializer, responses={200: UnitSerializer(many=True)})
    def post(self, request: Request, course_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)
        return _reorder_units(course_pk, request.data)


@extend_schema(tags=["Teacher Courses"])
class TeacherLessonListCreateView(CourseQuerysetMixin, UnitQuerysetMixin, APIView):
    authentication_classes = [TeacherJWTCookieAuthentication]
    permission_classes = [IsActiveTeacher]

    @extend_schema(summary="List lessons", responses={200: LessonSerializer(many=True)})
    def get(self, request: Request, course_pk: str, unit_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)
        self.get_unit_or_404(course_pk, unit_pk)
        lessons = Lesson.objects.using("mongodb").filter(unit_id=unit_pk).order_by("order")
        return Response(LessonSerializer(lessons, many=True).data)

    @extend_schema(summary="Create lesson", request=LessonSerializer, responses={201: LessonSerializer})
    def post(self, request: Request, course_pk: str, unit_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)
        self.get_unit_or_404(course_pk, unit_pk)
        serializer = LessonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        next_order = auto_set_order(
            Lesson.objects.using("mongodb").filter(unit_id=unit_pk)
        )
        lesson = serializer.save(unit_id=unit_pk, course_id=course_pk, order=next_order)
        lesson.save(using="mongodb")
        recompute_course_stats(course_pk)
        course_cache.invalidate_course_cache(course_pk)
        return Response(LessonSerializer(lesson).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Teacher Courses"])
class TeacherLessonDetailView(CourseQuerysetMixin, UnitQuerysetMixin, LessonQuerysetMixin, APIView):
    authentication_classes = [TeacherJWTCookieAuthentication]
    permission_classes = [IsActiveTeacher]

    @extend_schema(summary="Get lesson", responses={200: LessonSerializer})
    def get(self, request: Request, course_pk: str, unit_pk: str, lesson_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)
        self.get_unit_or_404(course_pk, unit_pk)
        lesson = self.get_lesson_or_404(unit_pk, lesson_pk)
        return Response(LessonSerializer(lesson).data)

    @extend_schema(summary="Update lesson", request=LessonSerializer, responses={200: LessonSerializer})
    def patch(self, request: Request, course_pk: str, unit_pk: str, lesson_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)
        self.get_unit_or_404(course_pk, unit_pk)
        lesson = self.get_lesson_or_404(unit_pk, lesson_pk)
        serializer = LessonSerializer(lesson, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        lesson = serializer.save()
        lesson.save(using="mongodb")
        recompute_course_stats(course_pk)
        course_cache.invalidate_course_cache(course_pk)
        return Response(LessonSerializer(lesson).data)

    @extend_schema(summary="Delete lesson", responses={204: None})
    def delete(self, request: Request, course_pk: str, unit_pk: str, lesson_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)
        self.get_unit_or_404(course_pk, unit_pk)
        lesson = self.get_lesson_or_404(unit_pk, lesson_pk)
        lesson.delete(using="mongodb")
        recompute_course_stats(course_pk)
        course_cache.invalidate_course_cache(course_pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Teacher Courses"])
class TeacherLessonReorderView(CourseQuerysetMixin, UnitQuerysetMixin, APIView):
    authentication_classes = [TeacherJWTCookieAuthentication]
    permission_classes = [IsActiveTeacher]

    @extend_schema(summary="Reorder lessons within a unit", request=ReorderSerializer, responses={200: LessonSerializer(many=True)})
    def post(self, request: Request, course_pk: str, unit_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)
        self.get_unit_or_404(course_pk, unit_pk)
        return _reorder_lessons(unit_pk, request.data)


# ---------------------------------------------------------------------------
# ─── ADMIN views ────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


class AdminCourseQuerysetMixin(CourseQuerysetMixin):
    """Admin always sees everything — override base mixin."""

    def get_course_queryset(self, request: Request):
        return Course.objects.using("mongodb").all()


@extend_schema(tags=["Admin Courses"])
class AdminCourseListCreateView(AdminCourseQuerysetMixin, APIView):
    authentication_classes = [AdminJWTCookieAuthentication]
    permission_classes = [IsActiveAdmin]

    @extend_schema(summary="List all courses", responses={200: CourseListSerializer(many=True)})
    def get(self, request: Request) -> Response:
        qs = self.get_course_queryset(request).order_by("-created_at")
        # Filter support
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter.upper())

        paginator = CoursePagination()
        page = paginator.paginate_queryset(list(qs), request)
        data = self.enrich_with_creator_names(page)
        return paginator.get_paginated_response(data)

    @extend_schema(summary="Create a course (admin)", request=CourseWriteSerializer, responses={201: CourseDetailSerializer})
    def post(self, request: Request) -> Response:
        serializer = CourseWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        course = serializer.save(
            created_by=str(request.user.pk),
            created_by_name=request.user.full_name,
            status=Course.Status.DRAFT,
        )
        course.save(using="mongodb")
        return Response(CourseDetailSerializer(course).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Admin Courses"])
class AdminCourseDetailView(AdminCourseQuerysetMixin, APIView):
    authentication_classes = [AdminJWTCookieAuthentication]
    permission_classes = [IsActiveAdmin]

    @extend_schema(summary="Get any course detail", responses={200: CourseDetailSerializer})
    def get(self, request: Request, pk: str) -> Response:
        course = self.get_course_or_404(pk, request)
        return Response(CourseDetailSerializer(course).data)

    @extend_schema(summary="Update any course", request=CourseWriteSerializer, responses={200: CourseDetailSerializer})
    def patch(self, request: Request, pk: str) -> Response:
        course = self.get_course_or_404(pk, request)
        serializer = CourseWriteSerializer(course, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        course = serializer.save()
        course.save(using="mongodb")
        course_cache.invalidate_course_cache(str(course.pk))
        return Response(CourseDetailSerializer(course).data)

    @extend_schema(summary="Delete any course", responses={204: None})
    def delete(self, request: Request, pk: str) -> Response:
        course = self.get_course_or_404(pk, request)
        # Admin can delete any status.
        course_cache.invalidate_course_cache(str(course.pk))
        course.delete(using="mongodb")
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Admin Courses"])
class AdminCoursePublishView(AdminCourseQuerysetMixin, APIView):
    authentication_classes = [AdminJWTCookieAuthentication]
    permission_classes = [IsActiveAdmin]

    @extend_schema(summary="Force-publish any course", responses={200: CourseDetailSerializer})
    def post(self, request: Request, pk: str) -> Response:
        course = self.get_course_or_404(pk, request)
        if course.status != Course.Status.DRAFT:
            raise ValidationError({"detail": "Only DRAFT courses can be published."})
        course.status = Course.Status.PUBLISHED
        course.published_at = timezone.now()
        course.save(using="mongodb")
        course_cache.invalidate_course_cache(str(course.pk))
        return Response(CourseDetailSerializer(course).data)


@extend_schema(tags=["Admin Courses"])
class AdminCourseArchiveView(AdminCourseQuerysetMixin, APIView):
    authentication_classes = [AdminJWTCookieAuthentication]
    permission_classes = [IsActiveAdmin]

    @extend_schema(summary="Force-archive any course", responses={200: CourseDetailSerializer})
    def post(self, request: Request, pk: str) -> Response:
        course = self.get_course_or_404(pk, request)
        if course.status != Course.Status.PUBLISHED:
            raise ValidationError({"detail": "Only PUBLISHED courses can be archived."})
        course.status = Course.Status.ARCHIVED
        course.save(using="mongodb")
        course_cache.invalidate_course_cache(str(course.pk))
        return Response(CourseDetailSerializer(course).data)


@extend_schema(tags=["Admin Courses"])
class AdminCourseUnpublishView(AdminCourseQuerysetMixin, APIView):
    authentication_classes = [AdminJWTCookieAuthentication]
    permission_classes = [IsActiveAdmin]

    @extend_schema(summary="Force-unpublish any course", responses={200: CourseDetailSerializer})
    def post(self, request: Request, pk: str) -> Response:
        course = self.get_course_or_404(pk, request)
        if course.status != Course.Status.PUBLISHED:
            raise ValidationError({"detail": "Only PUBLISHED courses can be unpublished."})
        course.status = Course.Status.DRAFT
        course.published_at = None
        course.save(using="mongodb")
        course_cache.invalidate_course_cache(str(course.pk))
        return Response(CourseDetailSerializer(course).data)


# Admin unit/lesson views (mirror teacher, but with admin auth + no ownership filter)

@extend_schema(tags=["Admin Courses"])
class AdminUnitListCreateView(AdminCourseQuerysetMixin, UnitQuerysetMixin, APIView):
    authentication_classes = [AdminJWTCookieAuthentication]
    permission_classes = [IsActiveAdmin]

    @extend_schema(summary="List units (admin)", responses={200: UnitSerializer(many=True)})
    def get(self, request: Request, course_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)
        units = Unit.objects.using("mongodb").filter(course_id=course_pk).order_by("order")
        return Response(UnitSerializer(units, many=True).data)

    @extend_schema(summary="Create unit (admin)", request=UnitSerializer, responses={201: UnitSerializer})
    def post(self, request: Request, course_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)
        serializer = UnitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        next_order = auto_set_order(
            Unit.objects.using("mongodb").filter(course_id=course_pk)
        )
        unit = serializer.save(course_id=course_pk, order=next_order)
        unit.save(using="mongodb")
        recompute_course_stats(course_pk)
        course_cache.invalidate_course_cache(course_pk)
        return Response(UnitSerializer(unit).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Admin Courses"])
class AdminUnitDetailView(AdminCourseQuerysetMixin, UnitQuerysetMixin, APIView):
    authentication_classes = [AdminJWTCookieAuthentication]
    permission_classes = [IsActiveAdmin]

    @extend_schema(summary="Get unit (admin)", responses={200: UnitSerializer})
    def get(self, request: Request, course_pk: str, unit_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)
        unit = self.get_unit_or_404(course_pk, unit_pk)
        return Response(UnitSerializer(unit).data)

    @extend_schema(summary="Update unit (admin)", request=UnitSerializer, responses={200: UnitSerializer})
    def patch(self, request: Request, course_pk: str, unit_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)
        unit = self.get_unit_or_404(course_pk, unit_pk)
        serializer = UnitSerializer(unit, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        unit = serializer.save()
        unit.save(using="mongodb")
        course_cache.invalidate_course_cache(course_pk)
        return Response(UnitSerializer(unit).data)

    @extend_schema(summary="Delete unit (admin)", responses={204: None})
    def delete(self, request: Request, course_pk: str, unit_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)
        unit = self.get_unit_or_404(course_pk, unit_pk)
        Lesson.objects.using("mongodb").filter(unit_id=unit_pk).delete()
        unit.delete(using="mongodb")
        recompute_course_stats(course_pk)
        course_cache.invalidate_course_cache(course_pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Admin Courses"])
class AdminUnitReorderView(AdminCourseQuerysetMixin, APIView):
    authentication_classes = [AdminJWTCookieAuthentication]
    permission_classes = [IsActiveAdmin]

    @extend_schema(summary="Reorder units (admin)", request=ReorderSerializer, responses={200: UnitSerializer(many=True)})
    def post(self, request: Request, course_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)
        return _reorder_units(course_pk, request.data)


@extend_schema(tags=["Admin Courses"])
class AdminLessonListCreateView(AdminCourseQuerysetMixin, UnitQuerysetMixin, APIView):
    authentication_classes = [AdminJWTCookieAuthentication]
    permission_classes = [IsActiveAdmin]

    @extend_schema(summary="List lessons (admin)", responses={200: LessonSerializer(many=True)})
    def get(self, request: Request, course_pk: str, unit_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)
        self.get_unit_or_404(course_pk, unit_pk)
        lessons = Lesson.objects.using("mongodb").filter(unit_id=unit_pk).order_by("order")
        return Response(LessonSerializer(lessons, many=True).data)

    @extend_schema(summary="Create lesson (admin)", request=LessonSerializer, responses={201: LessonSerializer})
    def post(self, request: Request, course_pk: str, unit_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)
        self.get_unit_or_404(course_pk, unit_pk)
        serializer = LessonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        next_order = auto_set_order(
            Lesson.objects.using("mongodb").filter(unit_id=unit_pk)
        )
        lesson = serializer.save(unit_id=unit_pk, course_id=course_pk, order=next_order)
        lesson.save(using="mongodb")
        recompute_course_stats(course_pk)
        course_cache.invalidate_course_cache(course_pk)
        return Response(LessonSerializer(lesson).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Admin Courses"])
class AdminLessonDetailView(AdminCourseQuerysetMixin, UnitQuerysetMixin, LessonQuerysetMixin, APIView):
    authentication_classes = [AdminJWTCookieAuthentication]
    permission_classes = [IsActiveAdmin]

    @extend_schema(summary="Get lesson (admin)", responses={200: LessonSerializer})
    def get(self, request: Request, course_pk: str, unit_pk: str, lesson_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)
        self.get_unit_or_404(course_pk, unit_pk)
        lesson = self.get_lesson_or_404(unit_pk, lesson_pk)
        return Response(LessonSerializer(lesson).data)

    @extend_schema(summary="Update lesson (admin)", request=LessonSerializer, responses={200: LessonSerializer})
    def patch(self, request: Request, course_pk: str, unit_pk: str, lesson_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)
        self.get_unit_or_404(course_pk, unit_pk)
        lesson = self.get_lesson_or_404(unit_pk, lesson_pk)
        serializer = LessonSerializer(lesson, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        lesson = serializer.save()
        lesson.save(using="mongodb")
        recompute_course_stats(course_pk)
        course_cache.invalidate_course_cache(course_pk)
        return Response(LessonSerializer(lesson).data)

    @extend_schema(summary="Delete lesson (admin)", responses={204: None})
    def delete(self, request: Request, course_pk: str, unit_pk: str, lesson_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)
        self.get_unit_or_404(course_pk, unit_pk)
        lesson = self.get_lesson_or_404(unit_pk, lesson_pk)
        lesson.delete(using="mongodb")
        recompute_course_stats(course_pk)
        course_cache.invalidate_course_cache(course_pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Admin Courses"])
class AdminLessonReorderView(AdminCourseQuerysetMixin, UnitQuerysetMixin, APIView):
    authentication_classes = [AdminJWTCookieAuthentication]
    permission_classes = [IsActiveAdmin]

    @extend_schema(summary="Reorder lessons (admin)", request=ReorderSerializer, responses={200: LessonSerializer(many=True)})
    def post(self, request: Request, course_pk: str, unit_pk: str) -> Response:
        self.get_course_or_404(course_pk, request)
        self.get_unit_or_404(course_pk, unit_pk)
        return _reorder_lessons(unit_pk, request.data)


# ---------------------------------------------------------------------------
# ─── STUDENT views ──────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


@extend_schema(tags=["Student Courses"])
class StudentCourseListView(CourseQuerysetMixin, APIView):
    authentication_classes = [StudentJWTCookieAuthentication]
    permission_classes = [IsActiveStudent]

    @extend_schema(summary="Browse published courses", responses={200: CourseListSerializer(many=True)})
    def get(self, request: Request) -> Response:
        qs = (
            Course.objects.using("mongodb")
            .filter(status=Course.Status.PUBLISHED)
            .order_by("-published_at")
        )

        paginator = CoursePagination()
        page = paginator.paginate_queryset(list(qs), request)
        data = self.enrich_with_creator_names(page)
        return paginator.get_paginated_response(data)


@extend_schema(tags=["Student Courses"])
class StudentCourseDetailView(APIView):
    authentication_classes = [StudentJWTCookieAuthentication]
    permission_classes = [IsActiveStudent, CanViewCourse]

    @extend_schema(summary="Get published course detail", responses={200: CourseDetailSerializer})
    def get(self, request: Request, pk: str) -> Response:
        def _fetch():
            try:
                course = Course.objects.using("mongodb").get(pk=pk, status=Course.Status.PUBLISHED)
                return CourseDetailSerializer(course).data
            except Course.DoesNotExist:
                return None

        data = course_cache.get_or_set_cached_detail(pk, _fetch)
        if data is None:
            raise NotFound("Course not found.")
        return Response(data)


@extend_schema(tags=["Student Courses"])
class StudentCourseOutlineView(APIView):
    authentication_classes = [StudentJWTCookieAuthentication]
    permission_classes = [IsActiveStudent]

    @extend_schema(summary="Get course outline (units + lesson metadata)", responses={200: UnitWithLessonsSerializer(many=True)})
    def get(self, request: Request, pk: str) -> Response:
        def _fetch():
            try:
                course = Course.objects.using("mongodb").get(pk=pk, status=Course.Status.PUBLISHED)
            except Course.DoesNotExist:
                return None
            if not can_user_view_course(request.user, course):
                return None
            units = Unit.objects.using("mongodb").filter(course_id=pk).order_by("order")
            return UnitWithLessonsSerializer(units, many=True).data

        data = course_cache.get_or_set_cached_outline(pk, _fetch)
        if data is None:
            raise NotFound("Course not found.")
        return Response(data)


# ---------------------------------------------------------------------------
# ─── Shared reorder helpers ─────────────────────────────────────────────────
# ---------------------------------------------------------------------------


def _reorder_units(course_pk: str, data: dict) -> Response:
    serializer = ReorderSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    ordered_ids: list[str] = serializer.validated_data["ordered_ids"]

    units = {str(u.pk): u for u in Unit.objects.using("mongodb").filter(course_id=course_pk)}
    missing = [i for i in ordered_ids if i not in units]
    if missing:
        raise ValidationError({"ordered_ids": f"Unknown unit IDs: {missing}"})

    for new_order, uid in enumerate(ordered_ids, start=1):
        units[uid].order = new_order
        units[uid].save(using="mongodb")

    course_cache.invalidate_course_cache(course_pk)
    result = Unit.objects.using("mongodb").filter(course_id=course_pk).order_by("order")
    return Response(UnitSerializer(result, many=True).data)


def _reorder_lessons(unit_pk: str, data: dict) -> Response:
    serializer = ReorderSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    ordered_ids: list[str] = serializer.validated_data["ordered_ids"]

    lessons = {str(lo.pk): lo for lo in Lesson.objects.using("mongodb").filter(unit_id=unit_pk)}
    missing = [i for i in ordered_ids if i not in lessons]
    if missing:
        raise ValidationError({"ordered_ids": f"Unknown lesson IDs: {missing}"})

    for new_order, lid in enumerate(ordered_ids, start=1):
        lessons[lid].order = new_order
        lessons[lid].save(using="mongodb")

    result = Lesson.objects.using("mongodb").filter(unit_id=unit_pk).order_by("order")
    return Response(LessonSerializer(result, many=True).data)
