"""
Tests for Rate Limiting and Throttling:
- OTP email throttle
- Login email/IP throttle
"""

from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.fixture
def client():
    return APIClient()


@pytest.mark.django_db
class TestThrottling:
    @patch("apps.authentication.views.send_otp_email.delay")
    def test_login_rate_limiting(self, mock_email, client, settings):
        # Set a low limit for test speed
        settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["login_email"] = "3/minute"
        settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["login_ip"] = "5/minute"

        User.objects.create_user(
            email="throttle_test@example.com",
            password="CorrectPassword123!",
            full_name="Throttle User",
            role=User.Role.STUDENT,
        )

        url = "/api/student/auth/login/"
        payload = {"email": "throttle_test@example.com", "password": "WrongPassword"}

        # Send attempts until throttled
        throttled = False
        for _ in range(5):
            res = client.post(url, payload, format="json")
            if res.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                throttled = True
                assert res.data["error"]["code"] == "THROTTLED"
                break
            assert res.status_code == status.HTTP_401_UNAUTHORIZED

        assert throttled is True
