"""
Dashboard ping views — proof-of-permission endpoints.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.authentication import (
    AdminJWTCookieAuthentication,
    StudentJWTCookieAuthentication,
    TeacherJWTCookieAuthentication,
)
from apps.core.permissions import IsActiveAdmin, IsActiveStudent, IsActiveTeacher


class AdminDashboardPingView(APIView):
    """Admin-only protected endpoint to verify active admin role and full token scope."""

    authentication_classes = [AdminJWTCookieAuthentication]
    permission_classes = [IsActiveAdmin]

    @extend_schema(
        tags=["Dashboard"],
        summary="Admin dashboard ping",
        description="Verify admin authentication and active status.",
        responses={200: OpenApiResponse(description="Pong response")},
    )
    def get(self, request: Request) -> Response:
        return Response({"role": "admin", "message": "pong"})


class TeacherDashboardPingView(APIView):
    """Teacher-only protected endpoint to verify active teacher role and full token scope."""

    authentication_classes = [TeacherJWTCookieAuthentication]
    permission_classes = [IsActiveTeacher]

    @extend_schema(
        tags=["Dashboard"],
        summary="Teacher dashboard ping",
        description="Verify teacher authentication, approved status, and active account.",
        responses={200: OpenApiResponse(description="Pong response")},
    )
    def get(self, request: Request) -> Response:
        return Response({"role": "teacher", "message": "pong"})


class StudentDashboardPingView(APIView):
    """Student-only protected endpoint to verify active student role and full token scope."""

    authentication_classes = [StudentJWTCookieAuthentication]
    permission_classes = [IsActiveStudent]

    @extend_schema(
        tags=["Dashboard"],
        summary="Student dashboard ping",
        description="Verify student authentication, email verification, and active account.",
        responses={200: OpenApiResponse(description="Pong response")},
    )
    def get(self, request: Request) -> Response:
        return Response({"role": "student", "message": "pong"})
