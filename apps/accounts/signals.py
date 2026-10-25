"""Auto-create role-specific profiles when a User is created."""

from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import StudentProfile, TeacherProfile, User


@receiver(post_save, sender=User)
def create_user_profile(sender, instance: User, created: bool, **kwargs) -> None:
    """Create the matching profile (Teacher or Student) for newly created users."""
    if not created:
        return

    if instance.role == User.Role.TEACHER:
        TeacherProfile.objects.get_or_create(user=instance)
    elif instance.role == User.Role.STUDENT:
        StudentProfile.objects.get_or_create(user=instance)
    # Admin accounts do not get a profile.
