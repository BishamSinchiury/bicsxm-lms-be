"""
Global pytest fixtures and test configuration.
Uses fakeredis to isolate tests without requiring an active Redis server.
"""

import fakeredis
import pytest


@pytest.fixture(autouse=True)
def configure_test_settings(settings):
    """Ensure Celery runs synchronously and cache uses in-memory storage during tests."""
    from config.celery import app as celery_app

    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
    )
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-cache",
        },
        # Courses cache — also in-memory during tests.
        "courses": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-courses-cache",
        },
    }


@pytest.fixture(autouse=True)
def mock_otp_redis(monkeypatch):
    """Provide a consistent in-memory FakeRedis client for all OTP and token blacklist operations."""
    fake_client = fakeredis.FakeRedis(decode_responses=True)

    # Patch get_otp_redis in both apps.core.utils and apps.authentication.services
    monkeypatch.setattr("apps.core.utils.get_otp_redis", lambda: fake_client)
    monkeypatch.setattr("apps.core.utils._otp_redis_client", fake_client)

    return fake_client
