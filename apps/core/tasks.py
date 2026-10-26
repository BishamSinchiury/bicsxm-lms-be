"""
Celery async tasks for sending emails with retries and exponential backoff.
"""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def send_notification_sync(
    email: str,
    subject: str,
    template_name: str,
    context: dict[str, Any] | None = None,
) -> None:
    """Synchronous helper for rendering and sending an email message."""
    logger.info("Sending email '%s' to %s", subject, email)
    ctx = context or {}

    text_template = f"emails/{template_name}.txt"
    html_template = f"emails/{template_name}.html"

    text_content = render_to_string(text_template, ctx)
    html_content = render_to_string(html_template, ctx)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )
    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=False)


@shared_task(
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 5},
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
)
def send_otp_email(
    email: str,
    otp: str,
    purpose: str = "verification",
    role: str = "",
    purpose_slug: str = "",
) -> None:
    """
    Send an OTP email asynchronously with retries on failure.

    Args:
        email: Recipient address.
        otp: Plain-text one-time password (displayed in the email).
        purpose: Human-readable description shown in the email body.
        role: Role slug (student | teacher | admin) used to build the frontend link.
        purpose_slug: URL slug for the frontend page
                      (e.g. "verify-email", "reset-password").
    """
    logger.info("Sending OTP email to %s for %s", email, purpose)

    # Build frontend link — contains NO OTP or token; the user types the OTP.
    link = ""
    if role and purpose_slug:
        import urllib.parse

        base = getattr(settings, "FRONTEND_BASE_URL", "").rstrip("/")
        query = urllib.parse.urlencode({"email": email})
        link = f"{base}/{role}/{purpose_slug}?{query}"

    context = {
        "email": email,
        "otp": otp,
        "purpose": purpose,
        "ttl_minutes": int(settings.OTP_TTL // 60),
        "link": link,
    }
    subject = f"Your LMS Verification Code"
    send_notification_sync(email, subject, "otp", context)



@shared_task(
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 5},
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
)
def send_notification_email(
    email: str,
    subject: str,
    template_name: str,
    context: dict[str, Any] | None = None,
) -> None:
    """
    Send a general notification email asynchronously.
    """
    send_notification_sync(email, subject, template_name, context)


@shared_task(
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 5},
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
)
def send_teacher_status_email(user_id: str, approved: bool, reason: str = "") -> None:
    """Send approval or rejection email to teacher upon admin review."""
    from apps.accounts.models import User

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.warning("send_teacher_status_email: User %s does not exist", user_id)
        return

    if approved:
        subject = "Your LMS Teacher Application has been Approved"
        template_name = "teacher_approved"
    else:
        subject = "Status of Your LMS Teacher Application"
        template_name = "teacher_rejected"

    send_notification_sync(
        email=user.email,
        subject=subject,
        template_name=template_name,
        context={"full_name": user.full_name, "email": user.email, "reason": reason},
    )
