"""Django admin registration for accounts models."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.models import StudentProfile, TeacherProfile, User


class TeacherProfileInline(admin.StackedInline):
    model = TeacherProfile
    can_delete = False
    verbose_name_plural = "Teacher Profile"


class StudentProfileInline(admin.StackedInline):
    model = StudentProfile
    can_delete = False
    verbose_name_plural = "Student Profile"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin view for the custom User model."""

    list_display = (
        "email",
        "full_name",
        "role",
        "is_email_verified",
        "approval_status",
        "is_active",
        "date_joined",
    )
    list_filter = ("role", "is_email_verified", "approval_status", "is_active", "is_staff")
    search_fields = ("email", "full_name")
    ordering = ("-date_joined",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal", {"fields": ("full_name",)}),
        (
            "Role & Status",
            {"fields": ("role", "is_email_verified", "approval_status", "is_approved")},
        ),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Dates", {"fields": ("last_login",)}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "role", "password1", "password2"),
            },
        ),
    )

    def get_inlines(self, request, obj=None):
        """Show the correct profile inline based on user role."""
        if obj is None:
            return []
        if obj.role == User.Role.TEACHER:
            return [TeacherProfileInline]
        if obj.role == User.Role.STUDENT:
            return [StudentProfileInline]
        return []


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "department", "phone")
    search_fields = ("user__email", "department")


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "enrollment_id", "phone")
    search_fields = ("user__email", "enrollment_id")
