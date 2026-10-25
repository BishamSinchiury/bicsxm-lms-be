"""
Celery application for the LMS project.

Usage:
    celery -A config worker -l info
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("lms")

# Read config from Django settings, namespace CELERY_
app.config_from_object("django.conf:settings", namespace="CELERY")

# In development or test, execute tasks synchronously
from django.conf import settings  # noqa: E402
if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
    app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
    )

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> None:
    """Verify Celery is working."""
    print(f"Request: {self.request!r}")
