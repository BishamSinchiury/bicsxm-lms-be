"""
Database router for the LMS project.

- All models in the ``courses`` app are read from / written to / migrated on the
  ``mongodb`` database alias.
- All other apps continue to use the ``default`` PostgreSQL database.
- Cross-database relations (e.g. courses ↔ accounts) are explicitly blocked.
"""

from __future__ import annotations

MONGO_APPS: frozenset[str] = frozenset({"courses"})


class CourseRouter:
    """Route ``courses`` app models to MongoDB; everything else to PostgreSQL."""

    # ------------------------------------------------------------------
    # Read / write routing
    # ------------------------------------------------------------------

    def db_for_read(self, model: type, **hints: object) -> str | None:
        if model._meta.app_label in MONGO_APPS:
            return "mongodb"
        return "default"

    def db_for_write(self, model: type, **hints: object) -> str | None:
        if model._meta.app_label in MONGO_APPS:
            return "mongodb"
        return "default"

    # ------------------------------------------------------------------
    # Relation guard — block cross-DB FK / M2M resolution
    # ------------------------------------------------------------------

    def allow_relation(self, obj1: object, obj2: object, **hints: object) -> bool | None:
        labels = {obj1._meta.app_label, obj2._meta.app_label}  # type: ignore[union-attr]
        # If one side is Mongo and the other is Postgres — disallow.
        if MONGO_APPS & labels and not labels <= MONGO_APPS:
            return False
        # Both on the same DB — allow.
        if labels <= MONGO_APPS or not (MONGO_APPS & labels):
            return True
        return None

    # ------------------------------------------------------------------
    # Migration routing
    # ------------------------------------------------------------------

    def allow_migrate(
        self,
        db: str,
        app_label: str,
        model_name: str | None = None,
        **hints: object,
    ) -> bool | None:
        if app_label in MONGO_APPS:
            return db == "mongodb"
        # Non-Mongo apps must NOT run migrations on MongoDB.
        if db == "mongodb":
            return False
        return db == "default"
