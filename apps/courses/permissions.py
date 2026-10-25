"""
Course-specific permission classes.

IsCourseOwnerOrAdmin  — object-level: teacher must own the course; admins pass always.
CanViewCourse         — delegates to can_user_view_course() service helper.
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class IsCourseOwnerOrAdmin(BasePermission):
    """
    Object-level permission.

    - ADMIN: always allowed.
    - TEACHER: allowed only if course.created_by matches their UUID.
    - Others: denied (returns False at object level, but view raises 404 first
      for non-owner teachers via the queryset filter in the viewset).
    """

    message = "You do not have permission to access this course."

    def has_object_permission(self, request: Request, view: APIView, obj: object) -> bool:
        user = request.user
        if user.role == "ADMIN":  # type: ignore[union-attr]
            return True
        return str(obj.created_by) == str(user.pk)  # type: ignore[union-attr]


class CanViewCourse(BasePermission):
    """
    Object-level permission for student read access.
    Delegates to the centralised service helper so the logic lives in one place.
    """

    message = "This course is not available."

    def has_object_permission(self, request: Request, view: APIView, obj: object) -> bool:
        from apps.courses.services import can_user_view_course

        return can_user_view_course(request.user, obj)  # type: ignore[arg-type]
