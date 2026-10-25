"""
Management command to create an admin user (role=ADMIN).

Usage:
    python manage.py create_admin --email admin@example.com --password secret123 --full-name "Admin User"

Admin accounts must NEVER be created through the public API.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Create an admin user (role=ADMIN, is_staff=True, is_superuser=True)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--email", required=True, help="Admin email address")
        parser.add_argument("--password", required=True, help="Admin password")
        parser.add_argument("--full-name", required=True, help="Admin full name")

    def handle(self, *args, **options) -> None:
        email = options["email"].strip().lower()
        password = options["password"]
        full_name = options["full_name"].strip()

        if User.objects.filter(email=email).exists():
            raise CommandError(f"A user with email '{email}' already exists.")

        user = User.objects.create_superuser(
            email=email,
            password=password,
            full_name=full_name,
        )

        self.stdout.write(self.style.SUCCESS(f"Admin user created: {user.email} (id={user.id})"))
