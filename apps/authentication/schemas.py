"""
drf-spectacular schema extensions for cookie and JWT authentication documentation.
"""

from __future__ import annotations

from drf_spectacular.extensions import OpenApiAuthenticationExtension

from apps.core.authentication import (
    AdminJWTCookieAuthentication,
    StudentJWTCookieAuthentication,
    TeacherJWTCookieAuthentication,
)


class AdminCookieAuthExtension(OpenApiAuthenticationExtension):
    target_class = AdminJWTCookieAuthentication
    name = "adminCookieAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "cookie",
            "name": "admin_access",
            "description": "Admin access token stored in HttpOnly cookie 'admin_access'.",
        }


class TeacherCookieAuthExtension(OpenApiAuthenticationExtension):
    target_class = TeacherJWTCookieAuthentication
    name = "teacherCookieAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "cookie",
            "name": "teacher_access",
            "description": "Teacher access token stored in HttpOnly cookie 'teacher_access'.",
        }


class StudentCookieAuthExtension(OpenApiAuthenticationExtension):
    target_class = StudentJWTCookieAuthentication
    name = "studentCookieAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "cookie",
            "name": "student_access",
            "description": "Student access token stored in HttpOnly cookie 'student_access'.",
        }
