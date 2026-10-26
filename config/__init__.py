# Expose the Celery app here so that @shared_task decorators in all
# installed apps bind to the 'lms' Celery instance (not a blank default).
# See: https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html
from config.celery import app as celery_app  # noqa: F401

__all__ = ["celery_app"]
