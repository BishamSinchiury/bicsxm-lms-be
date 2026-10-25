"""
Redis-backed rate limiting throttles for OTP requests and authentication attempts.
"""

from __future__ import annotations

from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView


class BaseEmailRateThrottle(SimpleRateThrottle):
    """Throttle based on the email provided in request data or the authenticated user."""

    def get_cache_key(self, request: Request, view: APIView) -> str | None:
        email = None
        if hasattr(request, "data") and isinstance(request.data, dict):
            email = request.data.get("email")

        if not email and request.user and request.user.is_authenticated:
            email = getattr(request.user, "email", None)

        if not email:
            # If no email is found, fall back to client IP so the request is still limited
            ident = self.get_ident(request)
            return self.cache_format % {"scope": self.scope, "ident": ident}

        return self.cache_format % {"scope": self.scope, "ident": email.strip().lower()}


class BaseIPRateThrottle(SimpleRateThrottle):
    """Throttle based on the client IP address."""

    def get_cache_key(self, request: Request, view: APIView) -> str | None:
        ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class OTPEmailRateThrottle(BaseEmailRateThrottle):
    """Rate limit for requesting OTPs by email (default 5/hour)."""

    scope = "otp_email"


class OTPIPRateThrottle(BaseIPRateThrottle):
    """Rate limit for requesting OTPs by client IP (default 10/hour)."""

    scope = "otp_ip"


class LoginEmailRateThrottle(BaseEmailRateThrottle):
    """Rate limit for login attempts by email (default 10/hour)."""

    scope = "login_email"


class LoginIPRateThrottle(BaseIPRateThrottle):
    """Rate limit for login attempts by client IP (default 20/hour)."""

    scope = "login_ip"
