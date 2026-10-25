"""
Health check view — reports connectivity to Postgres, Redis, and MongoDB.

GET /api/health/  → 200 if all services reachable, 503 if any fail.
"""

from __future__ import annotations

from django.core.cache import caches
from django.db import connections
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


@extend_schema(tags=["Health"], summary="Service health check")
class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        checks: dict[str, dict] = {}
        overall_ok = True

        # ── PostgreSQL ────────────────────────────────────────────────────
        try:
            conn = connections["default"]
            conn.ensure_connection()
            checks["postgres"] = {"status": "ok", "db": conn.settings_dict.get("NAME")}
        except Exception as exc:
            checks["postgres"] = {"status": "error", "detail": str(exc)}
            overall_ok = False

        # ── Redis (default cache) ─────────────────────────────────────────
        try:
            cache = caches["default"]
            cache.set("_health_ping", "1", timeout=5)
            val = cache.get("_health_ping")
            if val != "1":
                raise RuntimeError("Redis ping value mismatch")
            checks["redis"] = {"status": "ok"}
        except Exception as exc:
            checks["redis"] = {"status": "error", "detail": str(exc)}
            overall_ok = False

        # ── MongoDB ───────────────────────────────────────────────────────
        try:
            from django.db import connections as dj_connections

            mongo_conn = dj_connections["mongodb"]
            mongo_conn.ensure_connection()
            client = mongo_conn.connection.client
            info = client.admin.command("ping")
            rs_status = None
            try:
                rs_info = client.admin.command("replSetGetStatus")
                rs_status = rs_info.get("set")
            except Exception:
                pass
            checks["mongodb"] = {
                "status": "ok" if info.get("ok") == 1.0 else "error",
                "replica_set": rs_status,
            }
            if info.get("ok") != 1.0:
                overall_ok = False
        except Exception as exc:
            checks["mongodb"] = {"status": "error", "detail": str(exc)}
            overall_ok = False

        http_status = 200 if overall_ok else 503
        return Response({"healthy": overall_ok, "services": checks}, status=http_status)
