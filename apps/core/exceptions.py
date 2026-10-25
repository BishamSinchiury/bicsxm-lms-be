"""
Custom exception handler and standard error response formatting.

All errors return the standard format:
{
    "error": {
        "code": "ERROR_CODE",
        "message": "Human readable message",
        "field_errors": { ... }
    }
}
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler


class LMSAPIException(exceptions.APIException):
    """Base class for LMS-specific API exceptions with custom error codes."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "An error occurred."
    default_code = "BAD_REQUEST"

    def __init__(
        self,
        detail: str | None = None,
        code: str | None = None,
        status_code: int | None = None,
        field_errors: dict[str, Any] | None = None,
    ) -> None:
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.default_code = code
        self.field_errors = field_errors or {}
        super().__init__(detail=detail or self.default_detail, code=self.default_code)


class OTPInvalidError(LMSAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid OTP code."
    default_code = "OTP_INVALID"


class OTPExpiredError(LMSAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "OTP code has expired."
    default_code = "OTP_EXPIRED"


class OTPMaxAttemptsError(LMSAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Maximum OTP attempts exceeded. Please request a new OTP."
    default_code = "OTP_MAX_ATTEMPTS"


class OTPCooldownError(LMSAPIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = "Please wait before requesting another OTP."
    default_code = "OTP_COOLDOWN"


class AccountInactiveError(LMSAPIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Account is inactive or pending approval."
    default_code = "ACCOUNT_INACTIVE"


def _format_error_response(
    code: str,
    message: str,
    field_errors: dict[str, Any] | None = None,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> Response:
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "field_errors": field_errors or {},
        }
    }
    return Response(payload, status=status_code)


def custom_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """
    Standardize all exception responses to the LMS error envelope:
    {
        "error": {
            "code": "...",
            "message": "...",
            "field_errors": { ... }
        }
    }
    """
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    # Call REST framework's default exception handler to get standard handling
    response = exception_handler(exc, context)

    if response is None:
        # Unhandled server exception
        import logging

        logging.getLogger(__name__).exception("Unhandled exception in view: %s", exc)
        return _format_error_response(
            code="SERVER_ERROR",
            message=f"An unexpected server error occurred: {exc}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # Handle custom LMS exceptions
    if isinstance(exc, LMSAPIException):
        return _format_error_response(
            code=exc.default_code,
            message=str(exc.detail),
            field_errors=exc.field_errors,
            status_code=exc.status_code,
        )

    # Handle standard DRF exceptions
    if isinstance(exc, exceptions.ValidationError):
        field_errors: dict[str, list[str]] = {}
        detail = response.data

        if isinstance(detail, dict):
            for key, val in detail.items():
                if isinstance(val, list):
                    field_errors[key] = [str(item) for item in val]
                elif isinstance(val, str):
                    field_errors[key] = [val]
                elif isinstance(val, dict):
                    field_errors[key] = [str(val)]
        elif isinstance(detail, list):
            field_errors["non_field_errors"] = [str(item) for item in detail]
        else:
            field_errors["non_field_errors"] = [str(detail)]

        return _format_error_response(
            code="VALIDATION_ERROR",
            message="Invalid input.",
            field_errors=field_errors,
            status_code=response.status_code,
        )

    if isinstance(exc, exceptions.AuthenticationFailed):
        msg = str(getattr(exc, "detail", "Authentication failed."))
        code = "AUTHENTICATION_FAILED"
        if "inactive" in msg.lower() or "deactivated" in msg.lower():
            code = "ACCOUNT_INACTIVE"
            status_code = status.HTTP_403_FORBIDDEN
        else:
            status_code = status.HTTP_401_UNAUTHORIZED
        return _format_error_response(
            code=code,
            message=msg,
            status_code=status_code,
        )

    if isinstance(exc, exceptions.NotAuthenticated):
        return _format_error_response(
            code="AUTHENTICATION_FAILED",
            message="Authentication credentials were not provided.",
            status_code=response.status_code,
        )

    if isinstance(exc, exceptions.PermissionDenied):
        return _format_error_response(
            code="PERMISSION_DENIED",
            message=str(
                getattr(exc, "detail", "You do not have permission to perform this action.")
            ),
            status_code=response.status_code,
        )

    if isinstance(exc, exceptions.NotFound):
        return _format_error_response(
            code="NOT_FOUND",
            message=str(getattr(exc, "detail", "Resource not found.")),
            status_code=response.status_code,
        )

    if isinstance(exc, exceptions.Throttled):
        wait_seconds = exc.wait
        msg = (
            f"Request was throttled. Expected available in {wait_seconds} seconds."
            if wait_seconds
            else "Request was throttled."
        )
        return _format_error_response(
            code="THROTTLED",
            message=msg,
            status_code=response.status_code,
        )

    # Fallback for any other DRF exception
    msg = (
        str(response.data.get("detail", "An error occurred."))
        if isinstance(response.data, dict)
        else str(response.data)
    )
    return _format_error_response(
        code="BAD_REQUEST",
        message=msg,
        status_code=response.status_code,
    )
