import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Core"

    def ready(self) -> None:
        """
        Post-startup checks.
        If EMAIL_HOST_PASSWORD is empty we silently fall back to the console
        email backend so development/staging environments never crash, and
        log a clear warning so the operator knows what to do.
        """
        from django.conf import settings

        if getattr(settings, "EMAIL_BACKEND", "").endswith("smtp.EmailBackend"):
            if not getattr(settings, "EMAIL_HOST_PASSWORD", ""):
                logger.warning(
                    "⚠  EMAIL_HOST_PASSWORD is not set. "
                    "Falling back to console email backend. "
                    "To enable real email delivery, set EMAIL_HOST_PASSWORD to a "
                    "Gmail App Password (see .env.example for instructions)."
                )
                settings.EMAIL_BACKEND = (
                    "django.core.mail.backends.console.EmailBackend"
                )

